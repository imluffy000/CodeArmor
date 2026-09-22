"""The performance and efficiency specialist agent."""
from app.core.telemetry import agent_span
from app.services.llm_service import review_diff


async def performance_agent(state) -> dict:
    with agent_span("performance") as span:
        result = await review_diff(
            "performance",
            "PERFORMANCE",
            state["agent_diff"],
            review_context=state.get("review_context", ""),
            span=span,
        )

    return {
        "performance_issues": result.issues,
        "agent_errors": [{"agent": "performance", "error": result.error}] if result.error else [],
        "dropped_findings": result.dropped,
        "injection_suspected": result.injection_suspected,
    }
