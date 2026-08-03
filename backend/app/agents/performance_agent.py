from app.services.llm_service import review_diff


async def performance_agent(state):
    issues = await review_diff("performance", state["diff"])
    return {"performance_issues": issues}
