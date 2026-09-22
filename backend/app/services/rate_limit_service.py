"""Per-user rate limiting for the endpoints that spend money.

A review is six LLM calls; the chat endpoint is one per message. Without a
limit, a single account (or a single loop in a browser tab) can run up an
unbounded OpenRouter bill.

This is an in-process sliding window: correct for a single instance, and
approximate once you scale to several. When you add a second instance, move the
counters to Render Key Value / Redis - the interface here is deliberately small
enough that only the two module-level functions change.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.core.config import CHAT_RATE_LIMIT_PER_HOUR, REVIEW_RATE_LIMIT_PER_HOUR
from app.core.logging import audit

_WINDOW_SECONDS = 3600

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)

_LIMITS = {
    "review": REVIEW_RATE_LIMIT_PER_HOUR,
    "chat": CHAT_RATE_LIMIT_PER_HOUR,
}


def _prune(timestamps: deque[float], now: float) -> None:
    cutoff = now - _WINDOW_SECONDS
    while timestamps and timestamps[0] < cutoff:
        timestamps.popleft()


def check_rate_limit(action: str, user_id: int) -> None:
    """Record one use of `action` by `user_id`, or raise 429."""
    limit = _LIMITS.get(action)
    if not limit or limit <= 0:
        return

    key = f"{action}:{user_id}"
    now = time.monotonic()

    with _lock:
        timestamps = _hits[key]
        _prune(timestamps, now)
        if len(timestamps) >= limit:
            retry_after = int(_WINDOW_SECONDS - (now - timestamps[0])) + 1
            audit("ratelimit.exceeded", action=action, user_id=user_id)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit reached: {limit} {action} requests per hour. "
                    f"Try again in about {max(1, retry_after // 60)} minute(s)."
                ),
                headers={"Retry-After": str(retry_after)},
            )
        timestamps.append(now)


def remaining(action: str, user_id: int) -> int:
    limit = _LIMITS.get(action, 0)
    if limit <= 0:
        return 0
    with _lock:
        timestamps = _hits[f"{action}:{user_id}"]
        _prune(timestamps, time.monotonic())
        return max(0, limit - len(timestamps))


def reset() -> None:
    """Clear all counters. For tests."""
    with _lock:
        _hits.clear()
