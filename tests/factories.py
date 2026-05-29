"""Convenience builders for test fixtures."""

from __future__ import annotations

from typing import Optional

from app.schemas import (
    CandidateProduct,
    Company,
    ContractItem,
    ReplacementRequest,
    RequestedProduct,
)


def make_company(**kw) -> Company:
    return Company(**{"id": "company_001", "name": "ABC Restaurant", **kw})


def make_requested(**kw) -> RequestedProduct:
    base = dict(
        id="product_001",
        name="Chicken Breast 2kg",
        category_id="cat_chicken",
        brand="Brand A",
        unit="kg",
        pack_size=2,
        base_price=10.0,
    )
    base.update(kw)
    return RequestedProduct(**base)


def make_candidate(**kw) -> CandidateProduct:
    base = dict(
        id="product_2033",
        name="Chicken Breast Premium 2kg",
        category_id="cat_chicken",
        brand="Brand B",
        unit="kg",
        pack_size=2,
        base_price=10.5,
        stock_quantity=150,
        contract_price=None,
        is_active=True,
    )
    base.update(kw)
    return CandidateProduct(**base)


def make_request(
    candidates: Optional[list[CandidateProduct]] = None,
    contract_items: Optional[list[ContractItem]] = None,
    **kw,
) -> ReplacementRequest:
    base = dict(
        company=make_company(),
        requested_product=make_requested(),
        requested_quantity=20,
        contract_items=contract_items or [],
        candidate_products=[make_candidate()] if candidates is None else candidates,
        max_results=3,
        use_ai_explanation=False,
    )
    base.update(kw)
    return ReplacementRequest(**base)
