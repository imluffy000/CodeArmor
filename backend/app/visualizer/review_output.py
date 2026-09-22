"""Turn a finished review into the structured payload the API returns."""
from collections import defaultdict

from app.core.constants import SEVERITY_ORDER, SUPPORTED_CATEGORIES, SUPPORTED_SEVERITIES
from app.models.issue import Issue
from app.services.issue_service import compute_score, score_label


def build_stats(issues: list[Issue], coverage_percent: int = 100) -> dict:
    by_severity: dict[str, int] = defaultdict(int)
    by_category: dict[str, int] = defaultdict(int)
    files = set()

    for issue in issues:
        by_severity[issue.severity] += 1
        by_category[issue.category] += 1
        files.add(issue.file)

    score = compute_score(issues, coverage_percent)

    return {
        "total_issues": len(issues),
        "files_affected": len(files),
        # Worst-first, and every bucket present so the client never has to guess
        # whether a missing key means zero or means the key was renamed.
        "by_severity": {
            severity: by_severity.get(severity, 0)
            for severity in sorted(SUPPORTED_SEVERITIES, key=lambda s: -SEVERITY_ORDER[s])
        },
        "by_category": {
            category: by_category.get(category, 0) for category in SUPPORTED_CATEGORIES
        },
        "blocking_issues": by_severity.get("CRITICAL", 0) + by_severity.get("HIGH", 0),
        # Computed server-side so it is stored, reproducible, and identical for
        # every client that reads this review.
        "score": score,
        "score_label": score_label(score),
    }


def build_files_with_issues(issues: list[Issue]) -> list[dict]:
    grouped: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        grouped[issue.file].append(issue)

    result = []
    # Files with the worst finding first, so the reader starts where it matters.
    for path in sorted(
        grouped.keys(),
        key=lambda p: (-max(SEVERITY_ORDER.get(i.severity, 0) for i in grouped[p]), p),
    ):
        file_issues = grouped[path]
        result.append(
            {
                "path": path,
                "issue_count": len(file_issues),
                "issues": [
                    {
                        "severity": i.severity,
                        "category": i.category,
                        "problem": i.issue,
                        "recommendation": i.suggestion,
                        "code_snippet": i.code_snippet,
                        "suggestion_snippet": i.suggestion_snippet,
                        "line": i.line,
                        "agreement": i.agreement,
                        "also_reported_as": i.also_reported_as,
                    }
                    for i in file_issues
                ],
            }
        )
    return result


def build_folder_view(node: dict, prefix: str = "") -> str:
    """Render the tree as text. Node shapes are explicit, so nothing is guessed."""
    if not node:
        return ""

    lines: list[str] = []
    dirs = node.get("dirs") or {}
    files = node.get("files") or {}

    entries: list[tuple[str, str, object]] = [
        *[("dir", name, child) for name, child in sorted(dirs.items())],
        *[("file", name, child) for name, child in sorted(files.items())],
    ]

    for index, (kind, name, child) in enumerate(entries):
        is_last = index == len(entries) - 1
        branch = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "
        lines.append(f"{prefix}{branch}{name}")

        if kind == "dir":
            rendered = build_folder_view(child, prefix + extension)
            if rendered:
                lines.append(rendered)
            continue

        for issue_index, item in enumerate(child):
            marker = "└─" if issue_index == len(child) - 1 else "├─"
            continuation = "   " if marker == "└─" else "│  "
            location = f" (line {item['line']})" if item.get("line") else ""
            lines.append(
                f"{prefix}{extension}{marker} "
                f"[{item['severity']}] {item['category']}{location}: {item['problem']}"
            )
            lines.append(
                f"{prefix}{extension}{continuation}-> Fix: {item['recommendation']}"
            )

    return "\n".join(lines)


def build_structured_review(
    summary: str,
    issues: list[Issue],
    folder_tree: dict,
    merge_readiness: dict | None = None,
    coverage: dict | None = None,
    agent_errors: list[dict] | None = None,
    dropped_findings: int = 0,
) -> dict:
    coverage = coverage or {}
    coverage_percent = coverage.get("coverage_percent", 100)

    stats = build_stats(issues, coverage_percent)
    files_with_issues = build_files_with_issues(issues)

    folder_view = (
        "Files with findings:\n" + build_folder_view(folder_tree)
        if issues
        else "No files with findings."
    )

    return {
        "summary": summary,
        "stats": stats,
        "files_with_issues": files_with_issues,
        "folder_tree": folder_tree,
        "folder_view": folder_view,
        "issues": issues,
        "merge_readiness": merge_readiness or {},
        "coverage": {
            "reviewed_percent": coverage_percent,
            "truncated": bool(coverage.get("truncated")),
            "files_reviewed": coverage.get("files_included") or [],
            "files_not_reviewed": coverage.get("files_omitted") or [],
        },
        # Surfaced rather than swallowed: a review missing its security pass must
        # not be presentable as a clean bill of health.
        "agent_errors": agent_errors or [],
        "dropped_findings": dropped_findings,
        "github_error": None,
        "posted_to_github": False,
    }
