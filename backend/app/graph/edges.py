"""Graph topology: fan out to every specialist, then converge on the summary."""
from app.graph.nodes import FAN_IN_NODE, SPECIALIST_NODES


def configure_edges(workflow) -> None:
    from langgraph.graph import END, START

    for name in SPECIALIST_NODES:
        # START -> every specialist gives six concurrent branches.
        workflow.add_edge(START, name)
        # Every specialist -> summary makes summary wait for all six.
        workflow.add_edge(name, FAN_IN_NODE)

    workflow.add_edge(FAN_IN_NODE, END)
