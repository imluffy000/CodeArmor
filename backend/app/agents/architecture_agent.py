"""The architecture and design specialist agent."""
from app.core.telemetry import agent_span
from app.services.llm_service import review_diff


async def architecture_agent(state) -> dict:
    with agent_span("architecture") as span:
        result = await review_diff(
            "architecture",
            "ARCHITECTURE",
            state["agent_diff"],
            review_context=state.get("review_context", ""),
            span=span,
        )

    return {
        "architecture_issues": result.issues,
        "agent_errors": [{"agent": "architecture", "error": result.error}] if result.error else [],
        "dropped_findings": result.dropped,
        "injection_suspected": result.injection_suspected,
    }
