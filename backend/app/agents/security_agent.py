from app.services.llm_service import review_diff


async def security_agent(state):
    issues = await review_diff("security", state["diff"])
    return {"security_issues": issues}
