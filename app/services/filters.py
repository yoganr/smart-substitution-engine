"""Hard filters — eliminate ineligible candidates before scoring.

Implements the rules from HACKATHON.md:

    | Active products only   | is_active == true                       |
    | Sufficient stock       | stock_quantity >= requested_quantity    |
    | Compatible category    | category_id matches or is compatible    |
    | Not same product       | id != requested_product.id              |
    | Acceptable price        | price increase within threshold        |

Category compatibility uses the precomputed semantic similarity so a
closely-related product from a neighbouring category can still qualify.
"""

from __future__ import annotations

from typing import Optional, Sequence

from app.config import Settings
from app.schemas import CandidateProduct, ContractItem, RejectedCandidate, RequestedProduct
from app.services.scoring import effective_price


def _candidate_effective_price(
    candidate: CandidateProduct, contract_lookup: dict[str, ContractItem]
) -> float:
    contract_price = candidate.contract_price
    if contract_price is None and candidate.id in contract_lookup:
        contract_price = contract_lookup[candidate.id].contract_price
    return effective_price(candidate.base_price, contract_price)


def apply_hard_filters(
    requested: RequestedProduct,
    candidates: Sequence[CandidateProduct],
    *,
    requested_quantity: float,
    requested_effective_price: float,
    category_similarities: dict[str, float],
    contract_lookup: dict[str, ContractItem],
    settings: Settings,
) -> tuple[list[CandidateProduct], list[RejectedCandidate]]:
    """Partition candidates into (accepted, rejected-with-reasons)."""
    accepted: list[CandidateProduct] = []
    rejected: list[RejectedCandidate] = []

    price_ceiling: Optional[float] = (
        requested_effective_price * (1.0 + settings.max_price_increase_pct)
        if requested_effective_price > 0
        else None
    )

    for cand in candidates:
        reasons: list[str] = []

        if cand.id == requested.id:
            reasons.append("same_product")
        if not cand.is_active:
            reasons.append("inactive")
        if cand.stock_quantity < requested_quantity:
            reasons.append("insufficient_stock")

        # Category compatibility.
        if cand.category_id != requested.category_id:
            sim = category_similarities.get(cand.id, 0.0)
            if not settings.allow_cross_category:
                reasons.append("incompatible_category")
            elif sim < settings.category_semantic_threshold:
                reasons.append(f"incompatible_category(sim={sim:.2f})")

        # Acceptable price.
        if price_ceiling is not None:
            cand_price = _candidate_effective_price(cand, contract_lookup)
            if cand_price > price_ceiling:
                reasons.append("price_too_high")

        if reasons:
            rejected.append(RejectedCandidate(id=cand.id, name=cand.name, reasons=reasons))
        else:
            accepted.append(cand)

    return accepted, rejected
