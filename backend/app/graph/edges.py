from langgraph.graph import END


def configure_edges(workflow):
    workflow.set_entry_point("run_specialist_agents")
    workflow.add_edge("run_specialist_agents", "summary_agent")
    workflow.add_edge("summary_agent", END)
