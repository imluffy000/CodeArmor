"""The code quality specialist agent."""
from app.services.llm_service import review_diff


async def quality_agent(state) -> dict:
    result = await review_diff(
        "quality",
        "QUALITY",
        state["agent_diff"],
        review_context=state.get("review_context", ""),
    )
    return {
        "quality_issues": result.issues,
        "agent_errors": [{"agent": "quality", "error": result.error}] if result.error else [],
        "dropped_findings": result.dropped,
        "injection_suspected": result.injection_suspected,
    }
