"""The review orchestrator.

There is one pipeline here, not two. It was previously implemented twice - once
through LangGraph for `POST /review` and once by hand for the SSE stream - and
the copies had already diverged on error handling, so a bug fixed in one path
stayed live in the other. Now a single async generator yields progress events,
and the non-streaming caller drains it to completion.

The GitHub write is deliberately not part of this pipeline. Posting a review to
someone's pull request is irreversible and happens under their identity, so it
is a separate, explicit action on a review that already exists.
"""
import json
from typing import AsyncIterator

from app.core.config import LLM_MODEL, REVIEW_COST_CEILING_USD
from app.core.timeutil import iso_utc
from app.core.logging import audit, logger, request_id_var
from app.core.telemetry import (
    CostCeilingExceeded,
    Trace,
    check_cost_ceiling,
    current_trace,
)
from app.db.models import AgentRun, Repository, Review, User
from app.github import client as gh
from app.graph.nodes import FAN_IN_NODE, SPECIALIST_NODES
from app.graph.workflow import get_graph
from app.models.issue import Issue
from app.services.diff_parser_service import parse_diff_files
from app.services.integration_context_service import build_integration_context
from app.services.review_message_service import generate_review_message
from app.utils.helpers import (
    PROMPT_VERSION,
    build_agent_diff,
    default_pr_state,
    truncate_diff,
)
from app.visualizer.review_output import build_structured_review


def _review_context(context: dict, repo: Repository | None, coverage: dict) -> str:
    """The header every specialist prompt gets, outside the untrusted fence.

    Without this each agent saw a bare diff: no file list, no PR description, no
    language. The testing agent then cannot tell "no test was added" from "the
    test file is outside the budget", and reports a false missing-test finding.
    """
    pr = context.get("pull_request", {})
    lines = [
        f"Repository: {repo.full_name if repo else 'unknown'}",
        f"Primary language: {repo.language or 'unknown'}" if repo else "",
        f"Default branch: {repo.default_branch}" if repo else "",
        f"Pull request #{pr.get('number')}: {pr.get('title') or '(no title)'}",
        f"Author: {pr.get('author') or 'unknown'}",
        f"Branch: {pr.get('head_ref')} -> {pr.get('base_ref')}",
        f"Size: {pr.get('changed_file_count', 0)} file(s), "
        f"+{pr.get('additions', 0)}/-{pr.get('deletions', 0)}",
    ]

    description = (pr.get("body") or "").strip()
    if description:
        lines.append("Description (untrusted, written by the PR author):")
        lines.append("  " + description[:800].replace("\n", "\n  "))

    if coverage.get("truncated"):
        lines.append(
            f"NOTE: you are seeing about {coverage.get('coverage_percent', 0)}% of "
            "this diff. Files listed without hunks are named in the diff block "
            "but their contents are not shown - do not report findings about "
            "code you cannot see, and do not assume a listed file is unchanged."
        )

    return "\n".join(line for line in lines if line)


def _cached_review(user: User, repo_full_name: str, pr_number: int, head_sha: str):
    """A completed review of this exact commit, if we already have one.

    Re-running six LLM calls because someone refreshed the page is pure waste,
    and a new push changes head_sha, which is what invalidates this.
    """
    if not head_sha:
        return None
    return (
        Review.select()
        .where(
            (Review.user == user)
            & (Review.repo_full_name == repo_full_name)
            & (Review.pr_number == pr_number)
            & (Review.head_sha == head_sha)
        )
        .order_by(Review.created_at.desc())
        .first()
    )


def _persist(
    user: User,
    repo: Repository | None,
    repo_full_name: str,
    pr_number: int,
    pr_title: str | None,
    head_sha: str,
    structured: dict,
    trace: Trace | None = None,
) -> Review:
    """Store the finished review.

    Reviews used to live only in React state, so closing the tab destroyed a
    result that cost real money and minutes of waiting, and there was no history
    to compare against.
    """
    serialisable = _serialisable(structured)
    stats = structured["stats"]

    review = Review.create(
        user=user,
        repository=repo,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        pr_title=pr_title,
        head_sha=head_sha,
        total_issues=stats["total_issues"],
        critical_issues=stats["by_severity"].get("CRITICAL", 0),
        payload=json.dumps(serialisable),
        trace_id=trace.trace_id if trace else None,
        duration_ms=trace.duration_ms if trace else None,
        tokens_in=trace.total_tokens_in if trace else 0,
        tokens_out=trace.total_tokens_out if trace else 0,
        cost_usd=round(trace.total_cost_usd, 6) if trace else 0.0,
        model=LLM_MODEL,
        prompt_version=PROMPT_VERSION,
        trace=json.dumps(trace.to_dict()) if trace else None,
    )

    # A row per span, so "which agent times out most" and "what does
    # the security agent cost" are queries rather than a scan of JSON.
    if trace and trace.spans:
        AgentRun.bulk_create(
            [
                AgentRun(
                    review=review,
                    agent=span.name,
                    status=span.status,
                    model=span.model,
                    duration_ms=span.duration_ms,
                    tokens_in=span.tokens_in,
                    tokens_out=span.tokens_out,
                    cost_usd=round(span.cost_usd, 6),
                    findings=span.findings,
                    dropped=span.dropped,
                    parse_status=span.parse_status,
                    error=span.error,
                )
                for span in trace.spans
            ]
        )

    return review


def _serialisable(structured: dict) -> dict:
    """Convert Issue models to plain dicts for JSON storage and SSE."""
    return {
        **structured,
        "issues": [
            issue.model_dump() if isinstance(issue, Issue) else issue
            for issue in structured.get("issues", [])
        ],
    }


def review_payload(review: Review, cached: bool = False) -> dict:
    """Rehydrate a stored review into the API response shape."""
    payload = review.data
    payload.update(
        {
            "review_id": review.id,
            "repo_full_name": review.repo_full_name,
            "pr_number": review.pr_number,
            "head_sha": review.head_sha,
            "created_at": iso_utc(review.created_at),
            "cached": cached,
            "posted_to_github": review.posted_to_github,
            "duration_ms": review.duration_ms,
            "cost_usd": review.cost_usd,
        }
    )
    return payload


# --------------------------------------------------------------------------
# The pipeline
# --------------------------------------------------------------------------

async def stream_review(
    user: User,
    repo: Repository,
    pr_number: int,
    github_token: str,
    use_cache: bool = True,
) -> AsyncIterator[dict]:
    """Run a review, yielding SSE-shaped progress events.

    Yields `{"event": ..., "data": ...}` dicts. The terminal event is either
    `complete` (with the full JSON payload) or `error`.
    """
    # One trace per review, held in a ContextVar so every parallel agent
    # branch records into the same object without the graph having to
    # carry it as state.
    trace = Trace()
    trace.attributes = {
        "repo_id": repo.id,
        "pr_number": pr_number,
        "user_id": user.id,
        "request_id": request_id_var.get(),
    }
    # Restore by setting the previous value rather than with reset(token):
    # an async generator is resumed in the consumer's context, so a token
    # created in this frame raises "was created in a different Context" when
    # the finally block runs.
    previous = current_trace.get()
    current_trace.set(trace)
    try:
        async for event in _run_review(
            user, repo, pr_number, github_token, use_cache, trace
        ):
            yield event
    finally:
        current_trace.set(previous)
        trace.log_summary()


async def _run_review(
    user: User,
    repo: Repository,
    pr_number: int,
    token: str,
    use_cache: bool,
    trace: Trace,
) -> AsyncIterator[dict]:
    full_name = repo.full_name

    yield {"event": "step", "data": "fetch_diff_start"}

    try:
        with trace.span("gather", kind="github"):
            context = await build_integration_context(token, full_name, pr_number)
            diff = await gh.fetch_pr_diff(token, full_name, pr_number)
    except gh.GitHubError as exc:
        logger.warning("Could not load %s#%s: %s", full_name, pr_number, exc)
        yield {"event": "error", "data": exc.safe_message}
        return
    except Exception:
        logger.exception("Unexpected failure loading %s#%s", full_name, pr_number)
        yield {"event": "error", "data": "Could not load this pull request from GitHub."}
        return

    pr_meta = context.get("pull_request", {})
    head_sha = pr_meta.get("head_sha") or ""

    if use_cache:
        existing = _cached_review(user, full_name, pr_number, head_sha)
        if existing:
            logger.info("Serving cached review %s for %s#%s", existing.id, full_name, pr_number)
            yield {"event": "cached", "data": str(existing.id)}
            yield {"event": "complete", "data": json.dumps(review_payload(existing, cached=True))}
            return

    # Pop the patches before the context is persisted or sent anywhere: they are
    # the user's source code and only the budgeter needs them.
    files_for_budget = context.pop("_files_with_patches", []) or []
    coverage = build_agent_diff(files_for_budget, raw_diff=diff)

    initial_state = default_pr_state(
        pr_url=f"https://github.com/{full_name}/pull/{pr_number}",
        diff=truncate_diff(diff),
        parsed_files=parse_diff_files(diff),
        agent_diff=coverage["text"],
        review_context=_review_context(context, repo, coverage),
        integration_context=context,
        coverage=coverage,
    )

    yield {"event": "step", "data": "fetch_diff_done"}
    if coverage.get("truncated"):
        yield {
            "event": "coverage",
            "data": json.dumps(
                {
                    "reviewed_percent": coverage["coverage_percent"],
                    "files_not_reviewed": coverage["files_omitted"],
                }
            ),
        }

    graph = get_graph()
    final_state: dict = dict(initial_state)

    try:
        # One orchestrator: LangGraph owns the fan-out, and `updates` gives a
        # per-node event as each specialist finishes, so progress streaming
        # needs no second implementation.
        async for update in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in (update or {}).items():
                if not isinstance(node_output, dict):
                    continue
                final_state.update(node_output)

                if node_name in SPECIALIST_NODES:
                    errors = node_output.get("agent_errors") or []
                    if errors:
                        yield {"event": "agent_failed", "data": node_name}
                    else:
                        yield {"event": "agent_done", "data": node_name}
                elif node_name == FAN_IN_NODE:
                    yield {"event": "step", "data": "summary_done"}

        check_cost_ceiling(trace, REVIEW_COST_CEILING_USD)
    except CostCeilingExceeded as exc:
        logger.warning(
            "Review of %s#%s stopped at the cost ceiling: %s",
            full_name,
            pr_number,
            exc,
        )
        yield {"event": "error", "data": str(exc)}
        return
    except Exception:
        logger.exception("Review pipeline failed for %s#%s", full_name, pr_number)
        yield {"event": "error", "data": "The review pipeline failed. Please try again."}
        return

    if not final_state.get("final_summary"):
        yield {"event": "error", "data": "The review did not produce a result."}
        return

    structured = build_structured_review(
        summary=final_state["final_summary"],
        issues=final_state.get("all_issues") or [],
        folder_tree=final_state.get("folder_tree") or {},
        merge_readiness=final_state.get("merge_readiness") or {},
        coverage=coverage,
        agent_errors=final_state.get("agent_errors") or [],
        dropped_findings=final_state.get("dropped_findings", 0),
    )

    review = _persist(
        user=user,
        repo=repo,
        repo_full_name=full_name,
        pr_number=pr_number,
        pr_title=pr_meta.get("title"),
        head_sha=head_sha,
        structured=structured,
        trace=trace,
    )

    audit(
        "review.completed",
        user_id=user.id,
        review_id=review.id,
        repo_id=repo.id,
        pr_number=pr_number,
        findings=structured["stats"]["total_issues"],
        verdict=(structured.get("merge_readiness") or {}).get("verdict"),
        trace_id=trace.trace_id,
        cost_usd=round(trace.total_cost_usd, 4),
        duration_ms=trace.duration_ms,
    )

    yield {"event": "complete", "data": json.dumps(review_payload(review))}


async def run_review(
    user: User,
    repo: Repository,
    pr_number: int,
    token: str,
    use_cache: bool = True,
) -> dict:
    """Non-streaming review: drain the one pipeline and return the final payload."""
    error: str | None = None

    async for event in stream_review(user, repo, pr_number, token, use_cache=use_cache):
        if event["event"] == "complete":
            return json.loads(event["data"])
        if event["event"] == "error":
            error = event["data"]

    raise RuntimeError(error or "The review did not produce a result.")


# --------------------------------------------------------------------------
# Publishing to GitHub - separate, explicit, and never an approval
# --------------------------------------------------------------------------

async def post_review_to_github(review: Review, token: str) -> dict:
    """Publish a stored review as a COMMENT on the pull request.

    Always COMMENT. An APPROVE can satisfy a branch-protection rule, so an
    automated approval driven by attacker-controlled diff text becomes a way to
    merge unreviewed code; and GitHub rejects APPROVE or REQUEST_CHANGES on your
    own pull request anyway, which is the common case here.
    """
    payload = review.data
    body = generate_review_message(
        payload.get("issues") or [],
        stats=payload.get("stats") or {},
        merge_readiness=payload.get("merge_readiness") or {},
        coverage=payload.get("coverage") or {},
        agent_errors=payload.get("agent_errors") or [],
    )

    try:
        await gh.create_pr_review(
            token, review.repo_full_name, review.pr_number, body, event="COMMENT"
        )
    except gh.GitHubError as exc:
        logger.warning(
            "Could not post review %s to %s#%s: %s",
            review.id,
            review.repo_full_name,
            review.pr_number,
            exc,
        )
        return {"posted": False, "error": exc.safe_message}

    review.posted_to_github = True
    review.save()

    stored = review.data
    stored["posted_to_github"] = True
    review.payload = json.dumps(stored)
    review.save()

    audit(
        "review.posted_to_github",
        user_id=review.user.id,
        review_id=review.id,
        repo=review.repo_full_name,
        pr_number=review.pr_number,
    )
    return {"posted": True, "error": None}
