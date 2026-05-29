from typing import TypedDict
from .schemas import (
    ReplacementRequest,
    CandidateProduct,
    Replacement,
    RejectedCandidate,
)


class RecommendationState(TypedDict):
    request: ReplacementRequest
    candidates: list[CandidateProduct]
    rejected: list[RejectedCandidate]
    scored: list[tuple[CandidateProduct, int, dict]]  # (product, score, breakdown)
    replacements: list[Replacement]
    no_candidates_reason: str | None
