"""HTTP-level tests via FastAPI's TestClient (Ollama disabled for determinism)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SSE_ENABLE_EMBEDDINGS", "false")
    monkeypatch.setenv("SSE_ENABLE_LLM_EXPLANATIONS", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


SAMPLE_PAYLOAD = {
    "company": {"id": "company_001", "name": "ABC Restaurant"},
    "requested_product": {
        "id": "product_001",
        "name": "Chicken Breast 2kg",
        "category_id": "cat_chicken",
        "brand": "Brand A",
        "unit": "kg",
        "pack_size": 2,
        "base_price": 10.0,
    },
    "requested_quantity": 20,
    "contract_items": [
        {"product_id": "product_2033", "contract_price": 9.5, "is_preferred": True}
    ],
    "candidate_products": [
        {
            "id": "product_2033",
            "name": "Chicken Breast Premium 2kg",
            "category_id": "cat_chicken",
            "brand": "Brand B",
            "unit": "kg",
            "pack_size": 2,
            "base_price": 10.5,
            "stock_quantity": 150,
            "contract_price": 9.5,
        },
        {
            "id": "product_2099",
            "name": "Organic Chicken Breast 2kg",
            "category_id": "cat_chicken",
            "brand": "Brand C",
            "unit": "kg",
            "pack_size": 2,
            "base_price": 11.0,
            "stock_quantity": 40,
        },
    ],
    "max_results": 3,
    "use_ai_explanation": False,
}


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert "reachable" in body["ollama"]


def test_recommend_returns_ranked_replacements(client):
    resp = client.post("/recommendations/replacements", json=SAMPLE_PAYLOAD)
    assert resp.status_code == 200
    body = resp.json()

    assert body["candidates_evaluated"] == 2
    assert len(body["replacements"]) >= 1

    top = body["replacements"][0]
    assert top["product_id"] == "product_2033"  # preferred + cheaper
    assert top["is_preferred"] is True

    for rep in body["replacements"]:
        b = rep["score_breakdown"]
        total = (
            b["category_similarity"] + b["contract_match"] + b["price_similarity"]
            + b["stock_availability"] + b["unit_pack_similarity"]
        )
        assert rep["final_score"] == total
        assert 0 <= rep["final_score"] <= 93
        assert rep["explanation"]


def test_recommend_validation_error(client):
    bad = dict(SAMPLE_PAYLOAD, requested_quantity=0)  # gt=0 -> 422
    resp = client.post("/recommendations/replacements", json=bad)
    assert resp.status_code == 422


def test_openapi_schema_exposes_endpoints(client):
    spec = client.get("/openapi.json").json()
    assert "/recommendations/replacements" in spec["paths"]
    assert "/health" in spec["paths"]
