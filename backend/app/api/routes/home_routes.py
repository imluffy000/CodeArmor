from fastapi import APIRouter

from app.core.config import ENVIRONMENT

router = APIRouter(tags=["meta"])


@router.get("/")
async def home():
    """Service metadata. Deliberately lists no secrets and no user data."""
    return {
        "service": "CodeArmor",
        "status": "running",
        "version": "2.0.0",
        "environment": ENVIRONMENT,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
    }
