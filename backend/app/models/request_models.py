"""Request bodies.

A review is addressed by `repo_id` + `pr_number`, not by a free-text URL. The
server builds the GitHub URL from a repository row the caller owns, so an
attacker-supplied repository path never reaches the GitHub API - and the private
repository name never lands in an access log via a query string.
"""
from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    repo_id: int = Field(ge=1)
    pr_number: int = Field(ge=1)
    # Posting writes to the user's repository under their GitHub identity, so it
    # is an explicit per-request choice and defaults to off.
    post_to_github: bool = False


class PostReviewRequest(BaseModel):
    """Publish an already-completed review to the pull request."""

    review_id: int = Field(ge=1)


class ChatRequest(BaseModel):
    """Ask about a stored review.

    The findings are loaded server-side from `review_id`. Accepting them in the
    request body would let a caller write the assistant's own context.
    """

    review_id: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict] = Field(default_factory=list, max_length=40)
