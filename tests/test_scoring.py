"""Unit tests for the deterministic scoring layer."""

from __future__ import annotations

import pytest

from app.services.scoring import (
    build_contract_lookup,
    price_factor,
    rank_candidates,
    score_candidate,
    stock_factor,
    unit_pack_factor,
)
from app.schemas import ContractItem
from tests.factories import make_candidate, make_requested


# --- price_factor -----------------------------------------------------------
def test_price_factor_equal_or_cheaper_is_full():
    assert price_factor(10.0, 10.0, 0.25) == 1.0
    assert price_factor(10.0, 8.0, 0.25) == 1.0


def test_price_factor_decays_linearly_to_threshold():
    # +12.5% with a 25% ceiling -> halfway -> 0.5
    assert price_factor(10.0, 11.25, 0.25) == pytest.approx(0.5)


def test_price_factor_at_or_above_threshold_is_zero():
    assert price_factor(10.0, 12.5, 0.25) == 0.0
    assert price_factor(10.0, 20.0, 0.25) == 0.0


# --- stock_factor -----------------------------------------------------------
def test_stock_factor_meets_demand_is_half():
    assert stock_factor(20, 20) == pytest.approx(0.5)


def test_stock_factor_double_demand_is_full():
    assert stock_factor(40, 20) == 1.0
    assert stock_factor(1000, 20) == 1.0


def test_stock_factor_below_demand_degrades():
    assert stock_factor(10, 20) == pytest.approx(0.25)


# --- unit_pack_factor -------------------------------------------------------
def test_unit_pack_identical_is_full():
    req = make_requested(unit="kg", pack_size=2)
    cand = make_candidate(unit="kg", pack_size=2)
    assert unit_pack_factor(req, cand) == 1.0


def test_unit_pack_different_unit_is_zero():
    req = make_requested(unit="kg")
    cand = make_candidate(unit="lb")
    assert unit_pack_factor(req, cand) == 0.0


def test_unit_pack_same_unit_different_pack_is_partial():
    req = make_requested(unit="kg", pack_size=2)
    cand = make_candidate(unit="kg", pack_size=4)
    factor = unit_pack_factor(req, cand)
    assert 0.5 < factor < 1.0


# --- score_candidate --------------------------------------------------------
def test_perfect_candidate_scores_max(settings):
    """Same category, preferred contract, cheaper, ample stock, same unit/pack."""
    req = make_requested()
    cand = make_candidate(base_price=9.0, contract_price=8.5, stock_quantity=200)
    contract = [ContractItem(product_id=cand.id, contract_price=8.5, is_preferred=True)]
    scored = score_candidate(
        req,
        cand,
        category_similarity=1.0,
        requested_effective_price=10.0,
        contract_lookup=build_contract_lookup(contract),
        requested_quantity=20,
        settings=settings,
    )
    assert scored.breakdown.category_similarity == 30
    assert scored.breakdown.contract_match == 25
    assert scored.breakdown.price_similarity == 20
    assert scored.breakdown.stock_availability == 10
    assert scored.breakdown.unit_pack_similarity == 8
    assert scored.final_score == 93


def test_final_score_always_equals_breakdown_sum(settings):
    req = make_requested()
    cand = make_candidate(base_price=11.5, stock_quantity=25, pack_size=5)
    scored = score_candidate(
        req,
        cand,
        category_similarity=0.7,
        requested_effective_price=10.0,
        contract_lookup={},
        requested_quantity=20,
        settings=settings,
    )
    b = scored.breakdown
    assert scored.final_score == (
        b.category_similarity
        + b.contract_match
        + b.price_similarity
        + b.stock_availability
        + b.unit_pack_similarity
    )


def test_non_contract_candidate_gets_zero_contract_points(settings):
    req = make_requested()
    cand = make_candidate(contract_price=None)
    scored = score_candidate(
        req,
        cand,
        category_similarity=1.0,
        requested_effective_price=10.0,
        contract_lookup={},
        requested_quantity=20,
        settings=settings,
    )
    assert scored.breakdown.contract_match == 0
    assert scored.facts.is_under_contract is False


def test_contracted_but_not_preferred_gets_partial_points(settings):
    req = make_requested()
    cand = make_candidate(contract_price=9.5)
    contract = [ContractItem(product_id=cand.id, contract_price=9.5, is_preferred=False)]
    scored = score_candidate(
        req,
        cand,
        category_similarity=1.0,
        requested_effective_price=10.0,
        contract_lookup=build_contract_lookup(contract),
        requested_quantity=20,
        settings=settings,
    )
    # 0.7 * 25 = 17.5 -> rounds to 18
    assert scored.breakdown.contract_match == 18
    assert scored.facts.is_preferred is False


# --- rank_candidates --------------------------------------------------------
def test_rank_orders_by_score_and_truncates(settings):
    req = make_requested()
    high = make_candidate(id="high", contract_price=8.0, stock_quantity=200)
    low = make_candidate(id="low", category_id="cat_chicken", base_price=12.0, stock_quantity=20)
    scored = [
        score_candidate(
            req, c,
            category_similarity=1.0,
            requested_effective_price=10.0,
            contract_lookup=build_contract_lookup(
                [ContractItem(product_id="high", contract_price=8.0, is_preferred=True)]
            ),
            requested_quantity=20,
            settings=settings,
        )
        for c in (low, high)
    ]
    ranked = rank_candidates(scored, max_results=1)
    assert len(ranked) == 1
    assert ranked[0].candidate.id == "high"
