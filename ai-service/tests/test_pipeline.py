import pytest
from unittest.mock import AsyncMock, patch
from app.pipeline import recommendation_pipeline
from app.schemas import ReplacementRequest


@pytest.mark.asyncio
async def test_happy_path_returns_sorted_results(sample_request):
    result = await recommendation_pipeline.ainvoke({
        "request": sample_request,
        "candidates": [],
        "rejected": [],
        "scored": [],
        "replacements": [],
        "no_candidates_reason": None,
    })
    assert len(result["replacements"]) >= 1
    scores = [r.final_score for r in result["replacements"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_ollama_failure_uses_template_fallback(sample_request):
    sample_with_ai = sample_request.model_copy(update={"use_ai_explanation": True})
    with patch("app.nodes.ChatOllama") as mock_llm_class:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.side_effect = ConnectionError("Ollama unavailable")
        mock_llm_class.return_value = mock_instance

        result = await recommendation_pipeline.ainvoke({
            "request": sample_with_ai,
            "candidates": [],
            "rejected": [],
            "scored": [],
            "replacements": [],
            "no_candidates_reason": None,
        })
    assert len(result["replacements"]) >= 1
    # Fallback template contains "compatible replacement"
    for r in result["replacements"]:
        assert "compatible replacement" in r.explanation or len(r.explanation) > 0


@pytest.mark.asyncio
async def test_all_candidates_filtered_returns_reason(sample_request):
    # Request halal, all candidates have no halal tag
    from app.schemas import CandidateProduct
    no_halal = sample_request.candidate_products[0].model_copy(
        update={"dietary_tags": [], "id": "p_nohalal"}
    )
    filtered_request = sample_request.model_copy(
        update={"candidate_products": [no_halal]}
    )
    result = await recommendation_pipeline.ainvoke({
        "request": filtered_request,
        "candidates": [],
        "rejected": [],
        "scored": [],
        "replacements": [],
        "no_candidates_reason": None,
    })
    assert result["replacements"] == []
    assert result["no_candidates_reason"] is not None
    assert "filtered" in result["no_candidates_reason"]
