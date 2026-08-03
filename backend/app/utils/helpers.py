from pathlib import Path

from app.core.constants import MAX_DIFF_LENGTH

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}_prompt.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def truncate_diff(diff: str, max_length: int = MAX_DIFF_LENGTH) -> str:
    if len(diff) <= max_length:
        return diff
    return diff[:max_length] + "\n\n... [diff truncated]"


def default_pr_state(pr_url: str, diff: str, parsed_files: list) -> dict:
    return {
        "pr_url": pr_url,
        "diff": diff,
        "parsed_files": parsed_files,
        "security_issues": [],
        "quality_issues": [],
        "performance_issues": [],
        "testing_issues": [],
        "architecture_issues": [],
        "all_issues": [],
        "folder_tree": {},
        "final_summary": "",
    }
