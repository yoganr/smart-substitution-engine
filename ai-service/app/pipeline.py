from langgraph.graph import StateGraph, END

from .state import RecommendationState
from .nodes import (
    validate_input,
    apply_hard_filters,
    score_candidates,
    rank_replacements,
    generate_ollama_explanations,
    return_result,
)


def build_pipeline() -> StateGraph:
    graph = StateGraph(RecommendationState)

    graph.add_node("validate_input", validate_input)
    graph.add_node("apply_hard_filters", apply_hard_filters)
    graph.add_node("score_candidates", score_candidates)
    graph.add_node("rank_replacements", rank_replacements)
    graph.add_node("generate_ollama_explanations", generate_ollama_explanations)
    graph.add_node("return_result", return_result)

    graph.set_entry_point("validate_input")
    graph.add_edge("validate_input", "apply_hard_filters")
    graph.add_edge("apply_hard_filters", "score_candidates")
    graph.add_edge("score_candidates", "rank_replacements")
    graph.add_edge("rank_replacements", "generate_ollama_explanations")
    graph.add_edge("generate_ollama_explanations", "return_result")
    graph.add_edge("return_result", END)

    return graph.compile()


# Module-level compiled pipeline, built once at import time
recommendation_pipeline = build_pipeline()
