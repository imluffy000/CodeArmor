from collections.abc import Callable
from dataclasses import dataclass

from app.static_analysis.csharp.roslyn_runner import run_roslyn
from app.static_analysis.java.spotbugs_runner import run_spotbugs
from app.static_analysis.javascript.eslint_runner import run_eslint
from app.static_analysis.python.bandit_runner import run_bandit
from app.static_analysis.python.pylint_runner import run_pylint
from app.static_analysis.shared.detector import scan_repository_languages
from app.static_analysis.shared.semgrep_runner import run_semgrep
from app.static_analysis.sql.sqlfluff_runner import run_sqlfluff


Runner = Callable[[str], list[dict]]


@dataclass(frozen=True)
class StaticAnalysisTool:
    name: str
    runner: Runner
    category: str


LANGUAGE_TOOLS = {
    "python": [
        StaticAnalysisTool("bandit", run_bandit, "SECURITY"),
        StaticAnalysisTool("pylint", run_pylint, "QUALITY"),
    ],
    "javascript": [
        StaticAnalysisTool("eslint", run_eslint, "QUALITY"),
    ],
    "typescript": [
        StaticAnalysisTool("eslint", run_eslint, "QUALITY"),
    ],
    "java": [
        StaticAnalysisTool("spotbugs", run_spotbugs, "QUALITY"),
    ],
    "csharp": [
        StaticAnalysisTool("roslyn", run_roslyn, "QUALITY"),
    ],
    "sql": [
        StaticAnalysisTool("sqlfluff", run_sqlfluff, "QUALITY"),
    ],
}

COMMON_TOOLS = [
    StaticAnalysisTool("semgrep", run_semgrep, "SECURITY"),
]


def get_tools_for_languages(languages: set[str]) -> list[StaticAnalysisTool]:
    tools = [*COMMON_TOOLS]
    for language in sorted(languages):
        tools.extend(LANGUAGE_TOOLS.get(language, []))

    deduped = []
    seen_names = set()
    for tool in tools:
        if tool.name in seen_names:
            continue
        seen_names.add(tool.name)
        deduped.append(tool)
    return deduped


def run_static_analysis(target_dir: str) -> dict[str, list]:
    languages = scan_repository_languages(target_dir)
    grouped_findings = {
        "security": [],
        "quality": [],
    }

    for tool in get_tools_for_languages(languages):
        findings = tool.runner(target_dir)
        if tool.category.upper() == "SECURITY":
            grouped_findings["security"].extend(findings)
        else:
            grouped_findings["quality"].extend(findings)

    return grouped_findings
