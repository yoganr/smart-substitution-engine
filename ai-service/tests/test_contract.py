"""Contract tests: lock the JSON response shape to the .NET backend DTOs.

These mirror the fields the C# ``PythonReplacementResponseDto`` /
``PythonReplacementDto`` / ``PythonRejectedCandidateDto`` records deserialize
(see backend/SmartSubstitution.Api/Dtos/PythonAiDtos.cs). If any of these break,
the .NET side silently gets nulls/zeros — so we assert them explicitly.
"""

from __future__ import annotations

from app.engine import build_engine
from app.schemas import ContractItem
from tests.factories import make_candidate, make_request, make_requested

# Exact keys the .NET DTOs expect (snake_case via SnakeCaseNamingPolicy).
REPLACEMENT_KEYS = {
    "product_id",
    "name",
    "final_score",
    "confidence_pct",
    "confidence_label",
    "score_breakdown",
    "explanation",
}
BREAKDOWN_KEYS = {
    "category_similarity",
    "contract_match",
    "price_similarity",
    "stock_availability",
    "unit_pack_similarity",
}
REJECTED_KEYS = {"product_id", "name", "rejection_reason"}
LABELS = {"Excellent", "Strong", "Good", "Fair", "Weak"}


async def test_replacement_matches_dotnet_dto(settings):
    engine = build_engine(settings)
    response = await engine.recommend(
        make_request(
            candidates=[make_candidate(id="best", contract_price=8.5, stock_quantity=300)],
            contract_items=[ContractItem(product_id="best", contract_price=8.5, is_preferred=True)],
        )
    )
    body = response.model_dump()

    # Top-level keys the .NET response DTO reads.
    assert {"replacements", "rejected_candidates", "no_candidates_reason"} <= set(body)

    rep = body["replacements"][0]
    assert REPLACEMENT_KEYS <= set(rep)
    assert set(rep["score_breakdown"]) == BREAKDOWN_KEYS

    # Types / value ranges the .NET ints expect.
    assert isinstance(rep["final_score"], int)
    assert isinstance(rep["confidence_pct"], int) and 0 <= rep["confidence_pct"] <= 100
    assert rep["confidence_label"] in LABELS
    assert all(isinstance(v, int) for v in rep["score_breakdown"].values())

    # confidence_pct is consistent with final_score (max 93).
    assert rep["confidence_pct"] == round(rep["final_score"] / 93 * 100)
    # Replacements present -> no_candidates_reason must be null.
    assert body["no_candidates_reason"] is None


async def test_rejected_candidates_match_dotnet_dto(settings):
    engine = build_engine(settings)
    # One good, one inactive (rejected with a reason).
    response = await engine.recommend(
        make_request(
            candidates=[
                make_candidate(id="ok", stock_quantity=100),
                make_candidate(id="dead", is_active=False, stock_quantity=100),
            ]
        )
    )
    body = response.model_dump()
    assert body["rejected_candidates"], "expected the inactive candidate to be reported"
    rc = body["rejected_candidates"][0]
    assert set(rc) >= REJECTED_KEYS
    assert rc["product_id"] == "dead"
    assert isinstance(rc["rejection_reason"], str) and rc["rejection_reason"]


async def test_no_candidates_reason_set_when_all_filtered(settings):
    engine = build_engine(settings)
    response = await engine.recommend(
        make_request(candidates=[make_candidate(id=f"x{i}", is_active=False) for i in range(3)])
    )
    body = response.model_dump()
    assert body["replacements"] == []
    assert isinstance(body["no_candidates_reason"], str) and body["no_candidates_reason"]
    assert len(body["rejected_candidates"]) == 3


async def test_dietary_tags_enforced_end_to_end(settings):
    engine = build_engine(settings)
    requested = make_requested(dietary_tags=["gluten_free"])
    response = await engine.recommend(
        make_request(
            requested_product=requested,
            candidates=[
                make_candidate(id="safe", dietary_tags=["gluten_free"], stock_quantity=100),
                make_candidate(id="unsafe", dietary_tags=[], stock_quantity=100),
            ],
        )
    )
    ids = [r.product_id for r in response.replacements]
    assert "safe" in ids
    assert "unsafe" not in ids
    rejected_ids = [r.product_id for r in response.rejected_candidates]
    assert "unsafe" in rejected_ids
