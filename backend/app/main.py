from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth_routes import router as auth_router
from app.api.routes.health_routes import router as health_router
from app.api.routes.home_routes import router as home_router
from app.api.routes.repo_routes import router as repo_router
from app.api.routes.review_routes import router as review_router
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI PR Reviewer",
    version="1.0.0",
    description="Multi-agent AI pull request reviewer",
    lifespan=lifespan,
)

# Allow frontend dev server access (Vite default port). In production, lock this down.
# Both hostnames listed, but the app redirects users to 127.0.0.1 so session
# cookies (SameSite=lax, host 127.0.0.1) are sent with API calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(home_router)
app.include_router(health_router)
app.include_router(review_router)
app.include_router(auth_router)
app.include_router(repo_router)
