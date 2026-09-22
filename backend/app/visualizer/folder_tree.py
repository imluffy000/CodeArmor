"""Group findings into a directory tree for display.

The obvious implementation - one dict where directories and filenames share a
namespace - crashes on real input. An agent is free to name a file `src/app`
while another names `src/app/main.py`, and then one ordering wraps a subtree
dict into an issue list (later `item["severity"]` raises KeyError) and the other
tries to assign a string key on a list (TypeError). Either way a review that
already cost six LLM calls dies at the rendering step.

So folders and files live in separate maps and every node says what it is.
"""
from app.models.issue import Issue


def _new_node() -> dict:
    return {"type": "dir", "dirs": {}, "files": {}}


def _normalise(path: str) -> list[str]:
    """Split a path into segments, dropping the noise agents sometimes emit.

    Absolute paths turn up when a static-analysis runner reports a host path;
    without this, the tree grows an empty-string root that renders as a blank
    branch.
    """
    cleaned = (path or "unknown").replace("\\", "/").strip()
    segments = [part for part in cleaned.split("/") if part not in ("", ".", "..")]
    return segments or ["unknown"]


def build_folder_tree(issues: list[Issue]) -> dict:
    root = _new_node()

    for issue in issues:
        segments = _normalise(issue.file)
        *folders, filename = segments

        current = root
        for folder in folders:
            current = current["dirs"].setdefault(folder, _new_node())

        entry = {
            "severity": issue.severity,
            "category": issue.category,
            "problem": issue.issue,
            "recommendation": issue.suggestion,
            "line": issue.line,
            "agreement": issue.agreement,
        }
        current["files"].setdefault(filename, []).append(entry)

    return root
