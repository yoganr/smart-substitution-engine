"""Deterministic scoring of replacement candidates.

This module is the heart of the engine and is intentionally free of any I/O so
it is fully deterministic and trivially unit-testable. Semantic similarity is
computed elsewhere and injected as a plain float.

Scoring dimensions (default max points, total 93):
    category_similarity   30
    contract_match        25
    price_similarity      20
    stock_availability    10
    unit_pack_similarity    8
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.config import Settings
from app.schemas import CandidateProduct, ContractItem, RequestedProduct, ScoreBreakdown


def effective_price(base_price: float, contract_price: Optional[float]) -> float:
    """The price actually paid: contract price when present, else base price."""
    return contract_price if contract_price is not None else base_price


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# --- Per-dimension factors (each returns a fraction in [0, 1]) ------------
def price_factor(requested_price: float, candidate_price: float, max_increase_pct: float) -> float:
    """1.0 when candidate is equal/cheaper, decaying linearly to 0 at the
    maximum acceptable price increase."""
    if requested_price <= 0:
        return 1.0
    if candidate_price <= requested_price:
        return 1.0
    if max_increase_pct <= 0:
        return 0.0
    increase = (candidate_price - requested_price) / requested_price
    if increase >= max_increase_pct:
        return 0.0
    return _clamp01(1.0 - increase / max_increase_pct)


def stock_factor(stock_quantity: float, requested_quantity: float) -> float:
    """0.5 when stock exactly meets demand, scaling to 1.0 at >= 2x demand."""
    if requested_quantity <= 0:
        return 1.0
    ratio = stock_quantity / requested_quantity
    if ratio < 1.0:
        # Should be filtered out earlier; degrade gracefully just in case.
        return _clamp01(0.5 * ratio)
    return _clamp01(0.5 + 0.5 * (ratio - 1.0))


def unit_pack_factor(requested: RequestedProduct, candidate: CandidateProduct) -> float:
    """Reward matching unit-of-measure and pack size."""
    req_unit = (requested.unit or "").strip().lower()
    cand_unit = (candidate.unit or "").strip().lower()

    if not req_unit or not cand_unit:
        return 0.6  # unknown unit on either side — neutral-positive
    if req_unit != cand_unit:
        return 0.0  # different unit of measure — not directly comparable

    if requested.pack_size is None or candidate.pack_size is None:
        return 0.8  # same unit, unknown pack size
    if requested.pack_size == candidate.pack_size:
        return 1.0
    if requested.pack_size <= 0 or candidate.pack_size <= 0:
        return 0.8
    ratio = min(requested.pack_size, candidate.pack_size) / max(
        requested.pack_size, candidate.pack_size
    )
    return _clamp01(0.5 + 0.5 * ratio)


# --- Computed facts (shared with the explanation layer) -------------------
class CandidateFacts(BaseModel):
    same_category: bool
    category_similarity: float
    is_under_contract: bool
    is_preferred: bool
    requested_effective_price: float
    candidate_effective_price: float
    price_delta_pct: float
    cheaper_or_equal: bool
    stock_ratio: float
    same_unit: bool
    same_pack: bool


class ScoredCandidate(BaseModel):
    candidate: CandidateProduct
    breakdown: ScoreBreakdown
    final_score: int
    facts: CandidateFacts
    explanation: str = ""
    explanation_source: str = "template"


def build_contract_lookup(contract_items: list[ContractItem]) -> dict[str, ContractItem]:
    return {item.product_id: item for item in contract_items}


def score_candidate(
    requested: RequestedProduct,
    candidate: CandidateProduct,
    *,
    category_similarity: float,
    requested_effective_price: float,
    contract_lookup: dict[str, ContractItem],
    requested_quantity: float,
    settings: Settings,
) -> ScoredCandidate:
    """Score a single candidate, returning its breakdown, total and facts."""
    # --- Contract status ---
    contract_item = contract_lookup.get(candidate.id)
    candidate_contract_price = candidate.contract_price
    if candidate_contract_price is None and contract_item is not None:
        candidate_contract_price = contract_item.contract_price
    is_preferred = bool(contract_item and contract_item.is_preferred)
    is_under_contract = candidate_contract_price is not None or contract_item is not None

    # --- Prices ---
    candidate_price = effective_price(candidate.base_price, candidate_contract_price)
    price_delta_pct = (
        (candidate_price - requested_effective_price) / requested_effective_price
        if requested_effective_price > 0
        else 0.0
    )

    # --- Factors -> points ---
    category_points = settings.w_category * _clamp01(category_similarity)

    if is_preferred:
        contract_points = settings.w_contract
    elif is_under_contract:
        contract_points = settings.w_contract * 0.7
    else:
        contract_points = 0.0

    price_points = settings.w_price * price_factor(
        requested_effective_price, candidate_price, settings.max_price_increase_pct
    )
    stock_points = settings.w_stock * stock_factor(candidate.stock_quantity, requested_quantity)
    unit_pack_points = settings.w_unit_pack * unit_pack_factor(requested, candidate)

    breakdown = ScoreBreakdown(
        category_similarity=round(category_points),
        contract_match=round(contract_points),
        price_similarity=round(price_points),
        stock_availability=round(stock_points),
        unit_pack_similarity=round(unit_pack_points),
    )
    final_score = (
        breakdown.category_similarity
        + breakdown.contract_match
        + breakdown.price_similarity
        + breakdown.stock_availability
        + breakdown.unit_pack_similarity
    )

    req_unit = (requested.unit or "").strip().lower()
    cand_unit = (candidate.unit or "").strip().lower()
    facts = CandidateFacts(
        same_category=candidate.category_id == requested.category_id,
        category_similarity=round(_clamp01(category_similarity), 3),
        is_under_contract=is_under_contract,
        is_preferred=is_preferred,
        requested_effective_price=round(requested_effective_price, 2),
        candidate_effective_price=round(candidate_price, 2),
        price_delta_pct=round(price_delta_pct, 4),
        cheaper_or_equal=candidate_price <= requested_effective_price,
        stock_ratio=round(candidate.stock_quantity / requested_quantity, 2)
        if requested_quantity > 0
        else 0.0,
        same_unit=bool(req_unit) and req_unit == cand_unit,
        same_pack=requested.pack_size is not None
        and requested.pack_size == candidate.pack_size,
    )

    return ScoredCandidate(
        candidate=candidate,
        breakdown=breakdown,
        final_score=final_score,
        facts=facts,
    )


def rank_candidates(scored: list[ScoredCandidate], max_results: int) -> list[ScoredCandidate]:
    """Sort by score (desc) with deterministic tie-breakers, then truncate."""
    ranked = sorted(
        scored,
        key=lambda s: (
            s.final_score,
            s.facts.is_preferred,
            s.facts.is_under_contract,
            s.candidate.stock_quantity,
            -s.facts.candidate_effective_price,
        ),
        reverse=True,
    )
    return ranked[:max_results]
