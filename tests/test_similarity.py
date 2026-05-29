"""Unit tests for the similarity layer (lexical fallback + embedding path)."""

from __future__ import annotations

from app.services.similarity import (
    SimilarityService,
    cosine_similarity,
    lexical_similarity,
)
from tests.factories import make_candidate, make_requested


def test_cosine_basic():
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    assert cosine_similarity([1, 0], [0, 1]) == 0.0
    assert cosine_similarity([0, 0], [1, 1]) == 0.0  # zero vector guard


def test_lexical_identical_and_disjoint():
    assert lexical_similarity("chicken breast", "chicken breast") == 1.0
    assert lexical_similarity("chicken breast 2kg", "chicken thigh 2kg") > 0.3
    assert lexical_similarity("apple", "tractor") < 0.3


async def test_exact_category_is_one_without_embeddings():
    svc = SimilarityService(embeddings=None)
    req = make_requested(category_id="cat_chicken")
    cand = make_candidate(category_id="cat_chicken")
    sims = await svc.category_similarities(req, [cand])
    assert sims[cand.id] == 1.0
    assert svc.uses_embeddings is False


async def test_cross_category_uses_lexical_fallback():
    svc = SimilarityService(embeddings=None)
    req = make_requested(name="Chicken Breast 2kg", category_id="cat_chicken")
    related = make_candidate(id="c1", name="Chicken Breast Premium 2kg", category_id="cat_poultry")
    unrelated = make_candidate(id="c2", name="Carrot Bag 5kg", category_id="cat_veg")
    sims = await svc.category_similarities(req, [related, unrelated])
    assert sims["c1"] > sims["c2"]


class _FakeEmbeddings:
    """Deterministic embeddings: 'chicken' items map to one axis, others to another."""

    async def aembed_documents(self, texts):
        vectors = []
        for t in texts:
            if "chicken" in t.lower():
                vectors.append([1.0, 0.0, 0.0])
            elif "carrot" in t.lower():
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


async def test_embedding_path_computes_cosine():
    svc = SimilarityService(embeddings=_FakeEmbeddings())
    req = make_requested(name="Chicken Breast", category_id="cat_chicken")
    chicken = make_candidate(id="c1", name="Chicken Thigh", category_id="cat_poultry")
    carrot = make_candidate(id="c2", name="Carrot Bag", category_id="cat_veg")
    sims = await svc.category_similarities(req, [chicken, carrot])
    assert sims["c1"] == 1.0   # same axis as the chicken query
    assert sims["c2"] == 0.0   # orthogonal
    assert svc.uses_embeddings is True
