"""The GitHub OAuth authorization-code flow.

Only the flow lives here. Everything that calls the GitHub API on a user's
behalf lives in app/github/client.py, so there is one transport and one auth
model rather than two parallel clients.
"""
from urllib.parse import urlencode

import httpx

from app.core.config import BACKEND_URL, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET
from app.core.logging import logger
from app.github.client import (
    GITHUB_API,
    GITHUB_AUTHORIZE_URL,
    GITHUB_TOKEN_URL,
    DEFAULT_TIMEOUT,
)

# `repo` is broad - read *and write* on every repository the user can reach.
# It is the only classic OAuth scope that can list and diff private
# repositories, which the product requires, and `repo` is also what lets
# CodeArmor post its review comment back.
#
# If you only ever review public repositories, set
# GITHUB_OAUTH_SCOPES="read:user public_repo" and the grant shrinks
# accordingly. The durable fix is a GitHub App with per-repository
# installation and granular permissions (Contents: read, Pull requests:
# write) plus short-lived installation tokens instead of a long-lived user
# token at rest - see the README roadmap.
import os

OAUTH_SCOPES = os.getenv("GITHUB_OAUTH_SCOPES", "read:user repo")

# GitHub's authorize endpoint accepts a `prompt` parameter; allowlist it rather
# than reflecting whatever arrives in the query string into an outbound URL.
ALLOWED_PROMPTS = {"select_account", "consent", "login", "none"}


def oauth_configured() -> bool:
    return bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)


def callback_url() -> str:
    return BACKEND_URL + "/auth/github/callback"


def build_authorize_url(state: str, prompt: str | None = None) -> str:
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": callback_url(),
        "scope": OAUTH_SCOPES,
        "state": state,
    }
    if prompt:
        if prompt not in ALLOWED_PROMPTS:
            raise ValueError("Unsupported prompt value")
        params["prompt"] = prompt
    return GITHUB_AUTHORIZE_URL + "?" + urlencode(params)


async def exchange_code_for_token(code: str) -> str:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": callback_url(),
            },
            headers={"Accept": "application/json"},
        )

    payload = response.json()
    token = payload.get("access_token")
    if not token:
        # Log the error code, not the payload: it can echo the request.
        logger.error(
            "GitHub token exchange failed: %s", payload.get("error", "unknown_error")
        )
        raise RuntimeError("GitHub token exchange failed")
    return token


async def revoke_grant(token: str) -> bool:
    """Revoke the user's OAuth grant.

    Used by "switch account" so GitHub shows the authorize screen again instead
    of silently reusing the signed-in account, and on request as a way for a
    user to withdraw CodeArmor's access to their repositories entirely.
    """
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.request(
            "DELETE",
            GITHUB_API + "/applications/" + str(GITHUB_CLIENT_ID) + "/grant",
            auth=(GITHUB_CLIENT_ID or "", GITHUB_CLIENT_SECRET or ""),
            headers={"Accept": "application/vnd.github+json"},
            json={"access_token": token},
        )
    # 204 = revoked, 404 = already gone. Both mean the goal is met.
    return response.status_code in (204, 404)
