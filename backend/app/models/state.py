"""The state the review graph carries.

The six specialist agents run as genuine parallel graph nodes, so every field
more than one of them writes needs a reducer. Without `Annotated[..., add]`,
LangGraph raises `InvalidUpdateError: Can receive only one value per step` the
moment two branches write the same key - which is exactly what `agent_errors`
and `dropped_findings` do.
"""
import operator
from typing import Annotated, TypedDict

from app.models.issue import Issue


def _or_reducer(left: bool, right: bool) -> bool:
    return bool(left) or bool(right)


class PRState(TypedDict, total=False):
    # --- inputs ---
    pr_url: str
    diff: str
    # The budgeted, per-file assembled diff the agents actually read.
    agent_diff: str
    # Human-readable PR/repo context prepended to every specialist prompt.
    review_context: str
    # Deterministic integration facts (see integration_context_service).
    integration_context: dict
    # How much of the diff made it into agent_diff.
    coverage: dict
    parsed_files: list

    # --- per-agent findings, one writer each ---
    security_issues: list[Issue]
    quality_issues: list[Issue]
    performance_issues: list[Issue]
    testing_issues: list[Issue]
    architecture_issues: list[Issue]
    integration_issues: list[Issue]

    # --- written by several agents in the same step ---
    agent_errors: Annotated[list[dict], operator.add]
    dropped_findings: Annotated[int, operator.add]
    injection_suspected: Annotated[bool, _or_reducer]

    # --- outputs ---
    all_issues: list[Issue]
    folder_tree: dict
    merge_readiness: dict
    final_summary: str
