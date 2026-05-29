"""Shared state object threaded through the LangGraph workflow."""

from __future__ import annotations

from typing import TypedDict

from app.schemas import (
    CandidateProduct,
    ContractItem,
    RejectedCandidate,
    ReplacementRequest,
    ReplacementResponse,
)
from app.services.scoring import ScoredCandidate


class GraphState(TypedDict, total=False):
    # --- Input ---
    request: ReplacementRequest

    # --- Derived during validation ---
    contract_lookup: dict[str, ContractItem]
    requested_effective_price: float
    warnings: list[str]

    # --- Filtering ---
    category_similarities: dict[str, float]
    accepted: list[CandidateProduct]
    rejected: list[RejectedCandidate]

    # --- Scoring & ranking ---
    scored: list[ScoredCandidate]
    ranked: list[ScoredCandidate]

    # --- Output ---
    response: ReplacementResponse
