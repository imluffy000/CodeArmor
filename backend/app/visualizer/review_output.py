from collections import defaultdict

from app.models.issue import Issue


def build_stats(issues: list[Issue]) -> dict:
    by_severity: dict[str, int] = defaultdict(int)
    by_category: dict[str, int] = defaultdict(int)
    files = set()

    for issue in issues:
        by_severity[issue.severity] += 1
        by_category[issue.category] += 1
        files.add(issue.file)

    return {
        "total_issues": len(issues),
        "files_affected": len(files),
        "by_severity": dict(sorted(by_severity.items())),
        "by_category": dict(sorted(by_category.items())),
    }


def build_files_with_issues(issues: list[Issue]) -> list[dict]:
    grouped: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        grouped[issue.file].append(issue)

    result = []
    for path in sorted(grouped.keys()):
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
                    }
                    for i in file_issues
                ],
            }
        )
    return result


def build_folder_view(tree: dict, prefix: str = "") -> str:
    lines = []
    entries = sorted(tree.items(), key=lambda x: x[0])

    for index, (name, value) in enumerate(entries):
        is_last = index == len(entries) - 1
        branch = "└── " if is_last else "├── "
        lines.append(f"{prefix}{branch}{name}")

        if isinstance(value, dict) and value and "problem" not in value:
            extension = "    " if is_last else "│   "
            lines.append(build_folder_view(value, prefix + extension))
        elif isinstance(value, list):
            extension = "    " if is_last else "│   "
            for issue_index, item in enumerate(value):
                marker = "└─" if issue_index == len(value) - 1 else "├─"
                lines.append(
                    f"{prefix}{extension}{marker} "
                    f"[{item['severity']}] {item['category']}: {item['problem']}"
                )
                lines.append(
                    f"{prefix}{extension}{'   ' if marker == '└─' else '│  '}"
                    f"→ Fix: {item['recommendation']}"
                )

    return "\n".join(lines)


def build_structured_review(summary: str, issues: list[Issue], folder_tree: dict) -> dict:
    stats = build_stats(issues)
    files_with_issues = build_files_with_issues(issues)
    folder_view = (
        "📁 Files with issues:\n" + build_folder_view(folder_tree)
        if issues
        else "📁 No files with issues."
    )

    return {
        "summary": summary,
        "stats": stats,
        "files_with_issues": files_with_issues,
        "folder_tree": folder_tree,
        "folder_view": folder_view,
        "issues": issues,
    }
