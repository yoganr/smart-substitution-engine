"""Unit tests for the hard-filter layer."""

from __future__ import annotations

from app.services.filters import apply_hard_filters
from tests.factories import make_candidate, make_requested


def _filter(candidates, settings, sims=None, req_price=10.0, qty=20, requested=None):
    req = requested or make_requested()
    return apply_hard_filters(
        req,
        candidates,
        requested_quantity=qty,
        requested_effective_price=req_price,
        category_similarities=sims or {c.id: 1.0 for c in candidates},
        contract_lookup={},
        settings=settings,
    )


def test_inactive_candidate_rejected(settings):
    cand = make_candidate(is_active=False)
    accepted, rejected = _filter([cand], settings)
    assert not accepted
    assert "inactive" in rejected[0].reasons


def test_insufficient_stock_rejected(settings):
    cand = make_candidate(stock_quantity=5)
    accepted, rejected = _filter([cand], settings, qty=20)
    assert not accepted
    assert "insufficient_stock" in rejected[0].reasons


def test_same_product_rejected(settings):
    cand = make_candidate(id="product_001")  # equals requested.id
    accepted, rejected = _filter([cand], settings)
    assert not accepted
    assert "same_product" in rejected[0].reasons


def test_price_too_high_rejected(settings):
    cand = make_candidate(base_price=100.0, contract_price=None)
    accepted, rejected = _filter([cand], settings, req_price=10.0)
    assert not accepted
    assert "price_too_high" in rejected[0].reasons


def test_cross_category_low_similarity_rejected(settings):
    cand = make_candidate(category_id="cat_beef")
    accepted, rejected = _filter([cand], settings, sims={cand.id: 0.2})
    assert not accepted
    assert any("incompatible_category" in r for r in rejected[0].reasons)


def test_cross_category_high_similarity_accepted(settings):
    cand = make_candidate(category_id="cat_poultry")
    accepted, rejected = _filter([cand], settings, sims={cand.id: 0.85})
    assert len(accepted) == 1
    assert not rejected


def test_cross_category_blocked_when_disabled():
    from app.config import Settings

    strict = Settings(
        enable_embeddings=False,
        enable_llm_explanations=False,
        allow_cross_category=False,
    )
    cand = make_candidate(category_id="cat_poultry")
    accepted, rejected = _filter([cand], strict, sims={cand.id: 0.99})
    assert not accepted
    assert "incompatible_category" in rejected[0].reasons


def test_good_candidate_accepted(settings):
    cand = make_candidate()
    accepted, rejected = _filter([cand], settings)
    assert len(accepted) == 1
    assert not rejected


# --- dietary / allergen safety ---------------------------------------------
def test_candidate_missing_required_dietary_tag_rejected(settings):
    req = make_requested(dietary_tags=["gluten_free", "halal"])
    cand = make_candidate(dietary_tags=["halal"])  # missing gluten_free
    accepted, rejected = _filter([cand], settings, requested=req)
    assert not accepted
    assert any("missing_dietary_tags" in r for r in rejected[0].reasons)


def test_candidate_with_superset_of_dietary_tags_accepted(settings):
    req = make_requested(dietary_tags=["halal"])
    cand = make_candidate(dietary_tags=["halal", "gluten_free"])  # superset is fine
    accepted, rejected = _filter([cand], settings, requested=req)
    assert len(accepted) == 1
    assert not rejected


def test_no_required_dietary_tags_means_no_constraint(settings):
    req = make_requested(dietary_tags=[])
    cand = make_candidate(dietary_tags=[])
    accepted, rejected = _filter([cand], settings, requested=req)
    assert len(accepted) == 1


def test_dietary_enforcement_can_be_disabled():
    from app.config import Settings

    lenient = Settings(
        enable_embeddings=False,
        enable_llm_explanations=False,
        enforce_dietary_tags=False,
    )
    req = make_requested(dietary_tags=["gluten_free"])
    cand = make_candidate(dietary_tags=[])
    accepted, _ = _filter([cand], lenient, requested=req)
    assert len(accepted) == 1
