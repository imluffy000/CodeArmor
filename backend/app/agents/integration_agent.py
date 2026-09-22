"""The integration specialist agent - the "will this break anything on merge?" pass.

Unlike the other five, this agent does not reason from the diff alone. Integration
questions are about the relationship between the change and code the diff does not
contain, so `integration_context_service` computes the facts deterministically
first (removed routes, dependency deltas, risky migrations, CI state, base drift)
and this agent judges the consequences.
"""
from app.core.telemetry import agent_span
from app.services.integration_context_service import summarise_for_prompt
from app.services.llm_service import review_diff


async def integration_agent(state) -> dict:
    context = state.get("integration_context") or {}

    if not context:
        with agent_span("integration") as span:
            span.status = "skipped"
            span.error = "no_integration_facts"
        # Without the facts this agent would be guessing, and a guessed
        # "breaking API change" is worse than no finding at all.
        return {
            "integration_issues": [],
            "agent_errors": [
                {
                    "agent": "integration",
                    "error": "integration facts unavailable, so merge-readiness was not assessed",
                }
            ],
            "dropped_findings": 0,
        }

    with agent_span("integration") as span:
        result = await review_diff(
            "integration",
            "INTEGRATION",
            state["agent_diff"],
            review_context=state.get("review_context", ""),
            extra_context=summarise_for_prompt(context),
            span=span,
        )

    return {
        "integration_issues": result.issues,
        "agent_errors": [{"agent": "integration", "error": result.error}]
        if result.error
        else [],
        "dropped_findings": result.dropped,
        "injection_suspected": result.injection_suspected,
    }
