"""
LangGraph pipeline.

Flow:
  fetch → rag → review → critic
    ├─ score >= threshold → selector → END
    └─ score <  threshold → branch → critic_branch → selector → END
"""
from langgraph.graph import StateGraph, END

from backend.graph.state import PRCriticState
from backend.agents.fetch_agent import fetch_agent
from backend.agents.rag_agent import rag_agent
from backend.agents.review_agent import review_agent
from backend.agents.critic_agent import critic_agent
from backend.agents.branch_agent import branch_agent
from backend.agents.selector_agent import selector_agent


def _route_after_critic(state: PRCriticState) -> str:
    return "branch" if state.get("trigger_branch", False) else "selector"


def _route_after_branch_critic(state: PRCriticState) -> str:
    return "selector"


def build_graph() -> StateGraph:
    g = StateGraph(PRCriticState)

    g.add_node("fetch",         fetch_agent)
    g.add_node("rag",           rag_agent)
    g.add_node("review",        review_agent)
    g.add_node("critic",        critic_agent)
    g.add_node("branch",        branch_agent)
    g.add_node("critic_branch", critic_agent)   # same fn, different node
    g.add_node("selector",      selector_agent)

    g.set_entry_point("fetch")
    g.add_edge("fetch",  "rag")
    g.add_edge("rag",    "review")
    g.add_edge("review", "critic")

    g.add_conditional_edges("critic", _route_after_critic,
                            {"branch": "branch", "selector": "selector"})

    g.add_edge("branch", "critic_branch")
    g.add_conditional_edges("critic_branch", _route_after_branch_critic,
                            {"selector": "selector"})

    g.add_edge("selector", END)
    return g.compile()


compiled_graph = build_graph()