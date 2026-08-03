from typing import TypedDict
from typing import List

from app.models.issue import Issue


class PRState(TypedDict):

    pr_url: str

    diff: str

    parsed_files: list

    security_issues: List[Issue]

    quality_issues: List[Issue]

    performance_issues: List[Issue]

    testing_issues: List[Issue]

    architecture_issues: List[Issue]

    all_issues: List[Issue]

    folder_tree: dict

    final_summary: str