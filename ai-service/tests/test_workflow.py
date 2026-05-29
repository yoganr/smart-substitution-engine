"""End-to-end tests for the compiled LangGraph workflow (offline engine)."""

from __future__ import annotations

from app.engine import build_engine
from app.schemas import ContractItem
from tests.factories import make_candidate, make_request


async def test_end_to_end_ranks_best_candidate_first(settings):
    engine = build_engine(settings)

    preferred = make_candidate(
        id="best", name="Chicken Breast Premium 2kg",
        contract_price=8.5, stock_quantity=300,
    )
    pricey = make_candidate(
        id="pricey", name="Chicken Breast Deluxe 2kg",
        base_price=12.0, stock_quantity=25,
    )
    request = make_request(
        candidates=[pricey, preferred],
        contract_items=[ContractItem(product_id="best", contract_price=8.5, is_preferred=True)],
    )

    response = await engine.recommend(request)

    assert response.replacement_needed is True
    assert response.candidates_evaluated == 2
    assert len(response.replacements) >= 1
    # The preferred, cheaper, well-stocked product must win.
    assert response.replacements[0].product_id == "best"
    assert response.replacements[0].is_preferred is True

    # Each breakdown must sum to its final score, and an explanation must exist.
    for rep in response.replacements:
        b = rep.score_breakdown
        assert rep.final_score == (
            b.category_similarity + b.contract_match + b.price_similarity
            + b.stock_availability + b.unit_pack_similarity
        )
        assert 0 <= rep.final_score <= 93
        assert rep.explanation
        assert rep.explanation_source == "template"  # offline engine


async def test_results_sorted_descending(settings):
    engine = build_engine(settings)
    candidates = [
        make_candidate(id="a", contract_price=8.0, stock_quantity=300),
        make_candidate(id="b", base_price=10.5, stock_quantity=100),
        make_candidate(id="c", base_price=11.0, stock_quantity=25),
    ]
    request = make_request(
        candidates=candidates,
        contract_items=[ContractItem(product_id="a", contract_price=8.0, is_preferred=True)],
        max_results=3,
    )
    response = await engine.recommend(request)
    scores = [r.final_score for r in response.replacements]
    assert scores == sorted(scores, reverse=True)


async def test_max_results_is_respected(settings):
    engine = build_engine(settings)
    candidates = [make_candidate(id=f"p{i}", stock_quantity=100) for i in range(6)]
    request = make_request(candidates=candidates, max_results=2)
    response = await engine.recommend(request)
    assert len(response.replacements) == 2


async def test_empty_candidates_returns_warning(settings):
    engine = build_engine(settings)
    request = make_request(candidates=[])
    response = await engine.recommend(request)
    assert response.replacements == []
    assert response.warnings
    assert response.candidates_evaluated == 0


async def test_all_filtered_out_returns_empty(settings):
    engine = build_engine(settings)
    # Every candidate is inactive -> all rejected -> no scoring path.
    candidates = [make_candidate(id=f"x{i}", is_active=False) for i in range(3)]
    request = make_request(candidates=candidates)
    response = await engine.recommend(request)
    assert response.replacements == []
    assert response.candidates_rejected == 3
