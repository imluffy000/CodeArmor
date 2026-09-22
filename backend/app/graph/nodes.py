"""The graph's nodes: six specialist reviewers plus the fan-in."""
from app.agents.architecture_agent import architecture_agent
from app.agents.integration_agent import integration_agent
from app.agents.performance_agent import performance_agent
from app.agents.quality_agent import quality_agent
from app.agents.security_agent import security_agent
from app.agents.summary_agent import summary_agent
from app.agents.testing_agent import testing_agent

# Each entry becomes a real parallel branch in the graph, so LangGraph - not a
# hand-rolled asyncio.gather hidden inside one node - owns the fan-out. That is
# what makes per-agent progress streaming work without a second orchestrator.
SPECIALIST_NODES = {
    "security": security_agent,
    "quality": quality_agent,
    "performance": performance_agent,
    "testing": testing_agent,
    "architecture": architecture_agent,
    "integration": integration_agent,
}

FAN_IN_NODE = "summary"

NODE_FUNCTIONS = {**SPECIALIST_NODES, FAN_IN_NODE: summary_agent}
