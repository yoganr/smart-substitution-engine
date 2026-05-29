import pytest
from app.nodes import apply_hard_filters
from app.schemas import CandidateProduct


def _run_filters(sample_request, extra_candidates=None):
    candidates = list(sample_request.candidate_products)
    if extra_candidates:
        candidates.extend(extra_candidates)
    state = {
        "request": sample_request,
        "candidates": candidates,
        "rejected": [],
        "scored": [],
        "replacements": [],
        "no_candidates_reason": None,
    }
    return apply_hard_filters(state)


def test_inactive_product_rejected(sample_request, base_candidate):
    inactive = base_candidate.model_copy(update={"id": "p_inactive", "is_active": False})
    result = _run_filters(sample_request, [inactive])
    rejected_ids = {r.product_id for r in result["rejected"]}
    assert "p_inactive" in rejected_ids
    reason = next(r.rejection_reason for r in result["rejected"] if r.product_id == "p_inactive")
    assert "inactive" in reason


def test_insufficient_stock_rejected(sample_request, base_candidate):
    low_stock = base_candidate.model_copy(update={"id": "p_lowstock", "stock_quantity": 5})
    result = _run_filters(sample_request, [low_stock])
    rejected_ids = {r.product_id for r in result["rejected"]}
    assert "p_lowstock" in rejected_ids
    reason = next(r.rejection_reason for r in result["rejected"] if r.product_id == "p_lowstock")
    assert "stock" in reason


def test_wrong_category_rejected(sample_request, base_candidate):
    wrong_cat = base_candidate.model_copy(update={"id": "p_wrongcat", "category_id": "cat_beef"})
    result = _run_filters(sample_request, [wrong_cat])
    rejected_ids = {r.product_id for r in result["rejected"]}
    assert "p_wrongcat" in rejected_ids


def test_same_product_rejected(sample_request, base_candidate):
    same = base_candidate.model_copy(update={"id": "product_001"})
    result = _run_filters(sample_request, [same])
    rejected_ids = {r.product_id for r in result["rejected"]}
    assert "product_001" in rejected_ids


def test_price_over_threshold_rejected(sample_request, base_candidate):
    # 10.0 * 1.20 = 12.0; base_price 13.0 should be rejected
    expensive = base_candidate.model_copy(update={"id": "p_expensive", "base_price": 13.0})
    result = _run_filters(sample_request, [expensive])
    rejected_ids = {r.product_id for r in result["rejected"]}
    assert "p_expensive" in rejected_ids
    reason = next(r.rejection_reason for r in result["rejected"] if r.product_id == "p_expensive")
    assert "threshold" in reason


def test_allergen_mismatch_rejected(sample_request, base_candidate):
    # requested has dietary_tags=["halal"], candidate has no halal tag
    no_halal = base_candidate.model_copy(update={"id": "p_nohalal", "dietary_tags": ["gluten-free"]})
    result = _run_filters(sample_request, [no_halal])
    rejected_ids = {r.product_id for r in result["rejected"]}
    assert "p_nohalal" in rejected_ids
    reason = next(r.rejection_reason for r in result["rejected"] if r.product_id == "p_nohalal")
    assert "halal" in reason


def test_allergen_superset_passes(sample_request, base_candidate):
    # candidate has halal + extra tags — should pass
    superset = base_candidate.model_copy(
        update={"id": "p_superset", "dietary_tags": ["halal", "gluten-free", "kosher"]}
    )
    result = _run_filters(sample_request, [superset])
    passing_ids = {c.id for c in result["candidates"]}
    assert "p_superset" in passing_ids


def test_allergen_case_insensitive(sample_request, base_candidate):
    # "Halal" (uppercase) should match "halal" requirement
    upper_tag = base_candidate.model_copy(
        update={"id": "p_upper", "dietary_tags": ["Halal"]}
    )
    result = _run_filters(sample_request, [upper_tag])
    passing_ids = {c.id for c in result["candidates"]}
    assert "p_upper" in passing_ids


def test_good_candidate_passes(sample_request, base_candidate):
    result = _run_filters(sample_request)
    passing_ids = {c.id for c in result["candidates"]}
    assert base_candidate.id in passing_ids
