from app.services.llm_service import review_diff


async def quality_agent(state):
    issues = await review_diff("quality", state["diff"])
    return {"quality_issues": issues}
