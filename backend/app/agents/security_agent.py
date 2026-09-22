"""The security specialist agent."""
from app.services.llm_service import review_diff


async def security_agent(state) -> dict:
    result = await review_diff(
        "security",
        "SECURITY",
        state["agent_diff"],
        review_context=state.get("review_context", ""),
    )
    return {
        "security_issues": result.issues,
        "agent_errors": [{"agent": "security", "error": result.error}] if result.error else [],
        "dropped_findings": result.dropped,
        "injection_suspected": result.injection_suspected,
    }
