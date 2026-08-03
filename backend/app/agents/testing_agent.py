from app.services.llm_service import review_diff


async def testing_agent(state):
    issues = await review_diff("testing", state["diff"])
    return {"testing_issues": issues}
