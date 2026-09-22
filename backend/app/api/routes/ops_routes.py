"""Operational visibility: per-review traces and rolled-up usage.

Scoped to the signed-in user throughout. These endpoints report on your own
reviews, not on the deployment - a cost figure across all tenants is an
operator concern and does not belong behind a user session.
"""
import datetime
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from peewee import fn

from app.core.config import LLM_MODEL, REVIEW_COST_CEILING_USD
from app.core.timeutil import iso_utc, utcnow
from app.db.models import AgentRun, Review, User
from app.services.auth_service import get_current_user
from app.services.rate_limit_service import remaining
from app.utils.helpers import PROMPT_VERSION

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/reviews/{review_id}/trace")
def review_trace(review_id: int, user: User = Depends(get_current_user)):
    """The full trace for one review: a span per agent, with cost and latency.

    This is what makes a wrong finding attributable after the fact. Without it,
    "the security agent missed this" is unanswerable.
    """
    review = Review.get_or_none((Review.id == review_id) & (Review.user == user))
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    trace = json.loads(review.trace) if review.trace else None
    runs = [
        {
            "agent": run.agent,
            "status": run.status,
            "model": run.model,
            "duration_ms": run.duration_ms,
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
            "cost_usd": run.cost_usd,
            "findings": run.findings,
            "dropped": run.dropped,
            "parse_status": run.parse_status,
            "error": run.error,
        }
        for run in review.agent_runs.order_by(AgentRun.id)
    ]

    return {
        "review_id": review.id,
        "trace_id": review.trace_id,
        "repo_full_name": review.repo_full_name,
        "pr_number": review.pr_number,
        "head_sha": review.head_sha,
        "model": review.model,
        # A findings change is attributable to a prompt edit rather than to
        # model drift only if you recorded which prompts ran.
        "prompt_version": review.prompt_version,
        "duration_ms": review.duration_ms,
        "tokens_in": review.tokens_in,
        "tokens_out": review.tokens_out,
        "cost_usd": review.cost_usd,
        "created_at": iso_utc(review.created_at),
        "agents": runs,
        "trace": trace,
    }


@router.get("/usage")
def usage(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
):
    """What your reviews have cost, and which agents are misbehaving."""
    since = utcnow() - datetime.timedelta(days=days)

    totals = (
        Review.select(
            fn.COUNT(Review.id).alias("reviews"),
            fn.COALESCE(fn.SUM(Review.cost_usd), 0.0).alias("cost_usd"),
            fn.COALESCE(fn.SUM(Review.tokens_in), 0).alias("tokens_in"),
            fn.COALESCE(fn.SUM(Review.tokens_out), 0).alias("tokens_out"),
            fn.COALESCE(fn.AVG(Review.duration_ms), 0).alias("avg_duration_ms"),
        )
        .where((Review.user == user) & (Review.created_at >= since))
        .dicts()
        .get()
    )

    per_agent = (
        AgentRun.select(
            AgentRun.agent,
            fn.COUNT(AgentRun.id).alias("runs"),
            fn.COALESCE(fn.SUM(AgentRun.cost_usd), 0.0).alias("cost_usd"),
            fn.COALESCE(fn.AVG(AgentRun.duration_ms), 0).alias("avg_duration_ms"),
            fn.COALESCE(fn.SUM(AgentRun.findings), 0).alias("findings"),
            fn.COALESCE(fn.SUM(AgentRun.dropped), 0).alias("dropped"),
            fn.SUM(
                # A failure rate per agent is the signal that a model or a
                # prompt has started going wrong.
                AgentRun.status.not_in(["ok"]).cast("integer")
            ).alias("failures"),
        )
        .join(Review)
        .where((Review.user == user) & (Review.created_at >= since))
        .group_by(AgentRun.agent)
        .order_by(AgentRun.agent)
        .dicts()
    )

    agents = []
    for row in per_agent:
        runs = row["runs"] or 0
        produced = (row["findings"] or 0) + (row["dropped"] or 0)
        agents.append(
            {
                **row,
                "avg_duration_ms": int(row["avg_duration_ms"] or 0),
                "cost_usd": round(row["cost_usd"] or 0.0, 6),
                "failures": int(row["failures"] or 0),
                "failure_rate": round((row["failures"] or 0) / runs, 3) if runs else 0.0,
                # The share of returned findings that failed validation. Rising
                # here is the earliest warning that output quality slipped.
                "drop_rate": round((row["dropped"] or 0) / produced, 3) if produced else 0.0,
            }
        )

    reviews = totals["reviews"] or 0
    return {
        "window_days": days,
        "reviews": reviews,
        "cost_usd": round(totals["cost_usd"] or 0.0, 6),
        "cost_per_review_usd": round((totals["cost_usd"] or 0.0) / reviews, 6) if reviews else 0.0,
        "tokens_in": totals["tokens_in"] or 0,
        "tokens_out": totals["tokens_out"] or 0,
        "avg_duration_ms": int(totals["avg_duration_ms"] or 0),
        "agents": agents,
        "config": {
            "model": LLM_MODEL,
            "prompt_version": PROMPT_VERSION,
            "cost_ceiling_usd": REVIEW_COST_CEILING_USD,
        },
        "rate_limit_remaining": {
            "review": remaining("review", user.id),
            "chat": remaining("chat", user.id),
        },
    }
