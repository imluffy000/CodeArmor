"""The architecture and design specialist agent."""
from app.services.llm_service import review_diff


async def architecture_agent(state) -> dict:
    result = await review_diff(
        "architecture",
        "ARCHITECTURE",
        state["agent_diff"],
        review_context=state.get("review_context", ""),
    )
    return {
        "architecture_issues": result.issues,
        "agent_errors": [{"agent": "architecture", "error": result.error}] if result.error else [],
        "dropped_findings": result.dropped,
        "injection_suspected": result.injection_suspected,
    }
