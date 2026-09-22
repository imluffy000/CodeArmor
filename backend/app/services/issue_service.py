"""Merging, deduplicating and ordering findings from six independent agents.

Six agents reading the same diff will independently find the same problem and
describe it three different ways - security calls it "missing input validation",
quality calls it "missing error handling", architecture calls it "no validation
layer". Concatenating the lists ships all three, inflates every count, and
triples the score penalty for one defect.

So findings are reconciled: near-duplicates collapse into one finding that
records how many agents agreed, and agreement becomes a confidence signal
rather than noise.
"""
import re

from app.core.constants import SEVERITY_ORDER
from app.models.issue import Issue

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "for", "from", "has",
    "in", "is", "it", "its", "may", "not", "of", "on", "or", "that", "the", "this",
    "to", "which", "will", "with", "without", "should", "could", "would",
}

# How close two findings must be, as a fraction of shared significant words,
# before they are treated as the same problem.
_SIMILARITY_THRESHOLD = 0.6

# Findings within this many lines of each other are candidates for merging.
_LINE_WINDOW = 5


def _significant_words(text: str) -> set[str]:
    return {
        word
        for word in _WORD_RE.findall(text.lower())
        if len(word) > 2 and word not in _STOPWORDS
    }


def _similarity(left: str, right: str) -> float:
    left_words = _significant_words(left)
    right_words = _significant_words(right)
    if not left_words or not right_words:
        return 0.0
    overlap = len(left_words & right_words)
    return overlap / min(len(left_words), len(right_words))


def _same_place(left: Issue, right: Issue) -> bool:
    if left.file != right.file:
        return False
    if left.line is None or right.line is None:
        return True
    return abs(left.line - right.line) <= _LINE_WINDOW


def merge_issues(*issue_lists: list[Issue]) -> list[Issue]:
    """Flatten the per-agent lists. Varargs so adding a category is not a
    signature change across four call sites."""
    merged: list[Issue] = []
    for issues in issue_lists:
        if issues:
            merged.extend(issues)
    return merged


def deduplicate_issues(issues: list[Issue]) -> list[Issue]:
    """Collapse findings that describe the same problem.

    The surviving finding keeps the highest severity seen, records the other
    categories that reported it, and carries an `agreement` count - a problem
    three agents found independently deserves more of the reader's attention
    than one agent's guess.
    """
    kept: list[Issue] = []

    # Worst-first, so the survivor of a merge is the most severe description.
    for issue in sorted(issues, key=lambda i: -SEVERITY_ORDER.get(i.severity, 0)):
        duplicate_of = None
        for existing in kept:
            if not _same_place(existing, issue):
                continue
            if _similarity(existing.issue, issue.issue) >= _SIMILARITY_THRESHOLD:
                duplicate_of = existing
                break

        if duplicate_of is None:
            kept.append(issue)
            continue

        duplicate_of.agreement += 1
        if (
            issue.category != duplicate_of.category
            and issue.category not in duplicate_of.also_reported_as
        ):
            duplicate_of.also_reported_as.append(issue.category)
        # Keep a line number and snippets if the duplicate had them and the
        # survivor did not.
        if duplicate_of.line is None and issue.line is not None:
            duplicate_of.line = issue.line
        if not duplicate_of.code_snippet and issue.code_snippet:
            duplicate_of.code_snippet = issue.code_snippet
        if not duplicate_of.suggestion_snippet and issue.suggestion_snippet:
            duplicate_of.suggestion_snippet = issue.suggestion_snippet

    return kept


def sort_issues(issues: list[Issue]) -> list[Issue]:
    """Worst first, then by how many agents agreed, then by location.

    Ordering matters beyond presentation: the summary agent only sees the first
    N findings, so an unsorted list means a CRITICAL integration problem can be
    left out of the summary by a run of LOW style notes.
    """
    return sorted(
        issues,
        key=lambda i: (
            -SEVERITY_ORDER.get(i.severity, 0),
            -i.agreement,
            i.file,
            i.line if i.line is not None else 0,
        ),
    )


def reconcile(*issue_lists: list[Issue]) -> list[Issue]:
    """The whole pipeline: merge, deduplicate, order."""
    return sort_issues(deduplicate_issues(merge_issues(*issue_lists)))


def count_blocking(issues: list[Issue]) -> int:
    return sum(1 for issue in issues if issue.is_blocking)


def compute_score(issues: list[Issue], coverage_percent: int = 100) -> int:
    """A 0-100 health score, computed server-side so it is stored and reproducible.

    Weighted by severity and damped rather than a linear subtraction, so a large
    pull request does not floor at zero and stop discriminating on exactly the
    changes that need the most attention. Scaled down when the review only
    covered part of the diff - an incomplete review should not read as a clean one.
    """
    if not issues:
        base = 100
    else:
        weights = {"CRITICAL": 25, "HIGH": 12, "MEDIUM": 5, "LOW": 1.5}
        penalty = sum(weights.get(issue.severity, 1.5) for issue in issues)
        # Diminishing returns: the 20th LOW finding should not weigh as much as
        # the first CRITICAL one.
        base = int(round(100 * (100 / (100 + penalty))))

    if coverage_percent < 100:
        # Cap the score by how much of the diff was actually read.
        base = min(base, 50 + int(coverage_percent / 2))

    return max(0, min(100, base))


def score_label(score: int) -> str:
    if score >= 90:
        return "Looks clean"
    if score >= 75:
        return "Minor issues"
    if score >= 50:
        return "Needs attention"
    return "Needs work"
