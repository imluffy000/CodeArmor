from app.core.logging import logger
from app.github.fetch_pr import fetch_pr_diff, parse_pr_url
from app.github.review_pr import create_pr_review
from app.graph.workflow import graph
from app.models.response_models import ReviewResponse
from app.services.diff_parser_service import parse_diff_files
from app.services.review_message_service import generate_review_message
from app.utils.helpers import default_pr_state
from app.visualizer.review_output import build_structured_review


async def run_pr_review(
    pr_url: str,
    post_to_github: bool = True,
    token: str | None = None,
) -> ReviewResponse:
    logger.info("Starting PR review for %s", pr_url)

    diff = fetch_pr_diff(pr_url, token=token)
    parsed_files = parse_diff_files(diff)
    initial_state = default_pr_state(pr_url, diff, parsed_files)

    result = await graph.ainvoke(initial_state)
    structured = build_structured_review(
        summary=result["final_summary"],
        issues=result["all_issues"],
        folder_tree=result["folder_tree"],
    )

    review_message = generate_review_message(
        structured["issues"],
        folder_tree=structured["folder_tree"],
    )
    event_type = "REQUEST_CHANGES" if structured["issues"] else "APPROVE"

    github_error = None
    if post_to_github:
        parsed_pr = parse_pr_url(pr_url)
        try:
            create_pr_review(
                owner=parsed_pr["owner"],
                repo=parsed_pr["repo"],
                pr_number=parsed_pr["pr_number"],
                body=review_message,
                event=event_type,
                token=token,
            )
        except Exception as e:
            logger.warning("Failed to post review to GitHub: %s", e)
            github_error = str(e)

    structured["github_error"] = github_error
    return ReviewResponse(**structured)


async def stream_pr_review(
    pr_url: str,
    post_to_github: bool = True,
    token: str | None = None,
):
    import asyncio
    import json
    import os
    from app.agents.security_agent import security_agent
    from app.agents.quality_agent import quality_agent
    from app.agents.performance_agent import performance_agent
    from app.agents.testing_agent import testing_agent
    from app.agents.architecture_agent import architecture_agent
    from app.agents.summary_agent import summary_agent
    
    from app.static_analysis.bandit_runner import run_bandit
    from app.static_analysis.pylint_runner import run_pylint
    from app.static_analysis.semgrep_runner import run_semgrep
    from app.visualizer.issue_mapper import (
        map_bandit_results,
        map_pylint_results,
        map_semgrep_results,
    )

    logger.info("Starting streaming PR review for %s", pr_url)

    # Step 1: Fetch Diff
    yield {"event": "step", "data": "fetch_diff_start"}
    try:
        diff = fetch_pr_diff(pr_url, token=token)
        parsed_files = parse_diff_files(diff)
        initial_state = default_pr_state(pr_url, diff, parsed_files)
        yield {"event": "step", "data": "fetch_diff_done"}
    except Exception as e:
        logger.exception("Failed to fetch diff")
        yield {"event": "error", "data": f"Failed to fetch PR diff: {str(e)}"}
        return

    # Step 2: Run Specialist Agents Concurrently
    agents = [
        ("security", security_agent(initial_state)),
        ("quality", quality_agent(initial_state)),
        ("performance", performance_agent(initial_state)),
        ("testing", testing_agent(initial_state)),
        ("architecture", architecture_agent(initial_state)),
    ]

    async def run_agent(name, coro):
        try:
            res = await coro
            return name, res, None
        except Exception as e:
            return name, None, e

    tasks = [run_agent(name, task) for name, task in agents]
    futures = [asyncio.create_task(t) for t in tasks]
    merged = {}
    success_count = 0
    errors = []

    for future in asyncio.as_completed(futures):
        name, result, err = await future
        if err:
            logger.warning("Agent %s execution failed: %s", name, err)
            errors.append(f"{name}: {str(err)}")
            yield {"event": "agent_failed", "data": name}
        else:
            yield {"event": "agent_done", "data": name}
            merged.update(result)
            success_count += 1

    if success_count == 0:
        yield {"event": "error", "data": f"All review agents failed to run: {', '.join(errors)}"}
        return

    # Step 3: Run Static Analysis
    static_root = os.environ.get("STATIC_ANALYSIS_ROOT")
    if static_root:
        yield {"event": "step", "data": "static_analysis_start"}
        try:
            merged["security_issues"] = (
                list(merged.get("security_issues", []))
                + map_semgrep_results(run_semgrep(static_root))
                + map_bandit_results(run_bandit(static_root))
            )
            merged["quality_issues"] = (
                list(merged.get("quality_issues", []))
                + map_pylint_results(run_pylint(static_root))
            )
        except Exception as e:
            logger.warning("Static analysis failed: %s", e)
        yield {"event": "step", "data": "static_analysis_done"}

    # Step 4: Run Summary Agent
    state = {**initial_state, **merged}
    yield {"event": "step", "data": "summary_start"}
    try:
        summary_result = await summary_agent(state)
        state.update(summary_result)
        yield {"event": "step", "data": "summary_done"}
    except Exception as e:
        logger.exception("Summary agent failed")
        yield {"event": "error", "data": f"Failed to generate summary: {str(e)}"}
        return

    # Step 5: Build Structured Review
    structured = build_structured_review(
        summary=state["final_summary"],
        issues=state["all_issues"],
        folder_tree=state["folder_tree"],
    )

    # Step 6: Post to GitHub
    github_error = None
    if post_to_github:
        yield {"event": "step", "data": "github_post_start"}
        parsed_pr = parse_pr_url(pr_url)
        try:
            create_pr_review(
                owner=parsed_pr["owner"],
                repo=parsed_pr["repo"],
                pr_number=parsed_pr["pr_number"],
                body=generate_review_message(
                    structured["issues"],
                    folder_tree=structured["folder_tree"],
                ),
                event="REQUEST_CHANGES" if structured["issues"] else "APPROVE",
                token=token,
            )
        except Exception as e:
            logger.warning("Failed to post review to GitHub: %s", e)
            github_error = str(e)
        yield {"event": "step", "data": "github_post_done"}

    structured["github_error"] = github_error

    # Convert Pydantic models in structured for JSON serialization
    serializable_structured = {
        "summary": structured["summary"],
        "stats": structured["stats"],
        "files_with_issues": structured["files_with_issues"],
        "folder_tree": structured["folder_tree"],
        "folder_view": structured["folder_view"],
        "issues": [
            i.model_dump() if hasattr(i, "model_dump") else i.dict() if hasattr(i, "dict") else i
            for i in structured["issues"]
        ],
        "github_error": structured["github_error"],
    }

    # Yield complete event with JSON body
    yield {"event": "complete", "data": json.dumps(serializable_structured)}

