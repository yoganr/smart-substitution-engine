"""Compiles the chat state machine: orchestrator → specialist agent → END.

    START
      │
    orchestrate            (classify intent + extract slots)
      │  (conditional on state["intent"])
      ├── guide ───────────┐
      ├── substitution ────┤
      ├── similar ─────────┤
      ├── product_info ────┤
      └── refusal ─────────┘
                           ▼
                          END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.chat.state import (
    INTENT_FIND_REPLACEMENT,
    INTENT_GUIDE,
    INTENT_OFF_TOPIC,
    INTENT_PRODUCT_INFO,
    INTENT_SIMILAR,
    INTENT_STOCK_OVERVIEW,
    ChatState,
)

_ROUTES = {
    INTENT_GUIDE: "guide",
    INTENT_FIND_REPLACEMENT: "substitution",
    INTENT_SIMILAR: "similar",
    INTENT_PRODUCT_INFO: "product_info",
    INTENT_STOCK_OVERVIEW: "stock_overview",
    INTENT_OFF_TOPIC: "refusal",
}


def _route(state: ChatState) -> str:
    return state.get("intent", INTENT_GUIDE)


def build_chat_graph(orchestrator, agents):
    """Wire the orchestrator + agents into a compiled LangGraph."""
    graph = StateGraph(ChatState)
    graph.add_node("orchestrate", orchestrator)
    graph.add_node("guide", agents.guide)
    graph.add_node("substitution", agents.substitution)
    graph.add_node("similar", agents.similar)
    graph.add_node("product_info", agents.product_info)
    graph.add_node("stock_overview", agents.stock_overview)
    graph.add_node("refusal", agents.refusal)

    graph.add_edge(START, "orchestrate")
    graph.add_conditional_edges("orchestrate", _route, _ROUTES)
    for node in ("guide", "substitution", "similar", "product_info", "stock_overview", "refusal"):
        graph.add_edge(node, END)

    return graph.compile()
