"""Session management, CSRF, and the helper that turns a User into a token.

Sessions are JWTs in an httpOnly cookie, but the JWT is not the whole truth:
it carries the `sv` (session version) the user had when it was minted, and
`get_current_user` rejects any token whose `sv` is stale. Bumping
`User.session_version` therefore invalidates every cookie ever issued to that
user, which is what makes "sign out" revoke a copied session rather than just
clearing one browser.
"""
import datetime
import secrets

import jwt
from fastapi import Cookie, Header, HTTPException, Request, Response

from app.core.config import (
    ALLOWED_ORIGINS,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    SESSION_SECRET,
    SESSION_TTL_HOURS,
)
from app.core.timeutil import utcnow
from app.core.logging import audit, logger
from app.db.models import User
from app.services.crypto_service import TokenDecryptionError, decrypt_token

SESSION_COOKIE = "session"
STATE_COOKIE = "oauth_state"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "codearmor-api"
JWT_AUDIENCE = "codearmor-web"

STATE_TTL_MINUTES = 10


def cookie_kwargs(http_only: bool = True) -> dict:
    """Attributes every cookie this app sets must share.

    A cross-site deployment (Vercel frontend, Render backend) only gets its
    cookie back on fetch/XHR when it is SameSite=None *and* Secure; browsers
    silently drop a SameSite=None cookie that is not Secure. Same-host local
    development over plain HTTP cannot use Secure, so it uses Lax.

    `domain` is deliberately never set: onrender.com and vercel.app are on the
    Public Suffix List, and a host-only cookie is what we want anyway.
    """
    return {
        "httponly": http_only,
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        "path": "/",
    }


# --------------------------------------------------------------------------
# Session tokens
# --------------------------------------------------------------------------

def create_session_token(user: User) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "sv": user.session_version,
        "login": user.login,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + datetime.timedelta(hours=SESSION_TTL_HOURS),
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm=JWT_ALGORITHM)


def _decode_session(token: str) -> dict:
    return jwt.decode(
        token,
        SESSION_SECRET,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        options={"require": ["exp", "iat", "sub", "sv"]},
    )


def _resolve_user(token: str) -> User | None:
    try:
        payload = _decode_session(token)
    except jwt.PyJWTError:
        return None

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None

    user = User.get_or_none(User.id == user_id)
    if user is None:
        return None

    # A stale session version means the session was revoked server-side.
    if payload.get("sv") != user.session_version:
        audit("auth.session_revoked_token_used", user_id=user.id)
        return None

    return user


def set_session_cookie(response: Response, user: User) -> str:
    """Set the session cookie and a matching CSRF cookie. Returns the CSRF token."""
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user),
        max_age=SESSION_TTL_HOURS * 3600,
        **cookie_kwargs(),
    )
    csrf_token = secrets.token_urlsafe(32)
    # Readable by JavaScript on purpose: the browser echoes it back in a header
    # that a cross-site attacker cannot set (double-submit pattern).
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=SESSION_TTL_HOURS * 3600,
        **cookie_kwargs(http_only=False),
    )
    return csrf_token


def clear_session_cookies(response: Response) -> None:
    """Delete the cookies with the same attributes they were set with.

    A delete_cookie whose attributes do not match is ignored by the browser,
    which is how "sign out" ends up leaving the user signed in.
    """
    attrs = cookie_kwargs()
    response.delete_cookie(SESSION_COOKIE, path=attrs["path"], secure=attrs["secure"], samesite=attrs["samesite"], httponly=True)
    response.delete_cookie(CSRF_COOKIE, path=attrs["path"], secure=attrs["secure"], samesite=attrs["samesite"], httponly=False)


def revoke_all_sessions(user: User) -> None:
    """Invalidate every session token previously issued to this user."""
    user.session_version = (user.session_version or 1) + 1
    user.updated_at = utcnow()
    user.save()
    audit("auth.sessions_revoked", user_id=user.id, login=user.login)


# --------------------------------------------------------------------------
# OAuth state (CSRF for the authorization redirect)
# --------------------------------------------------------------------------

def create_state_token(state: str) -> str:
    now = utcnow()
    return jwt.encode(
        {
            "state": state,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "iat": now,
            "exp": now + datetime.timedelta(minutes=STATE_TTL_MINUTES),
        },
        SESSION_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def verify_state_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            SESSION_SECRET,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["exp", "state"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired sign-in request")
    return str(payload["state"])


# --------------------------------------------------------------------------
# FastAPI dependencies
# --------------------------------------------------------------------------

def get_current_user(session: str | None = Cookie(default=None)) -> User:
    """Resolve the session cookie to a User, or raise 401."""
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = _resolve_user(session)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user


def require_csrf(
    request: Request,
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
    csrf_token: str | None = Cookie(default=None, alias=CSRF_COOKIE),
) -> None:
    """Double-submit CSRF check for every state-changing request.

    Needed precisely because the session cookie is SameSite=None in a
    cross-site deployment: SameSite is no longer doing this job.
    """
    if not session:
        # No session, nothing to forge. Defer to get_current_user so the client
        # gets a 401 it can act on rather than a confusing 403.
        return

    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        audit("auth.csrf_origin_rejected", origin=origin, path=request.url.path)
        raise HTTPException(status_code=403, detail="Origin not allowed")

    if not x_csrf_token or not csrf_token:
        raise HTTPException(status_code=403, detail="CSRF token missing")
    if not secrets.compare_digest(x_csrf_token, csrf_token):
        audit("auth.csrf_mismatch", path=request.url.path)
        raise HTTPException(status_code=403, detail="CSRF token invalid")


def get_user_github_token(user: User) -> str:
    """Decrypt the user's GitHub token, or ask them to sign in again.

    Without this, a rotated encryption key turns every authenticated request
    into an unhandled InvalidToken and a 500.
    """
    try:
        return decrypt_token(user.access_token_encrypted)
    except TokenDecryptionError:
        logger.warning("Stored GitHub token for user %s is undecryptable", user.id)
        audit("auth.token_undecryptable", user_id=user.id)
        raise HTTPException(
            status_code=401,
            detail="Your GitHub authorization needs to be renewed. Please sign in again.",
        )
