"""The single finding type produced by every agent and static-analysis runner.

Severity and category are constrained enums. An LLM will reach for words like
"warning" or "info" no matter how firmly the prompt says otherwise, so the
validators normalise known synonyms instead of rejecting the finding - but
anything unrecognised is rejected, because an unknown severity silently falls
out of every histogram and score downstream.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.constants import (
    CATEGORY_ALIASES,
    SEVERITY_ALIASES,
    SEVERITY_ORDER,
    SUPPORTED_CATEGORIES,
    SUPPORTED_SEVERITIES,
)

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Category = Literal[
    "SECURITY", "QUALITY", "PERFORMANCE", "TESTING", "ARCHITECTURE", "INTEGRATION"
]

MAX_TEXT = 4000
MAX_SNIPPET = 8000


class Issue(BaseModel):
    file: str = Field(max_length=1024)
    severity: Severity
    category: Category
    issue: str = Field(max_length=MAX_TEXT)
    suggestion: str = Field(max_length=MAX_TEXT)
    code_snippet: str | None = Field(default=None, max_length=MAX_SNIPPET)
    suggestion_snippet: str | None = Field(default=None, max_length=MAX_SNIPPET)
    # Line in the PR's new file, when the agent could identify one. Needed for
    # inline PR comments and for location-based deduplication.
    line: int | None = Field(default=None, ge=0)
    # How many independent agents raised substantively the same finding.
    # 1 for a fresh finding; raised by the reconcile step.
    agreement: int = Field(default=1, ge=1)
    # Set by the reconcile step when several categories describe one problem.
    also_reported_as: list[Category] = Field(default_factory=list)

    @field_validator("severity", mode="before")
    @classmethod
    def _normalise_severity(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip().upper()
        if text in SEVERITY_ORDER:
            return text
        if text in SEVERITY_ALIASES:
            return SEVERITY_ALIASES[text]
        raise ValueError(
            f"severity must be one of {SUPPORTED_SEVERITIES}, got {value!r}"
        )

    @field_validator("category", mode="before")
    @classmethod
    def _normalise_category(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip().upper()
        if text in SUPPORTED_CATEGORIES:
            return text
        if text in CATEGORY_ALIASES:
            return CATEGORY_ALIASES[text]
        raise ValueError(
            f"category must be one of {SUPPORTED_CATEGORIES}, got {value!r}"
        )

    @field_validator("file", "issue", "suggestion", mode="before")
    @classmethod
    def _require_text(cls, value: object) -> object:
        if value is None:
            raise ValueError("field is required and cannot be null")
        if not isinstance(value, str):
            return str(value)
        return value.strip()

    @field_validator("code_snippet", "suggestion_snippet", mode="before")
    @classmethod
    def _coerce_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            # Models sometimes return a snippet as a list of lines.
            return "\n".join(str(part) for part in value)
        if not isinstance(value, str):
            return str(value)
        return value

    @property
    def severity_rank(self) -> int:
        """Higher is worse. Used for ordering and for gating."""
        return SEVERITY_ORDER.get(self.severity, 0)

    @property
    def is_blocking(self) -> bool:
        return self.severity in ("HIGH", "CRITICAL")
