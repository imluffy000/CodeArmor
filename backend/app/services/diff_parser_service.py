import re


def parse_diff_files(diff: str) -> list[str]:
    pattern = r"diff --git a/(.*?) b/"
    matches = re.findall(pattern, diff)
    return list(set(matches))


def extract_added_lines(diff: str) -> list[str]:
    added = []
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line)
    return added


def extract_removed_lines(diff: str) -> list[str]:
    removed = []
    for line in diff.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            removed.append(line)
    return removed


def summarize_diff(diff: str) -> dict:
    return {
        "changed_files": parse_diff_files(diff),
        "added_lines_count": len(extract_added_lines(diff)),
        "removed_lines_count": len(extract_removed_lines(diff)),
    }
