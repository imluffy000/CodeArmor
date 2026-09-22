"""Render a stored review as the Markdown body of a GitHub review comment."""
from app.core.constants import SEVERITY_ORDER

# GitHub rejects a review body over 65,536 characters with a 422, so a large
# review has to be trimmed rather than discovered at the API call.
MAX_BODY_CHARS = 60000

_VERDICT_HEADLINE = {
    "blocked": "Not ready to merge",
    "caution": "Merge with care",
    "clear": "Nothing blocking found",
}


def generate_review_message(
    issues: list[dict],
    stats: dict | None = None,
    merge_readiness: dict | None = None,
    coverage: dict | None = None,
    agent_errors: list[dict] | None = None,
) -> str:
    stats = stats or {}
    merge_readiness = merge_readiness or {}
    coverage = coverage or {}
    agent_errors = agent_errors or []

    verdict = merge_readiness.get("verdict", "clear")
    headline = _VERDICT_HEADLINE.get(verdict, "Review complete")

    parts: list[str] = ["## CodeArmor review", "", f"**{headline}.** "]

    if stats:
        parts[-1] += (
            f"{stats.get('total_issues', 0)} finding(s) across "
            f"{stats.get('files_affected', 0)} file(s). "
            f"Score {stats.get('score', '-')}/100."
        )
    parts.append("")

    # Caveats first - a reader who stops after two lines should still know the
    # review was partial or that a reviewer did not run.
    if coverage.get("truncated"):
        not_reviewed = coverage.get("files_not_reviewed") or []
        parts.append(
            f"> **Partial review.** About {coverage.get('reviewed_percent', 0)}% of "
            f"the diff was analysed. {len(not_reviewed)} file(s) were not read, so "
            "absence of a finding there means nothing."
        )
        parts.append("")

    if agent_errors:
        failed = ", ".join(sorted({e.get("agent", "unknown") for e in agent_errors}))
        parts.append(
            f"> **Incomplete.** These reviewers did not finish: {failed}. "
            "Their findings are missing from this report."
        )
        parts.append("")

    blockers = merge_readiness.get("blockers") or []
    warnings = merge_readiness.get("warnings") or []

    if blockers:
        parts.append("### Blocking before merge")
        parts.extend(f"- {item}" for item in blockers)
        parts.append("")

    if warnings:
        parts.append("### Worth checking")
        parts.extend(f"- {item}" for item in warnings)
        parts.append("")

    if issues:
        parts.append("### Findings by file")
        parts.append("")

        grouped: dict[str, list[dict]] = {}
        for issue in issues:
            grouped.setdefault(issue.get("file", "unknown"), []).append(issue)

        ordered_paths = sorted(
            grouped,
            key=lambda p: (
                -max(SEVERITY_ORDER.get(i.get("severity", "LOW"), 0) for i in grouped[p]),
                p,
            ),
        )

        for path in ordered_paths:
            file_issues = grouped[path]
            parts.append(f"#### `{path}` - {len(file_issues)} finding(s)")
            parts.append("")
            for index, issue in enumerate(file_issues, 1):
                location = f" (line {issue['line']})" if issue.get("line") else ""
                agreement = ""
                if (issue.get("agreement") or 1) > 1:
                    agreement = f" _{issue['agreement']} reviewers agreed_"
                parts.append(
                    f"{index}. **[{issue.get('severity')}] "
                    f"{issue.get('category')}**{location}{agreement}"
                )
                parts.append(f"  - **Problem:** {issue.get('issue') or issue.get('problem')}")
                parts.append(
                    "  - **Suggestion:** "
                    + str(issue.get("suggestion") or issue.get("recommendation") or "")
                )
                parts.append("")
    else:
        parts.append("No findings were reported in the analysed portion of this diff.")
        parts.append("")

    parts.append("---")
    parts.append(
        "_Posted by CodeArmor. This is an automated analysis, not an approval - "
        "a human still needs to review this change._"
    )

    body = "\n".join(parts)

    if len(body) > MAX_BODY_CHARS:
        cutoff = body.rfind("\n", 0, MAX_BODY_CHARS - 200)
        body = (
            body[: cutoff if cutoff > 0 else MAX_BODY_CHARS - 200]
            + "\n\n_...truncated. Open the review in CodeArmor for the remaining findings._"
        )

    return body
