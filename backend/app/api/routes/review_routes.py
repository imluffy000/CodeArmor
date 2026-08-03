from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict
from sse_starlette.sse import EventSourceResponse

from app.core.logging import logger
from app.db.models import User
from app.models.request_models import ReviewRequest
from app.models.response_models import ReviewResponse
from app.services.auth_service import get_optional_user
from app.services.crypto_service import decrypt_token
from app.services.review_service import run_pr_review, stream_pr_review
from app.services.llm_service import review_chat

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    history: List[Dict] = []
    issues: List[Dict] = []


@router.post("/review", response_model=ReviewResponse)
async def review_pr(
    data: ReviewRequest,
    user: User | None = Depends(get_optional_user),
):
    try:
        token = None
        if user and user.access_token_encrypted:
            token = decrypt_token(user.access_token_encrypted)
        return await run_pr_review(data.pr_url, token=token)
    except Exception as e:
        logger.exception("PR review failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/review/stream")
async def review_pr_stream(
    pr_url: str,
    user: User | None = Depends(get_optional_user),
):
    token = None
    if user and user.access_token_encrypted:
        token = decrypt_token(user.access_token_encrypted)

    async def event_generator():
        try:
            async for event in stream_pr_review(pr_url, token=token):
                yield event
        except Exception as e:
            logger.exception("PR review stream failed")
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


@router.post("/review/chat")
async def chat_about_review(data: ChatRequest):
    try:
        reply = await review_chat(
            message=data.message,
            history=data.history,
            issues=data.issues,
        )
        return {"response": reply}
    except Exception as e:
        logger.exception("Review chat failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


