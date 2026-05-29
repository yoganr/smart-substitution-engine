"""Builds and compiles the LangGraph state machine.

    validate_input
          │
    apply_hard_filters
          │  (conditional)
          ├── no survivors ─────────────┐
          ▼                             │
    score_candidates                    │
          │                             │
    rank_replacements                   │
          │                             │
    generate_ollama_explanations        │
          │                             │
          ▼                             ▼
    return_result ◄─────────────────────┘
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.graph.nodes import RecommendationNodes, has_accepted_candidates
from app.graph.state import GraphState
from app.services.explanation import ExplanationService
from app.services.similarity import SimilarityService


def build_workflow(
    settings: Settings,
    similarity: SimilarityService,
    explainer: ExplanationService,
):
    """Construct and compile the recommendation workflow graph."""
    nodes = RecommendationNodes(settings, similarity, explainer)

    graph = StateGraph(GraphState)
    graph.add_node("validate_input", nodes.validate_input)
    graph.add_node("apply_hard_filters", nodes.apply_hard_filters)
    graph.add_node("score_candidates", nodes.score_candidates)
    graph.add_node("rank_replacements", nodes.rank_replacements)
    graph.add_node("generate_ollama_explanations", nodes.generate_explanations)
    graph.add_node("return_result", nodes.return_result)

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "apply_hard_filters")
    graph.add_conditional_edges(
        "apply_hard_filters",
        has_accepted_candidates,
        {"score": "score_candidates", "empty": "return_result"},
    )
    graph.add_edge("score_candidates", "rank_replacements")
    graph.add_edge("rank_replacements", "generate_ollama_explanations")
    graph.add_edge("generate_ollama_explanations", "return_result")
    graph.add_edge("return_result", END)

    return graph.compile()
