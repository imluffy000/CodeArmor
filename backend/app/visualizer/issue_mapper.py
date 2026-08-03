from app.models.issue import Issue


def map_finding(
    file: str,
    severity: str,
    category: str,
    issue: str,
    suggestion: str,
) -> Issue:
    return Issue(
        file=file,
        severity=severity.upper(),
        category=category.upper(),
        issue=issue,
        suggestion=suggestion,
    )


def map_semgrep_results(results: list[dict]) -> list[Issue]:
    issues = []
    for item in results:
        issues.append(
            map_finding(
                file=item.get("file", "unknown"),
                severity=item.get("severity", "MEDIUM"),
                category="SECURITY",
                issue=item.get("issue", "Semgrep finding"),
                suggestion=item.get("suggestion", "Review and fix this finding."),
            )
        )
    return issues


def map_bandit_results(results: list[dict]) -> list[Issue]:
    issues = []
    for item in results:
        issues.append(
            map_finding(
                file=item.get("file", "unknown"),
                severity=item.get("severity", "HIGH"),
                category="SECURITY",
                issue=item.get("issue", "Bandit finding"),
                suggestion=item.get("suggestion", "Address security concern."),
            )
        )
    return issues


def map_pylint_results(results: list[dict]) -> list[Issue]:
    issues = []
    for item in results:
        issues.append(
            map_finding(
                file=item.get("file", "unknown"),
                severity=item.get("severity", "LOW"),
                category="QUALITY",
                issue=item.get("issue", "Pylint finding"),
                suggestion=item.get("suggestion", "Improve code quality."),
            )
        )
    return issues
