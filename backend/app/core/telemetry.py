"""Tracing and cost accounting for a review.

A review is six model calls costing real money, and when one produces a wrong
answer there is nothing to inspect afterwards unless it was recorded at the
time. This module records it: one trace per review, one span per agent, with
latency, token counts, cost, and how the output parsed.

Deliberately in-process and dependency-free. The span interface mirrors
OpenTelemetry closely enough that swapping in a real exporter later is a change
to this file rather than to every call site.
"""
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.core.logging import logger

# Per-million-token prices, USD. OpenRouter usually returns the real cost in
# response metadata; this is the fallback so a missing field degrades to an
# estimate rather than to zero, which would read as "this review was free".
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "deepseek/deepseek-chat-v3-0324": (0.28, 0.88),
    "deepseek/deepseek-chat": (0.28, 0.88),
    "anthropic/claude-sonnet-4": (3.00, 15.00),
    "anthropic/claude-3.5-haiku": (0.80, 4.00),
    "openai/gpt-4o": (2.50, 10.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "google/gemini-2.0-flash-001": (0.10, 0.40),
    "meta-llama/llama-3.3-70b-instruct": (0.12, 0.30),
}

DEFAULT_PRICE = (0.50, 1.50)


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = MODEL_PRICES.get(model, DEFAULT_PRICE)
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


@dataclass
class Span:
    """One unit of traced work - usually a single agent's model call."""

    name: str
    kind: str = "agent"
    status: str = "ok"  # ok | error | timeout | skipped
    started_at: float = field(default_factory=time.monotonic)
    duration_ms: int = 0

    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cost_is_estimate: bool = True

    # Output quality, which is what makes a bad review attributable later.
    findings: int = 0
    dropped: int = 0
    parse_status: str | None = None  # ok | unparseable | empty
    error: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def record_usage(self, response: Any, model: str) -> None:
        """Pull token counts and cost off a LangChain response.

        Shapes differ across providers and versions, so every read is defensive:
        losing a trace must never fail a review.
        """
        self.model = model
        try:
            usage = getattr(response, "usage_metadata", None) or {}
            self.tokens_in = int(usage.get("input_tokens") or 0)
            self.tokens_out = int(usage.get("output_tokens") or 0)

            metadata = getattr(response, "response_metadata", None) or {}
            if not (self.tokens_in or self.tokens_out):
                raw = metadata.get("token_usage") or metadata.get("usage") or {}
                self.tokens_in = int(raw.get("prompt_tokens") or 0)
                self.tokens_out = int(raw.get("completion_tokens") or 0)

            # OpenRouter reports the price it actually charged.
            reported = metadata.get("cost")
            if reported is None:
                reported = (metadata.get("usage") or {}).get("cost")
            if reported is not None:
                self.cost_usd = float(reported)
                self.cost_is_estimate = False
            else:
                self.cost_usd = estimate_cost(model, self.tokens_in, self.tokens_out)
                self.cost_is_estimate = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Could not read usage from the model response: %s", exc)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "cost_is_estimate": self.cost_is_estimate,
            "findings": self.findings,
            "dropped": self.dropped,
            "parse_status": self.parse_status,
            "error": self.error,
            **({"attributes": self.attributes} if self.attributes else {}),
        }


@dataclass
class Trace:
    """Everything recorded about one review."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    started_at: float = field(default_factory=time.monotonic)
    spans: list[Span] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    @contextmanager
    def span(self, name: str, kind: str = "agent") -> Iterator[Span]:
        span = Span(name=name, kind=kind)
        self.spans.append(span)
        try:
            yield span
        except Exception as exc:
            span.status = "error"
            span.error = type(exc).__name__
            raise
        finally:
            span.duration_ms = int((time.monotonic() - span.started_at) * 1000)

    # --- rollups ---------------------------------------------------------

    @property
    def duration_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    @property
    def total_tokens_in(self) -> int:
        return sum(s.tokens_in for s in self.spans)

    @property
    def total_tokens_out(self) -> int:
        return sum(s.tokens_out for s in self.spans)

    @property
    def total_cost_usd(self) -> float:
        return sum(s.cost_usd for s in self.spans)

    @property
    def failed_spans(self) -> list[Span]:
        return [s for s in self.spans if s.status != "ok"]

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "duration_ms": self.duration_ms,
            "model_calls": len([s for s in self.spans if s.model]),
            "tokens_in": self.total_tokens_in,
            "tokens_out": self.total_tokens_out,
            "cost_usd": round(self.total_cost_usd, 6),
            "cost_is_estimate": any(s.cost_is_estimate for s in self.spans if s.model),
            "spans": [s.to_dict() for s in self.spans],
            **({"attributes": self.attributes} if self.attributes else {}),
        }

    def log_summary(self) -> None:
        logger.info(
            "trace=%s finished in %sms: %s model call(s), %s in / %s out tokens, "
            "$%.4f%s, %s failed span(s)",
            self.trace_id,
            self.duration_ms,
            len([s for s in self.spans if s.model]),
            self.total_tokens_in,
            self.total_tokens_out,
            self.total_cost_usd,
            " (estimated)" if any(s.cost_is_estimate for s in self.spans if s.model) else "",
            len(self.failed_spans),
        )


class CostCeilingExceeded(RuntimeError):
    """A review hit its spend limit before finishing."""


def check_cost_ceiling(trace: Trace, ceiling_usd: float) -> None:
    """Abort a runaway review.

    A 500-file pull request costs the same as a typo fix unless something
    stops it, and nobody finds out until the invoice.
    """
    if ceiling_usd > 0 and trace.total_cost_usd > ceiling_usd:
        raise CostCeilingExceeded(
            f"This review reached its ${ceiling_usd:.2f} cost ceiling "
            f"(spent ${trace.total_cost_usd:.4f})."
        )


# The trace for the review running on this task. Set once by the orchestrator;
# every agent reads it. asyncio.create_task copies the context, so the parallel
# branches all see the same object.
current_trace: ContextVar["Trace | None"] = ContextVar("current_trace", default=None)


def get_trace() -> "Trace | None":
    return current_trace.get()


@contextmanager
def agent_span(name: str, kind: str = "agent") -> Iterator[Span]:
    """Open a span on the current trace, or a throwaway one if untraced.

    Untraced is the normal case in tests and in the eval harness, and an agent
    should not need to know the difference.
    """
    trace = current_trace.get()
    if trace is None:
        span = Span(name=name, kind=kind)
        started = time.monotonic()
        try:
            yield span
        finally:
            span.duration_ms = int((time.monotonic() - started) * 1000)
        return

    with trace.span(name, kind) as span:
        yield span
