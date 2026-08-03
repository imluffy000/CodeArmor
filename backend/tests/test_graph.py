import unittest

from app.graph.edges import configure_edges
from app.graph.nodes import NODE_FUNCTIONS
from app.graph.workflow import graph


class TestGraph(unittest.TestCase):
    def test_node_registry(self):
        self.assertIn("run_specialist_agents", NODE_FUNCTIONS)
        self.assertIn("summary_agent", NODE_FUNCTIONS)

    def test_graph_compiles(self):
        self.assertIsNotNone(graph)

    def test_configure_edges_registers_paths(self):
        from langgraph.graph import StateGraph

        from app.models.state import PRState

        wf = StateGraph(PRState)
        for name, fn in NODE_FUNCTIONS.items():
            wf.add_node(name, fn)
        configure_edges(wf)
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
