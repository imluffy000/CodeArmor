from app.services.llm_service import review_diff


async def architecture_agent(state):
    issues = await review_diff("architecture", state["diff"])
    return {"architecture_issues": issues}
