"""Connected-repository endpoints: browse, connect, sync status, pull requests."""
import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.logging import audit, logger
from app.core.timeutil import iso_utc
from app.db.models import Repository, SyncJob, User
from app.github import client as gh
from app.services.auth_service import get_current_user, get_user_github_token, require_csrf
from app.services.sync_service import run_repo_sync, track_task

router = APIRouter(prefix="/repos", tags=["repos"])

# Deliberately strict: GitHub owner and repo names cannot contain "..", "?" or
# "#", and those segments end up interpolated into an API path.
_SEGMENT = r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?"
REPO_URL_RE = re.compile(
    rf"^(?:https?://github\.com/)?(?P<owner>{_SEGMENT})/(?P<name>{_SEGMENT})(?:\.git)?/?$"
)

PER_PAGE = 30


class ConnectRepoRequest(BaseModel):
    full_name: str | None = None  # "owner/repo" from the picker
    url: str | None = None  # pasted URL


def _repo_dict(repo: Repository) -> dict:
    return {
        "id": repo.id,
        "full_name": repo.full_name,
        "owner": repo.owner,
        "name": repo.name,
        "private": repo.private,
        "default_branch": repo.default_branch,
        "html_url": repo.html_url,
        "description": repo.description,
        "language": repo.language,
        "stars": repo.stars,
        "open_prs": repo.open_prs,
        "sync_status": repo.sync_status,
        "synced_at": iso_utc(repo.synced_at),
    }


def _owned_repo(user: User, repo_id: int) -> Repository:
    repo = Repository.get_or_none((Repository.id == repo_id) & (Repository.user == user))
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not connected")
    return repo


@router.get("/available")
async def available_repos(
    page: int = Query(1, ge=1),
    search: str = Query("", max_length=100),
    user: User = Depends(get_current_user),
):
    """Repositories the user can access on GitHub.

    Search goes to GitHub rather than filtering the page we already fetched.
    Filtering after pagination searched only 30 of the user's repositories, and
    because the filtered page then held fewer than a full page, the client's
    "is there a next page" heuristic disabled Next - dead-ending anyone with
    more than 30 repositories.
    """
    token = get_user_github_token(user)
    term = search.strip()

    try:
        if term:
            result = await gh.search_user_repos(token, term, page=page, per_page=PER_PAGE)
            repos, total = result["items"], result["total"]
        else:
            repos = await gh.list_user_repos(token, page=page, per_page=PER_PAGE)
            total = None
    except gh.GitHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.safe_message)

    connected = {r.full_name for r in user.repositories}
    items = [
        {
            "full_name": r["full_name"],
            "private": r["private"],
            "description": r.get("description"),
            "language": r.get("language"),
            "pushed_at": r.get("pushed_at"),
            "connected": r["full_name"] in connected,
        }
        for r in repos
    ]

    return {
        "page": page,
        "per_page": PER_PAGE,
        "total": total,
        # Explicit, so the client never has to infer it from the page length.
        "has_more": (page * PER_PAGE < total) if total is not None else len(repos) == PER_PAGE,
        "repos": items,
    }


@router.post("/connect", dependencies=[Depends(require_csrf)])
async def connect_repo(body: ConnectRepoRequest, user: User = Depends(get_current_user)):
    """Connect a repository and start a background metadata sync."""
    raw = body.full_name or body.url
    if not raw:
        raise HTTPException(status_code=422, detail="Provide full_name or url")

    match = REPO_URL_RE.match(raw.strip())
    if not match:
        raise HTTPException(
            status_code=422,
            detail="Invalid repository. Expected owner/repo or a GitHub URL.",
        )
    full_name = f"{match.group('owner')}/{match.group('name')}"

    if Repository.get_or_none(
        (Repository.user == user) & (Repository.full_name == full_name)
    ):
        raise HTTPException(status_code=409, detail=f"{full_name} is already connected")

    # Confirm the user can actually reach it before storing anything.
    token = get_user_github_token(user)
    try:
        data = await gh.fetch_repo(token, full_name)
    except gh.GitHubNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"{full_name} was not found, or your account cannot access it.",
        )
    except gh.GitHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.safe_message)

    repo = Repository.create(
        user=user,
        full_name=data["full_name"],
        owner=data["owner"]["login"],
        name=data["name"],
        private=data["private"],
        default_branch=data.get("default_branch", "main"),
        html_url=data["html_url"],
        description=data.get("description"),
        language=data.get("language"),
        stars=data.get("stargazers_count", 0),
        sync_status="pending",
    )
    job = SyncJob.create(repository=repo, status="queued", progress="Queued")

    # Keep a strong reference: the event loop only weakly references a bare
    # task, so a fire-and-forget create_task can be collected mid-flight.
    track_task(asyncio.create_task(run_repo_sync(repo.id, job.id)))

    audit("repo.connected", user_id=user.id, repo_id=repo.id, private=repo.private)
    return {"repo": _repo_dict(repo), "sync_job_id": job.id}


@router.get("")
def list_connected(user: User = Depends(get_current_user)):
    repos = (
        Repository.select()
        .where(Repository.user == user)
        .order_by(Repository.created_at.desc())
    )
    return {"repos": [_repo_dict(r) for r in repos]}


@router.get("/{repo_id}/sync")
def sync_status(repo_id: int, user: User = Depends(get_current_user)):
    repo = _owned_repo(user, repo_id)
    job = (
        SyncJob.select()
        .where(SyncJob.repository == repo)
        .order_by(SyncJob.created_at.desc())
        .first()
    )
    return {
        "repo": _repo_dict(repo),
        "job": None
        if job is None
        else {
            "id": job.id,
            "status": job.status,
            "progress": job.progress,
            "error": job.error,
            "started_at": iso_utc(job.started_at),
            "finished_at": iso_utc(job.finished_at),
        },
    }


@router.post("/{repo_id}/sync", dependencies=[Depends(require_csrf)])
def resync_repo(repo_id: int, user: User = Depends(get_current_user)):
    """Re-sync metadata. Without this, the open-PR count is frozen at connect time."""
    repo = _owned_repo(user, repo_id)
    job = SyncJob.create(repository=repo, status="queued", progress="Queued")
    repo.sync_status = "pending"
    repo.save()
    track_task(asyncio.create_task(run_repo_sync(repo.id, job.id)))
    return {"repo": _repo_dict(repo), "sync_job_id": job.id}


@router.get("/{repo_id}/pulls")
async def repo_pulls(
    repo_id: int,
    state: str = Query("open", pattern="^(open|closed|all)$"),
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user),
):
    """Pull requests for a connected repository, using the user's own token."""
    repo = _owned_repo(user, repo_id)
    token = get_user_github_token(user)

    try:
        pulls = await gh.list_pull_requests(
            token, repo.full_name, state=state, page=page, per_page=PER_PAGE
        )
    except gh.GitHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.safe_message)

    return {
        "repo": repo.full_name,
        "repo_id": repo.id,
        "state": state,
        "page": page,
        "has_more": len(pulls) == PER_PAGE,
        "pulls": [
            {
                "number": p["number"],
                "title": p["title"],
                "state": p["state"],
                "draft": p.get("draft", False),
                "html_url": p["html_url"],
                "user": p["user"]["login"] if p.get("user") else None,
                "user_avatar": p["user"]["avatar_url"] if p.get("user") else None,
                "head": p["head"]["ref"] if p.get("head") else None,
                "base": p["base"]["ref"] if p.get("base") else None,
                "created_at": p.get("created_at"),
                "updated_at": p.get("updated_at"),
            }
            for p in pulls
        ],
    }


@router.delete("/{repo_id}", dependencies=[Depends(require_csrf)])
def disconnect_repo(repo_id: int, user: User = Depends(get_current_user)):
    repo = _owned_repo(user, repo_id)
    repo.delete_instance(recursive=True)
    audit("repo.disconnected", user_id=user.id, repo_id=repo_id)
    return {"ok": True}
