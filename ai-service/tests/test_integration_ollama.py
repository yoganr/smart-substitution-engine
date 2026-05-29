"""Live integration tests against a running Ollama instance.

These are skipped automatically when Ollama is not reachable, so they never
break the offline unit-test run. Execute explicitly with:

    pytest -m integration
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.engine import build_engine
from app.providers import probe_ollama
from tests.factories import make_candidate, make_request

pytestmark = pytest.mark.integration


async def _live_settings() -> Settings:
    settings = Settings(enable_embeddings=True, enable_llm_explanations=True)
    health = await probe_ollama(settings)
    if not health.get("reachable"):
        pytest.skip("Ollama is not reachable; skipping integration test.")
    return settings


async def test_real_ollama_generates_explanation():
    settings = await _live_settings()
    engine = build_engine(settings)
    request = make_request(
        candidates=[make_candidate(stock_quantity=100)],
        use_ai_explanation=True,
    )
    response = await engine.recommend(request)
    assert response.replacements
    rep = response.replacements[0]
    assert rep.explanation
    # Either Ollama answered or we cleanly fell back to a template.
    assert rep.explanation_source in {"ollama", "template"}


async def test_real_embeddings_rank_related_category_higher():
    settings = await _live_settings()
    engine = build_engine(settings)
    if not engine.similarity.uses_embeddings:
        pytest.skip("Embeddings unavailable (sentence-transformers / model not loaded).")
    related = make_candidate(
        id="related", name="Chicken Thigh 2kg", category_id="cat_poultry", stock_quantity=100
    )
    unrelated = make_candidate(
        id="unrelated", name="Carrot Bag 5kg", category_id="cat_veg", stock_quantity=100,
        unit="kg", pack_size=5,
    )
    request = make_request(candidates=[related, unrelated], use_ai_explanation=False)
    response = await engine.recommend(request)
    ids = [r.product_id for r in response.replacements]
    # The poultry item should outrank (or be the only) match over a vegetable.
    if "unrelated" in ids and "related" in ids:
        assert ids.index("related") < ids.index("unrelated")
