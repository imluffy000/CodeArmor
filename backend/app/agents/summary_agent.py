"""The fan-in: reconcile every agent's findings, gate the merge, write the summary."""
from app.core.logging import logger
from app.core.telemetry import agent_span
from app.core.constants import ISSUE_BUCKETS
from app.services import merge_gate_service
from app.services.issue_service import reconcile
from app.services.llm_service import generate_summary_text
from app.visualizer.folder_tree import build_folder_tree

# How many findings the summary writer sees. They arrive worst-first, so the
# cut never hides a critical finding behind a run of style notes.
SUMMARY_FINDING_LIMIT = 25


async def summary_agent(state) -> dict:
    all_issues = reconcile(*(state.get(bucket) or [] for bucket in ISSUE_BUCKETS))

    folder_tree = build_folder_tree(all_issues)
    coverage = state.get("coverage") or {}
    agent_errors = state.get("agent_errors") or []

    readiness = merge_gate_service.evaluate(
        all_issues,
        state.get("integration_context"),
        coverage=coverage,
        agent_errors=agent_errors,
    )

    if state.get("injection_suspected"):
        readiness["warnings"].insert(
            0,
            "Possible prompt injection: the pull request content appears to "
            "contain instructions aimed at the reviewer. Read these findings "
            "with that in mind, and check the diff by hand.",
        )
        if readiness["verdict"] == merge_gate_service.CLEAR:
            readiness["verdict"] = merge_gate_service.CAUTION
            readiness["headline"] = "Merge with care: possible prompt injection in the diff."

    categories = sorted({issue.category for issue in all_issues})
    issues_text = "\n".join(
        "- [{severity}] {file}{line}: {issue}".format(
            severity=issue.severity,
            file=issue.file,
            line=f":{issue.line}" if issue.line else "",
            issue=issue.issue,
        )
        for issue in all_issues[:SUMMARY_FINDING_LIMIT]
    )

    coverage_note = ""
    if coverage.get("truncated"):
        omitted = coverage.get("files_omitted") or []
        coverage_note = (
            "COVERAGE WARNING: this review read about "
            f"{coverage.get('coverage_percent', 0)}% of the diff. "
            f"{len(omitted)} file(s) were not reviewed. Say so in line 1."
        )

    try:
        with agent_span("summary") as span:
            summary = await generate_summary_text(
                issue_count=len(all_issues),
                categories=categories,
                issues_text=issues_text,
                merge_readiness=merge_gate_service.summarise_for_prompt(readiness),
                coverage_note=coverage_note,
                span=span,
            )
    except Exception as exc:
        # The findings and the gate are the valuable output; a missing prose
        # summary should degrade, not fail the review.
        logger.warning("Summary generation failed, using a computed fallback: %s", exc)
        summary = _fallback_summary(all_issues, readiness, coverage)

    return {
        "all_issues": all_issues,
        "folder_tree": folder_tree,
        "merge_readiness": readiness,
        "final_summary": summary,
    }


def _fallback_summary(all_issues, readiness, coverage) -> str:
    lines = [readiness.get("headline", "Review complete.")]
    for issue in all_issues[:4]:
        lines.append(f"- [{issue.severity}] {issue.file}: {issue.issue[:120]}")
    if coverage.get("truncated"):
        lines.append(
            f"- This review covered about {coverage.get('coverage_percent', 0)}% "
            "of the diff, so treat it as partial."
        )
    blockers = readiness.get("blockers") or []
    if blockers:
        lines.append(f"Recommendation: {blockers[0]}")
    elif all_issues:
        lines.append(f"Recommendation: start with {all_issues[0].file}.")
    else:
        lines.append("Recommendation: have a human review this change before merging.")
    return "\n".join(lines)
