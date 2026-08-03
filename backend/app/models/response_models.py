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


class FileReview(BaseModel):
    path: str
    issue_count: int
    issues: List[IssueDetail]


class ReviewStats(BaseModel):
    total_issues: int
    files_affected: int
    by_severity: Dict[str, int]
    by_category: Dict[str, int]


class ReviewResponse(BaseModel):
    summary: str
    stats: ReviewStats
    files_with_issues: List[FileReview]
    folder_tree: Dict
    folder_view: str
    issues: List[Issue]
    github_error: str | None = None

