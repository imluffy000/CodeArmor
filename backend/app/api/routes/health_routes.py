from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():

    return {

        "status": "healthy",

        "service": "AI PR Reviewer",

        "version": "1.0.0"
    }