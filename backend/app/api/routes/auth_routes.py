"""GitHub OAuth sign-in, session info, sign-out, and account switching."""
import datetime
import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.core.config import FRONTEND_URL
from app.core.logging import audit, logger
from app.core.timeutil import utcnow
from app.db.models import User
from app.github.client import GitHubError, fetch_github_user
from app.services.auth_service import (
    CSRF_COOKIE,
    STATE_COOKIE,
    clear_session_cookies,
    cookie_kwargs,
    create_state_token,
    get_current_user,
    get_user_github_token,
    require_csrf,
    revoke_all_sessions,
    set_session_cookie,
    verify_state_token,
)
from app.services.crypto_service import encrypt_token
from app.services.github_oauth_service import (
    ALLOWED_PROMPTS,
    build_authorize_url,
    exchange_code_for_token,
    oauth_configured,
    revoke_grant,
)

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_MAX_AGE_SECONDS = 600


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "-"


@router.get("/github/login")
def github_login(request: Request, prompt: str | None = Query(None)):
    if not oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="GitHub sign-in is not configured on this server.",
        )
    if prompt is not None and prompt not in ALLOWED_PROMPTS:
        raise HTTPException(status_code=422, detail="Unsupported prompt value")

    state = secrets.token_urlsafe(24)
    response = RedirectResponse(build_authorize_url(state, prompt=prompt))
    # CSRF protection for the redirect: a signed, short-lived state cookie that
    # the callback compares against the state GitHub echoes back.
    response.set_cookie(
        STATE_COOKIE,
        create_state_token(state),
        max_age=STATE_MAX_AGE_SECONDS,
        **cookie_kwargs(),
    )
    audit("auth.login_started", ip=_client_ip(request))
    return response


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str = Query(..., max_length=512),
    state: str = Query(..., max_length=512),
    oauth_state: str | None = Cookie(default=None, alias=STATE_COOKIE),
):
    if not oauth_state:
        audit("auth.callback_missing_state", ip=_client_ip(request))
        return RedirectResponse(FRONTEND_URL + "?auth_error=state")

    try:
        expected_state = verify_state_token(oauth_state)
    except HTTPException:
        audit("auth.callback_bad_state", ip=_client_ip(request))
        return RedirectResponse(FRONTEND_URL + "?auth_error=state")

    if not secrets.compare_digest(expected_state, state):
        audit("auth.callback_state_mismatch", ip=_client_ip(request))
        return RedirectResponse(FRONTEND_URL + "?auth_error=state")

    try:
        access_token = await exchange_code_for_token(code)
        gh_user = await fetch_github_user(access_token)
    except (GitHubError, RuntimeError) as exc:
        logger.error("GitHub OAuth failed: %s", exc)
        audit("auth.login_failed", ip=_client_ip(request))
        return RedirectResponse(FRONTEND_URL + "?auth_error=1")

    now = utcnow()
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
        user.updated_at = now
        user.save()

    response = RedirectResponse(FRONTEND_URL)
    attrs = cookie_kwargs()
    response.delete_cookie(
        STATE_COOKIE,
        path=attrs["path"],
        secure=attrs["secure"],
        samesite=attrs["samesite"],
        httponly=True,
    )
    set_session_cookie(response, user)

    audit(
        "auth.login_succeeded",
        user_id=user.id,
        login=user.login,
        new_account=created,
        ip=_client_ip(request),
    )
    return response


@router.get("/me")
def me(user: User = Depends(get_current_user), csrf_token: str | None = Cookie(default=None, alias=CSRF_COOKIE)):
    return {
        "id": user.id,
        "github_id": user.github_id,
        "login": user.login,
        "name": user.name,
        "avatar_url": user.avatar_url,
        # Echoed so a client that lost the readable cookie can still send the
        # header; it is not a secret, it only has to match the cookie.
        "csrf_token": csrf_token,
    }


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(response: Response, request: Request, user: User = Depends(get_current_user)):
    """Sign out everywhere.

    Bumping the session version invalidates every token issued to this user,
    so a copied cookie stops working instead of remaining valid until it
    expires.
    """
    revoke_all_sessions(user)
    clear_session_cookies(response)
    audit("auth.logout", user_id=user.id, login=user.login, ip=_client_ip(request))
    return {"ok": True}


@router.post("/switch", dependencies=[Depends(require_csrf)])
async def switch_account(
    response: Response, request: Request, user: User = Depends(get_current_user)
):
    """Sign out and revoke the GitHub grant, so the next login shows GitHub's
    authorize screen instead of silently reusing the same account."""
    revoked = False
    try:
        token = get_user_github_token(user)
        revoked = await revoke_grant(token)
    except HTTPException:
        # The stored token was already unusable; signing out is still correct.
        pass
    except Exception as exc:
        logger.warning("Failed to revoke GitHub grant for user %s: %s", user.id, exc)

    revoke_all_sessions(user)
    clear_session_cookies(response)
    audit(
        "auth.account_switched",
        user_id=user.id,
        login=user.login,
        grant_revoked=revoked,
        ip=_client_ip(request),
    )
    return {"ok": True, "revoked": revoked}


@router.delete("/account", dependencies=[Depends(require_csrf)])
async def delete_account(
    response: Response, request: Request, user: User = Depends(get_current_user)
):
    """Delete the account: revoke CodeArmor's GitHub access and erase all rows.

    Connected repositories, sync jobs and stored reviews cascade from the user
    row, so this leaves nothing behind.
    """
    user_id, login = user.id, user.login

    try:
        token = get_user_github_token(user)
        await revoke_grant(token)
    except HTTPException:
        pass
    except Exception as exc:
        logger.warning("Grant revocation during account deletion failed: %s", exc)

    user.delete_instance(recursive=True)
    clear_session_cookies(response)
    audit("auth.account_deleted", user_id=user_id, login=login, ip=_client_ip(request))
    return {"ok": True}
