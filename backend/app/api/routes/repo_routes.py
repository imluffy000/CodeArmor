"""Connected-repository endpoints: list available, connect (with background sync), status."""
import asyncio
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.logging import logger
from app.db.models import Repository, SyncJob, User
from app.services.auth_service import get_current_user
from app.services.crypto_service import decrypt_token
from app.services.github_oauth_service import fetch_repo, list_pull_requests, list_user_repos
from app.services.sync_service import run_repo_sync

router = APIRouter(prefix="/repos", tags=["repos"])

REPO_URL_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$"
)


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
        "synced_at": repo.synced_at.isoformat() if repo.synced_at else None,
    }


@router.get("/available")
async def available_repos(
    page: int = Query(1, ge=1),
    search: str = Query("", max_length=100),
    user: User = Depends(get_current_user),
):
    """List repos the user can access on GitHub (paginated, newest activity first)."""
    token = decrypt_token(user.access_token_encrypted)
    try:
        repos = await list_user_repos(token, page=page)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc.response.status_code}")

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
        if not search or search.lower() in r["full_name"].lower()
    ]
    return {"page": page, "repos": items}


@router.post("/connect")
async def connect_repo(body: ConnectRepoRequest, user: User = Depends(get_current_user)):
    """Connect a repo (from picker or pasted URL) and start a background sync job."""
    raw = body.full_name or body.url
    if not raw:
        raise HTTPException(status_code=422, detail="Provide full_name or url")

    match = REPO_URL_RE.match(raw.strip())
    if not match:
        raise HTTPException(status_code=422, detail="Invalid repository URL or name. Expected owner/repo or a GitHub URL.")
    full_name = f"{match.group('owner')}/{match.group('name')}"

    existing = Repository.get_or_none(
        (Repository.user == user) & (Repository.full_name == full_name)
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"{full_name} is already connected")

    # Verify the user can actually access this repo before saving
    token = decrypt_token(user.access_token_encrypted)
    try:
        data = await fetch_repo(token, full_name)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Repository {full_name} not found or you don't have access")
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc.response.status_code}")

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

    # Fire-and-forget background sync; the request returns immediately
    asyncio.create_task(run_repo_sync(repo.id, job.id))
    logger.info("Connected repo %s for %s, sync job %s queued", repo.full_name, user.login, job.id)

    return {"repo": _repo_dict(repo), "sync_job_id": job.id}


@router.get("")
def list_connected(user: User = Depends(get_current_user)):
    repos = Repository.select().where(Repository.user == user).order_by(Repository.created_at.desc())
    return {"repos": [_repo_dict(r) for r in repos]}


@router.get("/{repo_id}/sync")
def sync_status(repo_id: int, user: User = Depends(get_current_user)):
    repo = Repository.get_or_none((Repository.id == repo_id) & (Repository.user == user))
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not connected")
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
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        },
    }


@router.get("/{repo_id}/pulls")
async def repo_pulls(
    repo_id: int,
    state: str = Query("open", pattern="^(open|closed|all)$"),
    page: int = Query(1, ge=1),
    user: User = Depends(get_current_user),
):
    """List pull requests for a connected repo using the user's token."""
    repo = Repository.get_or_none((Repository.id == repo_id) & (Repository.user == user))
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not connected")

    token = decrypt_token(user.access_token_encrypted)
    try:
        pulls = await list_pull_requests(token, repo.full_name, state=state, page=page)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc.response.status_code}")

    return {
        "repo": repo.full_name,
        "state": state,
        "page": page,
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


@router.delete("/{repo_id}")
def disconnect_repo(repo_id: int, user: User = Depends(get_current_user)):
    repo = Repository.get_or_none((Repository.id == repo_id) & (Repository.user == user))
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not connected")
    repo.delete_instance(recursive=True)
    return {"ok": True}
