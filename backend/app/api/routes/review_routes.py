"""Review endpoints.

Every route here requires a signed-in user and a repository that user has
connected. Two properties follow from that, and both were previously missing:

* No anonymous access. These endpoints spend the operator's LLM budget and, in
  the old code, fell back to a server-wide GitHub token - which let an
  unauthenticated caller read any private diff that token could reach and post a
  review under the operator's identity.
* No attacker-chosen repository. The pull request is addressed by `repo_id` and
  `pr_number`, and the server builds the GitHub URL from a row the caller owns.
  That also keeps private repository names out of access logs.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.core.logging import audit, logger
from app.db.models import Repository, Review, User
from app.models.request_models import ChatRequest, PostReviewRequest, ReviewRequest
from app.models.response_models import ReviewResponse, ReviewSummaryItem
from app.services.auth_service import (
    get_current_user,
    get_user_github_token,
    require_csrf,
)
from app.services.llm_service import review_chat
from app.services.rate_limit_service import check_rate_limit, remaining
from app.services.review_service import (
    post_review_to_github,
    review_payload,
    run_review,
    stream_review,
)
from app.utils.openrouter_client import LLMNotConfigured

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _owned_repo(user: User, repo_id: int) -> Repository:
    repo = Repository.get_or_none((Repository.id == repo_id) & (Repository.user == user))
    if repo is None:
        # 404 rather than 403: whether a repository id exists is not the
        # caller's business.
        raise HTTPException(status_code=404, detail="Repository not connected")
    return repo


def _owned_review(user: User, review_id: int) -> Review:
    review = Review.get_or_none((Review.id == review_id) & (Review.user == user))
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@router.post("", response_model=ReviewResponse, dependencies=[Depends(require_csrf)])
async def create_review(data: ReviewRequest, user: User = Depends(get_current_user)):
    """Run a review and return the finished report."""
    repo = _owned_repo(user, data.repo_id)
    check_rate_limit("review", user.id)
    token = get_user_github_token(user)

    audit("review.started", user_id=user.id, repo_id=repo.id, pr_number=data.pr_number)

    try:
        payload = await run_review(user, repo, data.pr_number, token)
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        # stream_review has already logged the detail; the message it raises is
        # the client-safe one.
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        logger.exception("Review failed for repo %s PR %s", repo.id, data.pr_number)
        raise HTTPException(status_code=500, detail="The review failed. Please try again.")

    if data.post_to_github and payload.get("review_id"):
        review = _owned_review(user, payload["review_id"])
        result = await post_review_to_github(review, token)
        payload["posted_to_github"] = result["posted"]
        payload["github_error"] = result["error"]

    return payload


@router.get("/stream")
async def stream_review_endpoint(
    request: Request,
    repo_id: int = Query(..., ge=1),
    pr_number: int = Query(..., ge=1),
    refresh: bool = Query(False),
    user: User = Depends(get_current_user),
):
    """Run a review, streaming per-agent progress over SSE.

    This route is read-only by design. It never posts to GitHub: a GET that
    writes to someone's repository is a one-click CSRF, and EventSource cannot
    send a CSRF header. Publishing is a separate POST.
    """
    repo = _owned_repo(user, repo_id)
    check_rate_limit("review", user.id)
    token = get_user_github_token(user)

    audit("review.started", user_id=user.id, repo_id=repo.id, pr_number=pr_number)

    async def event_generator():
        try:
            async for event in stream_review(
                user, repo, pr_number, token, use_cache=not refresh
            ):
                if await request.is_disconnected():
                    logger.info(
                        "Client disconnected; abandoning review of repo %s PR %s",
                        repo.id,
                        pr_number,
                    )
                    return
                yield event
        except LLMNotConfigured as exc:
            yield {"event": "error", "data": str(exc)}
        except Exception:
            logger.exception("Review stream failed for repo %s PR %s", repo.id, pr_number)
            yield {"event": "error", "data": "The review failed. Please try again."}

    return EventSourceResponse(
        event_generator(),
        headers={
            # Render's router buffers by default, which would hold every event
            # until the stream closed.
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-transform",
        },
    )


@router.get("", response_model=list[ReviewSummaryItem])
def list_reviews(
    repo_id: int | None = Query(None, ge=1),
    pr_number: int | None = Query(None, ge=1),
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """Review history, newest first - so a result survives closing the tab."""
    query = Review.select().where(Review.user == user)
    if repo_id:
        repo = _owned_repo(user, repo_id)
        query = query.where(Review.repo_full_name == repo.full_name)
    if pr_number:
        query = query.where(Review.pr_number == pr_number)

    items = []
    for review in query.order_by(Review.created_at.desc()).limit(limit):
        payload = review.data
        items.append(
            {
                "review_id": review.id,
                "repo_full_name": review.repo_full_name,
                "pr_number": review.pr_number,
                "pr_title": review.pr_title,
                "head_sha": review.head_sha,
                "total_issues": review.total_issues,
                "critical_issues": review.critical_issues,
                "score": (payload.get("stats") or {}).get("score"),
                "verdict": (payload.get("merge_readiness") or {}).get("verdict"),
                "posted_to_github": review.posted_to_github,
                "created_at": review.created_at.isoformat() if review.created_at else "",
            }
        )
    return items


@router.get("/{review_id}", response_model=ReviewResponse)
def get_review(review_id: int, user: User = Depends(get_current_user)):
    return review_payload(_owned_review(user, review_id), cached=True)


@router.post("/{review_id}/publish", dependencies=[Depends(require_csrf)])
async def publish_review(
    review_id: int,
    body: PostReviewRequest | None = None,
    user: User = Depends(get_current_user),
):
    """Post a completed review to the pull request as a comment.

    Separate from running the review because it writes to the user's repository
    under their GitHub identity - an irreversible, outward-facing action that
    should be a deliberate click, not a side effect.
    """
    review = _owned_review(user, review_id)
    token = get_user_github_token(user)
    result = await post_review_to_github(review, token)
    if not result["posted"]:
        raise HTTPException(status_code=502, detail=result["error"])
    return {"ok": True, "posted_to_github": True}


@router.delete("/{review_id}", dependencies=[Depends(require_csrf)])
def delete_review(review_id: int, user: User = Depends(get_current_user)):
    review = _owned_review(user, review_id)
    review.delete_instance()
    audit("review.deleted", user_id=user.id, review_id=review_id)
    return {"ok": True}


@router.post("/chat", dependencies=[Depends(require_csrf)])
async def chat_about_review(data: ChatRequest, user: User = Depends(get_current_user)):
    """Ask a question about one of your stored reviews.

    The findings are read from the stored review, not from the request body. An
    endpoint that interpolates client-supplied text into the system prompt is an
    LLM with an attacker-writable persona, on the operator's API key.
    """
    review = _owned_review(user, data.review_id)
    check_rate_limit("chat", user.id)

    payload = review.data
    findings = payload.get("issues") or []

    try:
        reply = await review_chat(
            message=data.message, history=data.history, findings=findings
        )
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        logger.exception("Review chat failed for review %s", data.review_id)
        raise HTTPException(status_code=502, detail="The assistant could not answer. Try again.")

    return {
        "response": reply,
        "remaining_messages_this_hour": remaining("chat", user.id),
    }
