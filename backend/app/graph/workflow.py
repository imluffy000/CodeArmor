from langgraph.graph import StateGraph

from app.graph.edges import configure_edges
from app.graph.nodes import NODE_FUNCTIONS
from app.models.state import PRState

workflow = StateGraph(PRState)

for node_name, node_fn in NODE_FUNCTIONS.items():
    workflow.add_node(node_name, node_fn)

configure_edges(workflow)

graph = workflow.compile()
