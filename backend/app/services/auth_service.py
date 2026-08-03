"""Session management: JWT stored in an httpOnly cookie."""
import datetime

import jwt
from fastapi import Cookie, HTTPException

from app.core.config import SESSION_SECRET
from app.db.models import User

SESSION_COOKIE = "session"
STATE_COOKIE = "oauth_state"
JWT_ALGORITHM = "HS256"
SESSION_TTL_HOURS = 24 * 7


def create_session_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "github_id": user.github_id,
        "login": user.login,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=SESSION_TTL_HOURS),
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm=JWT_ALGORITHM)


def create_state_token(state: str) -> str:
    payload = {
        "state": state,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm=JWT_ALGORITHM)


def verify_state_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=[JWT_ALGORITHM])
        return payload["state"]
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")


def get_current_user(session: str | None = Cookie(default=None)) -> User:
    """FastAPI dependency: resolve the session cookie to a User or raise 401."""
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(session, SESSION_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    user = User.get_or_none(User.id == int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_optional_user(session: str | None = Cookie(default=None)) -> User | None:
    """FastAPI dependency: resolve the session cookie to a User or return None if unauthenticated."""
    if not session:
        return None
    try:
        payload = jwt.decode(session, SESSION_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

    return User.get_or_none(User.id == int(payload["sub"]))

