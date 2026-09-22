"""Response bodies."""
from typing import Dict, List

from pydantic import BaseModel

from app.models.issue import Issue


class IssueDetail(BaseModel):
    severity: str
    category: str
    problem: str
    recommendation: str
    code_snippet: str | None = None
    suggestion_snippet: str | None = None
    line: int | None = None
    agreement: int = 1
    also_reported_as: List[str] = []


class FileReview(BaseModel):
    path: str
    issue_count: int
    issues: List[IssueDetail]


class ReviewStats(BaseModel):
    total_issues: int
    files_affected: int
    by_severity: Dict[str, int]
    by_category: Dict[str, int]
    blocking_issues: int = 0
    score: int = 100
    score_label: str = "Looks clean"


class Gate(BaseModel):
    status: str  # pass | warn | fail | unknown
    detail: str


class MergeReadiness(BaseModel):
    verdict: str = "clear"  # blocked | caution | clear
    headline: str = ""
    blockers: List[str] = []
    warnings: List[str] = []
    gates: Dict[str, Gate] = {}
    highest_severity: str | None = None


class Coverage(BaseModel):
    """How much of the diff this review actually read.

    Surfaced deliberately: a review of 4% of a large pull request that happens
    to find nothing must not be presentable as a clean result.
    """

    reviewed_percent: int = 100
    truncated: bool = False
    files_reviewed: List[str] = []
    files_not_reviewed: List[str] = []


class AgentError(BaseModel):
    agent: str
    error: str | None = None


class ReviewResponse(BaseModel):
    review_id: int | None = None
    repo_full_name: str | None = None
    pr_number: int | None = None
    head_sha: str | None = None
    created_at: str | None = None
    cached: bool = False

    summary: str
    stats: ReviewStats
    files_with_issues: List[FileReview]
    folder_tree: Dict
    folder_view: str
    issues: List[Issue]

    merge_readiness: MergeReadiness = MergeReadiness()
    coverage: Coverage = Coverage()
    agent_errors: List[AgentError] = []
    dropped_findings: int = 0

    posted_to_github: bool = False
    github_error: str | None = None


class ReviewSummaryItem(BaseModel):
    """One row in the review history list."""

    review_id: int
    repo_full_name: str
    pr_number: int
    pr_title: str | None = None
    head_sha: str | None = None
    total_issues: int
    critical_issues: int
    score: int | None = None
    verdict: str | None = None
    posted_to_github: bool = False
    created_at: str
