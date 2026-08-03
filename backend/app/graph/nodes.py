import asyncio
import os

from app.core.logging import logger
from app.agents.architecture_agent import architecture_agent
from app.agents.performance_agent import performance_agent
from app.agents.quality_agent import quality_agent
from app.agents.security_agent import security_agent
from app.agents.summary_agent import summary_agent
from app.agents.testing_agent import testing_agent
from app.static_analysis.bandit_runner import run_bandit
from app.static_analysis.pylint_runner import run_pylint
from app.static_analysis.semgrep_runner import run_semgrep
from app.visualizer.issue_mapper import (
    map_bandit_results,
    map_pylint_results,
    map_semgrep_results,
)

SPECIALIST_AGENTS = [
    security_agent,
    quality_agent,
    performance_agent,
    testing_agent,
    architecture_agent,
]


async def run_specialist_agents(state):
    results = await asyncio.gather(
        *[agent(state) for agent in SPECIALIST_AGENTS],
        return_exceptions=True
    )

    merged = {}
    errors = []
    for agent_fn, res in zip(SPECIALIST_AGENTS, results):
        if isinstance(res, Exception):
            logger.warning("Agent %s failed: %s", agent_fn.__name__, res)
            errors.append(f"{agent_fn.__name__}: {res}")
        else:
            merged.update(res)

    if len(errors) == len(SPECIALIST_AGENTS):
        raise RuntimeError(f"All specialist agents failed: {', '.join(errors)}")

    static_root = os.environ.get("STATIC_ANALYSIS_ROOT")
    if static_root:
        merged["security_issues"] = (
            list(merged.get("security_issues", []))
            + map_semgrep_results(run_semgrep(static_root))
            + map_bandit_results(run_bandit(static_root))
        )
        merged["quality_issues"] = (
            list(merged.get("quality_issues", []))
            + map_pylint_results(run_pylint(static_root))
        )

    return merged


NODE_FUNCTIONS = {
    "run_specialist_agents": run_specialist_agents,
    "summary_agent": summary_agent,
}
