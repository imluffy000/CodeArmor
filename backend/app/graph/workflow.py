"""Compile the review graph.

Built lazily and cached: constructing it at import time means any error in an
agent module takes down the whole service at boot, including /health.
"""
from functools import lru_cache

from app.graph.edges import configure_edges
from app.graph.nodes import NODE_FUNCTIONS
from app.models.state import PRState


@lru_cache(maxsize=1)
def get_graph():
    from langgraph.graph import StateGraph

    workflow = StateGraph(PRState)
    for node_name, node_fn in NODE_FUNCTIONS.items():
        workflow.add_node(node_name, node_fn)
    configure_edges(workflow)
    return workflow.compile()
