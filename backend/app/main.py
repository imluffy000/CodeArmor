"""FastAPI application setup."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.auth_routes import router as auth_router
from app.api.routes.health_routes import router as health_router
from app.api.routes.home_routes import router as home_router
from app.api.routes.ops_routes import router as ops_router
from app.api.routes.repo_routes import router as repo_router
from app.api.routes.review_routes import router as review_router
from app.core.config import ALLOWED_ORIGINS, ENVIRONMENT, validate_config
from app.core.logging import logger, new_request_id, request_id_var
from app.db.database import close_db, init_db
from app.github.client import GitHubError
from app.services.auth_service import CSRF_HEADER
from app.services.sync_service import cancel_running_tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Raises on an unsafe production configuration - a service that boots wide
    # open is worse than one that refuses to start.
    for warning in validate_config():
        logger.warning("config: %s", warning)

    init_db()
    logger.info("CodeArmor API started in %s mode", ENVIRONMENT)
    try:
        yield
    finally:
        await cancel_running_tasks()
        close_db()


app = FastAPI(
    title="CodeArmor",
    version="2.0.0",
    description="Multi-agent AI pull request review with a merge-readiness gate",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Give every request an id, echoed in the response and in every log line."""
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


# Exact origins only. With allow_credentials=True a wildcard makes every site on
# the internet a trusted origin for cookie-bearing requests, and Starlette will
# reflect whatever Origin it is sent.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", CSRF_HEADER, "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)


@app.exception_handler(GitHubError)
async def github_error_handler(request: Request, exc: GitHubError):
    """One place that maps GitHub failures to a status code and a safe message.

    The old code raised with `response.text` embedded, which echoed GitHub's
    body - including private repository names and the token owner's user id -
    straight back to the caller.
    """
    logger.warning("GitHub error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.safe_message})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Never return a raw exception string: it leaks paths, config and upstream bodies."""
    request_id = request_id_var.get()
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Something went wrong on our side.",
            "request_id": request_id,
        },
    )


app.include_router(home_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(repo_router)
app.include_router(review_router)
app.include_router(ops_router)
