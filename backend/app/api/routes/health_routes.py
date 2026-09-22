from fastapi import APIRouter, Response

from app.core.config import ENVIRONMENT, validate_config
from app.db.database import db

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health():
    """Liveness. Static on purpose.

    The platform restarts the instance when this fails, so it must not depend
    on the database: a transient outage would otherwise become a restart loop.
    Use /readyz for dependency checks.
    """
    return {"status": "healthy", "service": "CodeArmor", "version": "2.0.0"}


@router.get("/readyz")
async def readiness(response: Response):
    """Readiness: is the configuration valid and the database reachable?

    For debugging and for deploy gates, not for the platform health check.
    """
    checks = {"config": "ok", "database": "ok"}

    try:
        validate_config()
    except Exception as exc:
        checks["config"] = f"invalid: {exc}"

    try:
        db.execute_sql("SELECT 1")
    except Exception:
        checks["database"] = "unreachable"

    ready = all(value == "ok" for value in checks.values())
    if not ready:
        response.status_code = 503
    return {"ready": ready, "environment": ENVIRONMENT, "checks": checks}
