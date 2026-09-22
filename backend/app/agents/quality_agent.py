"""The code quality specialist agent."""
from app.core.telemetry import agent_span
from app.services.llm_service import review_diff


async def quality_agent(state) -> dict:
    with agent_span("quality") as span:
        result = await review_diff(
            "quality",
            "QUALITY",
            state["agent_diff"],
            review_context=state.get("review_context", ""),
            span=span,
        )

    return {
        "quality_issues": result.issues,
        "agent_errors": [{"agent": "quality", "error": result.error}] if result.error else [],
        "dropped_findings": result.dropped,
        "injection_suspected": result.injection_suspected,
    }
