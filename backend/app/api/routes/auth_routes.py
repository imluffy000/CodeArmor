"""GitHub OAuth sign-in, session info, and logout."""
import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Cookie, Response
from fastapi.responses import RedirectResponse

from app.core.config import FRONTEND_URL
from app.core.logging import logger
from app.db.models import User
from app.services.auth_service import (
    SESSION_COOKIE,
    STATE_COOKIE,
    create_session_token,
    create_state_token,
    get_current_user,
    verify_state_token,
)
from app.services.crypto_service import decrypt_token, encrypt_token
from app.services.github_oauth_service import (
    build_authorize_url,
    exchange_code_for_token,
    fetch_github_user,
    oauth_configured,
    revoke_grant,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github/login")
def github_login(prompt: str | None = Query(None)):
    if not oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in backend/.env",
        )
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(build_authorize_url(state, prompt=prompt))
    # CSRF protection: signed state in a short-lived cookie, verified in callback
    response.set_cookie(
        STATE_COOKIE,
        create_state_token(state),
        max_age=600,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/github/callback")
async def github_callback(
    code: str = Query(...),
    state: str = Query(...),
    oauth_state: str | None = Cookie(default=None),
):
    if not oauth_state or verify_state_token(oauth_state) != state:
        raise HTTPException(status_code=400, detail="OAuth state mismatch")

    try:
        access_token = await exchange_code_for_token(code)
        gh_user = await fetch_github_user(access_token)
    except Exception as exc:
        logger.error("GitHub OAuth failed: %s", exc)
        return RedirectResponse(f"{FRONTEND_URL}?auth_error=1")

    user, created = User.get_or_create(
        github_id=gh_user["id"],
        defaults={
            "login": gh_user["login"],
            "name": gh_user.get("name"),
            "avatar_url": gh_user.get("avatar_url"),
            "access_token_encrypted": encrypt_token(access_token),
        },
    )
    if not created:
        user.login = gh_user["login"]
        user.name = gh_user.get("name")
        user.avatar_url = gh_user.get("avatar_url")
        user.access_token_encrypted = encrypt_token(access_token)
        user.updated_at = datetime.datetime.utcnow()
        user.save()

    logger.info("User %s signed in via GitHub OAuth", user.login)

    response = RedirectResponse(FRONTEND_URL)
    response.delete_cookie(STATE_COOKIE)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user),
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "github_id": user.github_id,
        "login": user.login,
        "name": user.name,
        "avatar_url": user.avatar_url,
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.post("/switch")
async def switch_account(response: Response, user: User = Depends(get_current_user)):
    """Sign out AND revoke the GitHub OAuth grant, so the next login shows
    GitHub's authorize screen instead of silently reusing the same account."""
    revoked = False
    try:
        token = decrypt_token(user.access_token_encrypted)
        revoked = await revoke_grant(token)
    except Exception as exc:
        logger.warning("Failed to revoke GitHub grant for %s: %s", user.login, exc)

    response.delete_cookie(SESSION_COOKIE)
    logger.info("User %s switched account (grant revoked: %s)", user.login, revoked)
    return {"ok": True, "revoked": revoked}
