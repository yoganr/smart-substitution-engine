"""Live integration tests for the Milvus vector store + retrieval service.

Skipped automatically when Milvus or the embedding model is unavailable, so the
offline suite is unaffected. Run explicitly with:

    pytest -m integration tests/test_milvus.py
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.engine import build_engine
from app.schemas import IndexProduct

pytestmark = pytest.mark.integration


def _engine_or_skip():
    settings = Settings(enable_embeddings=True, enable_llm_explanations=False, enable_milvus=True)
    engine = build_engine(settings)
    if not engine.retrieval.available:
        pytest.skip("Milvus or embeddings unavailable.")
    return engine


async def test_index_then_search_ranks_related_higher():
    engine = _engine_or_skip()
    products = [
        IndexProduct(id="t_chicken", name="Chicken Breast 2kg", category_id="cat_chicken", dietary_tags=["halal"]),
        IndexProduct(id="t_thigh", name="Chicken Thigh Fillet 2kg", category_id="cat_poultry", dietary_tags=["halal"]),
        IndexProduct(id="t_carrot", name="Fresh Carrots 5kg", category_id="cat_vegetables", dietary_tags=["vegan"]),
    ]
    assert await engine.retrieval.index_products(products) == 3

    hits = await engine.retrieval.search_similar(
        name="Chicken Breast 2kg", top_k=5, exclude_ids=["t_chicken"]
    )
    ids = [h["product_id"] for h in hits]
    assert ids, "expected at least one hit"
    # Poultry should be more similar to chicken than a vegetable is.
    if "t_thigh" in ids and "t_carrot" in ids:
        assert ids.index("t_thigh") < ids.index("t_carrot")
    # Scores are similarities in [0, 1], descending.
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)


async def test_search_by_indexed_product_id_excludes_itself():
    engine = _engine_or_skip()
    await engine.retrieval.index_products([
        IndexProduct(id="t_ref", name="Chicken Breast 2kg", category_id="cat_chicken"),
        IndexProduct(id="t_other", name="Turkey Breast 2kg", category_id="cat_poultry"),
    ])
    hits = await engine.retrieval.search_similar(product_id="t_ref", top_k=5)
    ids = [h["product_id"] for h in hits]
    assert "t_ref" not in ids  # the query product is excluded from its own results


async def test_active_only_filter_excludes_inactive():
    engine = _engine_or_skip()
    await engine.retrieval.index_products([
        IndexProduct(id="t_active", name="Chicken Breast Fresh", category_id="cat_chicken", is_active=True),
        IndexProduct(id="t_inactive", name="Chicken Breast Old", category_id="cat_chicken", is_active=False),
    ])
    hits = await engine.retrieval.search_similar(
        name="Chicken Breast", top_k=10, active_only=True
    )
    ids = [h["product_id"] for h in hits]
    assert "t_inactive" not in ids
