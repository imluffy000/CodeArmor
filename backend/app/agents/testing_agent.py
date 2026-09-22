"""The testing specialist agent."""
from app.services.llm_service import review_diff


async def testing_agent(state) -> dict:
    result = await review_diff(
        "testing",
        "TESTING",
        state["agent_diff"],
        review_context=state.get("review_context", ""),
    )
    return {
        "testing_issues": result.issues,
        "agent_errors": [{"agent": "testing", "error": result.error}] if result.error else [],
        "dropped_findings": result.dropped,
        "injection_suspected": result.injection_suspected,
    }
