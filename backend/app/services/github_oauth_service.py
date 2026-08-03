"""GitHub OAuth flow + per-user GitHub API helpers (async, via httpx)."""
from urllib.parse import urlencode

import httpx

from app.core.config import BACKEND_URL, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"

OAUTH_SCOPES = "repo read:user"


def oauth_configured() -> bool:
    return bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)


def build_authorize_url(state: str, prompt: str | None = None) -> str:
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": f"{BACKEND_URL}/auth/github/callback",
        "scope": OAUTH_SCOPES,
        "state": state,
    }
    if prompt:
        params["prompt"] = prompt
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": f"{BACKEND_URL}/auth/github/callback",
            },
            headers={"Accept": "application/json"},
        )
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"GitHub token exchange failed: {data.get('error_description') or data}")
    return token


async def revoke_grant(token: str) -> bool:
    """Revoke the user's OAuth grant so the next login shows GitHub's
    authorize screen again (lets the user pick a different account)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            "DELETE",
            f"{GITHUB_API}/applications/{GITHUB_CLIENT_ID}/grant",
            auth=(GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET),
            headers={"Accept": "application/vnd.github+json"},
            json={"access_token": token},
        )
    # 204 = revoked, 404 = grant already gone — both mean the goal is met
    return resp.status_code in (204, 404)


def _user_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


async def fetch_github_user(token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GITHUB_API}/user", headers=_user_headers(token))
    resp.raise_for_status()
    return resp.json()


async def list_user_repos(token: str, page: int = 1, per_page: int = 30) -> list[dict]:
    """Repos the authenticated user can access, most recently pushed first."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/user/repos",
            headers=_user_headers(token),
            params={"page": page, "per_page": per_page, "sort": "pushed"},
        )
    resp.raise_for_status()
    return resp.json()


async def fetch_repo(token: str, full_name: str) -> dict:
    """Fetch a single repo; raises httpx.HTTPStatusError (404) if inaccessible."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GITHUB_API}/repos/{full_name}", headers=_user_headers(token))
    resp.raise_for_status()
    return resp.json()


async def count_open_prs(token: str, full_name: str) -> int:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/search/issues",
            headers=_user_headers(token),
            params={"q": f"repo:{full_name} is:pr is:open", "per_page": 1},
        )
    if resp.status_code != 200:
        return 0
    return resp.json().get("total_count", 0)


async def list_pull_requests(token: str, full_name: str, state: str = "open", page: int = 1, per_page: int = 30) -> list[dict]:
    """List pull requests for a repo, newest first."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{full_name}/pulls",
            headers=_user_headers(token),
            params={"state": state, "page": page, "per_page": per_page, "sort": "created", "direction": "desc"},
        )
    resp.raise_for_status()
    return resp.json()
