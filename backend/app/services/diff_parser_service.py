"""Small helpers for reading a unified diff."""
import re

# Capture the b/ path: for a rename, a/ holds the OLD name, which is not the
# file a finding should be attributed to.
_DIFF_HEADER = re.compile(r"^diff --git a/(?P<old>.+?) b/(?P<new>.+)$", re.MULTILINE)


def parse_diff_files(diff: str) -> list[str]:
    """Changed file paths, in diff order, deduplicated.

    Order is stable: `list(set(...))` varies between processes under hash
    randomisation, which makes any output built from it non-reproducible.
    """
    paths = [match.group("new").strip() for match in _DIFF_HEADER.finditer(diff or "")]
    return list(dict.fromkeys(paths))


def extract_added_lines(diff: str) -> list[str]:
    return [
        line
        for line in (diff or "").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def extract_removed_lines(diff: str) -> list[str]:
    return [
        line
        for line in (diff or "").splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]


def summarize_diff(diff: str) -> dict:
    return {
        "changed_files": parse_diff_files(diff),
        "added_lines_count": len(extract_added_lines(diff)),
        "removed_lines_count": len(extract_removed_lines(diff)),
    }
