"""The single GitHub client.

One transport (async httpx), one auth model (the signed-in user's OAuth token,
never a server-wide token), and typed errors that the API layer maps to HTTP
status codes in one place.

There is deliberately no fallback to a global GITHUB_TOKEN. A server-wide token
turns every review endpoint into a confused deputy: an unauthenticated caller
could ask the server to read any private PR the deployment owner can see, and to
post a review under the owner's identity.
"""
import asyncio
import re
import time
from typing import Any

import httpx

from app.core.logging import logger

GITHUB_API = "https://api.github.com"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)

PR_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)"
    r"/pull/(?P<number>\d+)/?$"
)


class GitHubError(RuntimeError):
    """Base class for GitHub failures, carrying a client-safe message."""

    status_code = 502
    safe_message = "GitHub request failed."


class GitHubNotFound(GitHubError):
    status_code = 404
    safe_message = "Not found on GitHub, or your account cannot access it."


class GitHubForbidden(GitHubError):
    status_code = 403
    safe_message = "GitHub refused the request. Check the granted OAuth scopes."


class GitHubRateLimited(GitHubError):
    status_code = 429
    safe_message = "GitHub API rate limit reached. Try again shortly."

    def __init__(self, message: str, reset_in_seconds: int | None = None):
        super().__init__(message)
        self.reset_in_seconds = reset_in_seconds


class GitHubUnauthorized(GitHubError):
    status_code = 401
    safe_message = "Your GitHub authorization is no longer valid. Sign in again."


def parse_pr_url(pr_url: str) -> dict:
    """Split a PR URL into owner/repo/number, or raise ValueError."""
    match = PR_URL_RE.match((pr_url or "").strip())
    if not match:
        raise ValueError(
            "Invalid GitHub PR URL. Expected "
            "https://github.com/OWNER/REPO/pull/NUMBER"
        )
    owner = match.group("owner")
    repo = match.group("repo")
    return {
        "owner": owner,
        "repo": repo,
        "pr_number": int(match.group("number")),
        "full_name": owner + "/" + repo,
    }


def _headers(token: str, accept: str = "application/vnd.github+json") -> dict:
    if not token:
        raise GitHubUnauthorized("No GitHub token available for this request")
    return {
        "Authorization": "Bearer " + token,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _rate_limit_reset(response: httpx.Response) -> int | None:
    retry_after = response.headers.get("retry-after")
    if retry_after and retry_after.isdigit():
        return int(retry_after)
    reset = response.headers.get("x-ratelimit-reset")
    if reset and reset.isdigit():
        return max(0, int(reset) - int(time.time()))
    return None


def _raise_for_status(response: httpx.Response, what: str) -> None:
    if response.status_code < 300:
        return

    remaining = response.headers.get("x-ratelimit-remaining")
    if response.status_code in (403, 429) and remaining == "0":
        raise GitHubRateLimited(
            what + ": rate limited", reset_in_seconds=_rate_limit_reset(response)
        )
    if response.status_code == 401:
        raise GitHubUnauthorized(what + ": unauthorized")
    if response.status_code == 403:
        raise GitHubForbidden(what + ": forbidden")
    if response.status_code == 404:
        raise GitHubNotFound(what + ": not found")

    # Never surface the raw body to a client: GitHub echoes request details, and
    # for a private repository even an error message discloses its existence.
    logger.warning(
        "GitHub %s failed: status=%s body=%.500s",
        what,
        response.status_code,
        response.text,
    )
    raise GitHubError(what + ": unexpected status " + str(response.status_code))


async def _request(
    method: str,
    url: str,
    token: str,
    *,
    what: str,
    accept: str = "application/vnd.github+json",
    params: dict | None = None,
    json_body: dict | None = None,
    raw_text: bool = False,
) -> Any:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.request(
                method,
                url,
                headers=_headers(token, accept),
                params=params,
                json=json_body,
            )
        except httpx.TimeoutException as exc:
            raise GitHubError(what + ": timed out") from exc
        except httpx.HTTPError as exc:
            raise GitHubError(what + ": transport error") from exc

    _raise_for_status(response, what)
    return response.text if raw_text else response.json()


# --------------------------------------------------------------------------
# User & repositories
# --------------------------------------------------------------------------

async def fetch_github_user(token: str) -> dict:
    return await _request("GET", GITHUB_API + "/user", token, what="fetch user")


async def list_user_repos(token: str, page: int = 1, per_page: int = 30) -> list[dict]:
    """Repos the authenticated user can access, most recently pushed first."""
    return await _request(
        "GET",
        GITHUB_API + "/user/repos",
        token,
        what="list repositories",
        params={"page": page, "per_page": per_page, "sort": "pushed"},
    )


async def search_user_repos(
    token: str, query: str, page: int = 1, per_page: int = 30
) -> dict:
    """Server-side repo search, so filtering happens before pagination.

    Filtering a single fetched page client-side makes "next page" unreliable:
    a page of 30 that filters down to 3 looks like the last page.
    """
    payload = await _request(
        "GET",
        GITHUB_API + "/search/repositories",
        token,
        what="search repositories",
        params={
            "q": query + " user:@me fork:true",
            "page": page,
            "per_page": per_page,
            "sort": "updated",
        },
    )
    return {"items": payload.get("items", []), "total": payload.get("total_count", 0)}


async def fetch_repo(token: str, full_name: str) -> dict:
    return await _request(
        "GET",
        GITHUB_API + "/repos/" + full_name,
        token,
        what="fetch repo " + full_name,
    )


async def count_open_prs(token: str, full_name: str) -> int | None:
    """Open PR count, or None when GitHub would not tell us.

    Returning None rather than 0 matters: the search endpoint has its own rate
    budget, and reporting "0 open PRs" for a rate-limited response is
    indistinguishable from a successful sync of a repo with no PRs.
    """
    try:
        payload = await _request(
            "GET",
            GITHUB_API + "/search/issues",
            token,
            what="count open PRs for " + full_name,
            params={"q": "repo:" + full_name + " is:pr is:open", "per_page": 1},
        )
    except GitHubError as exc:
        logger.warning("Could not count open PRs for %s: %s", full_name, exc)
        return None
    return payload.get("total_count")


async def list_pull_requests(
    token: str,
    full_name: str,
    state: str = "open",
    page: int = 1,
    per_page: int = 30,
) -> list[dict]:
    return await _request(
        "GET",
        GITHUB_API + "/repos/" + full_name + "/pulls",
        token,
        what="list pull requests for " + full_name,
        params={
            "state": state,
            "page": page,
            "per_page": per_page,
            "sort": "created",
            "direction": "desc",
        },
    )


# --------------------------------------------------------------------------
# Pull request detail - the inputs the review pipeline needs
# --------------------------------------------------------------------------

def _pr_path(full_name: str, pr_number: int) -> str:
    return GITHUB_API + "/repos/" + full_name + "/pulls/" + str(pr_number)


async def fetch_pull_request(token: str, full_name: str, pr_number: int) -> dict:
    return await _request(
        "GET",
        _pr_path(full_name, pr_number),
        token,
        what="fetch PR " + full_name + "#" + str(pr_number),
    )


async def fetch_pr_diff(token: str, full_name: str, pr_number: int) -> str:
    return await _request(
        "GET",
        _pr_path(full_name, pr_number),
        token,
        what="fetch diff for " + full_name + "#" + str(pr_number),
        accept="application/vnd.github.v3.diff",
        raw_text=True,
    )


async def fetch_pr_files(
    token: str, full_name: str, pr_number: int, max_pages: int = 4
) -> list[dict]:
    """Changed files with per-file patches and add/delete counts."""
    files: list[dict] = []
    for page in range(1, max_pages + 1):
        batch = await _request(
            "GET",
            _pr_path(full_name, pr_number) + "/files",
            token,
            what="fetch files for " + full_name + "#" + str(pr_number),
            params={"page": page, "per_page": 100},
        )
        files.extend(batch)
        if len(batch) < 100:
            break
    return files


async def fetch_mergeability(
    token: str, full_name: str, pr_number: int, attempts: int = 3
) -> dict:
    """PR metadata with `mergeable` resolved where possible.

    GitHub computes mergeability lazily and returns null while it works, so poll
    briefly instead of reporting "unknown" on the first try.
    """
    payload: dict = {}
    for attempt in range(attempts):
        payload = await fetch_pull_request(token, full_name, pr_number)
        if payload.get("mergeable") is not None:
            break
        if attempt < attempts - 1:
            await asyncio.sleep(1.5 * (attempt + 1))
    return payload


async def fetch_check_runs(token: str, full_name: str, ref: str) -> dict:
    """CI check runs for a commit. Degrades to empty rather than failing."""
    try:
        return await _request(
            "GET",
            GITHUB_API + "/repos/" + full_name + "/commits/" + ref + "/check-runs",
            token,
            what="fetch check runs for " + full_name,
            params={"per_page": 100},
        )
    except GitHubError as exc:
        logger.info("Check runs unavailable for %s: %s", full_name, exc)
        return {"total_count": 0, "check_runs": []}


async def fetch_combined_status(token: str, full_name: str, ref: str) -> dict:
    """Legacy commit statuses, for repos still using the Status API."""
    try:
        return await _request(
            "GET",
            GITHUB_API + "/repos/" + full_name + "/commits/" + ref + "/status",
            token,
            what="fetch commit status for " + full_name,
        )
    except GitHubError as exc:
        logger.info("Combined status unavailable for %s: %s", full_name, exc)
        return {"state": "unknown", "statuses": []}


async def compare_refs(token: str, full_name: str, base: str, head: str) -> dict:
    """base...head comparison. `behind_by` is how far the PR has drifted."""
    try:
        return await _request(
            "GET",
            GITHUB_API + "/repos/" + full_name + "/compare/" + base + "..." + head,
            token,
            what="compare refs in " + full_name,
            params={"per_page": 100},
        )
    except GitHubError as exc:
        logger.info("Compare unavailable for %s: %s", full_name, exc)
        return {}


# --------------------------------------------------------------------------
# Writing back
# --------------------------------------------------------------------------

async def create_pr_review(
    token: str,
    full_name: str,
    pr_number: int,
    body: str,
    event: str = "COMMENT",
) -> dict:
    """Post a review comment on a PR.

    `event` is COMMENT by design. APPROVE and REQUEST_CHANGES are human
    authorization acts: an APPROVE can satisfy a branch-protection rule, so an
    automated approval driven by attacker-controlled diff text becomes a way to
    merge unreviewed code. GitHub also rejects APPROVE and REQUEST_CHANGES on
    your own pull request with a 422, which is the common case here.
    """
    if event != "COMMENT":
        raise ValueError(
            "CodeArmor only posts COMMENT reviews; approving is a human decision."
        )
    return await _request(
        "POST",
        _pr_path(full_name, pr_number) + "/reviews",
        token,
        what="post review on " + full_name + "#" + str(pr_number),
        json_body={"body": body, "event": event},
    )
