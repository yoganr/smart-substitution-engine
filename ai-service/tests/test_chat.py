"""Offline tests for the chatbot layer.

No live Ollama / Atlas: the orchestrator runs on its deterministic heuristics
(chat provider = None) and the agents talk to a small in-memory ``FakeRepo`` +
the real offline ``RecommendationEngine`` (lexical similarity, template
explanations). This exercises the whole graph: routing → agents → cards.
"""

from __future__ import annotations

import pytest

from app.chat.router import Orchestrator
from app.chat.service import build_chat_service
from app.chat.state import (
    INTENT_FIND_REPLACEMENT,
    INTENT_GUIDE,
    INTENT_OFF_TOPIC,
    INTENT_PRODUCT_INFO,
    INTENT_SIMILAR,
    INTENT_STOCK_OVERVIEW,
)
from app.engine import build_engine


class FakeRepo:
    """Tiny in-memory stand-in for MongoCatalogRepository."""

    def __init__(self) -> None:
        self.products = {
            "product_001": _p("product_001", "Chicken Breast 2kg", "cat_chicken", 10.0, 0),
            "product_002": _p("product_002", "Chicken Breast Premium 2kg", "cat_chicken", 10.5, 150),
            "product_003": _p("product_003", "Chicken Thigh Boneless 2kg", "cat_chicken", 8.5, 80),
            "product_010": _p("product_010", "Beef Mince 5% Fat 1kg", "cat_beef", 8.0, 40),
            "product_050": _p("product_050", "Beef Tomatoes 5kg", "cat_vegetables", 6.0, 100),
        }

    async def search_products(self, query, limit=8):
        q = (query or "").lower()
        hits = [dict(p) for p in self.products.values() if q and (q in p["name"].lower() or q in p["id"])]
        return hits[:limit]

    async def get_stock(self, product_id):
        p = self.products.get(product_id)
        return None if p is None else p["stock_quantity"]

    async def get_company(self, company_id):
        return {"id": company_id, "name": "ABC Restaurant"}

    async def get_product(self, product_id):
        p = self.products.get(product_id)
        return dict(p) if p else None

    async def get_contract_items(self, company_id):
        return []

    async def get_candidates(self, category_id, exclude_product_id):
        return [
            dict(p)
            for p in self.products.values()
            if p["category_id"] == category_id and p["id"] != exclude_product_id and p["stock_quantity"] > 0
        ]

    async def list_companies(self, limit=50):
        return [{"id": "company_001", "name": "ABC Restaurant"}]

    async def list_categories(self):
        return ["cat_beef", "cat_chicken"]

    async def list_out_of_stock_products(self, limit=6):
        oos = [dict(p) for p in self.products.values() if p["stock_quantity"] <= 0]
        rows = oos[:limit]
        for r in rows:
            r["stock_quantity"] = 0
        return rows, len(oos)


def _p(pid, name, category, price, stock):
    return {
        "id": pid, "name": name, "category_id": category, "brand": "Brand A",
        "unit": "kg", "pack_size": 2.0, "base_price": price, "is_active": True,
        "dietary_tags": [], "stock_quantity": stock,
    }


@pytest.fixture
def repo():
    return FakeRepo()


@pytest.fixture
def service(settings, repo):
    return build_chat_service(settings, build_engine(settings), repo)


# --- Orchestrator routing (deterministic, no LLM) ---------------------------
@pytest.mark.parametrize(
    "message, intent",
    [
        ("hi", INTENT_GUIDE),
        ("what can you do?", INTENT_GUIDE),
        ("find a replacement for chicken breast", INTENT_FIND_REPLACEMENT),
        ("chicken breast is out of stock", INTENT_FIND_REPLACEMENT),
        ("show me similar products to beef mince", INTENT_SIMILAR),
        ("what's the price of chicken breast", INTENT_PRODUCT_INFO),
        ("is chicken breast in stock?", INTENT_PRODUCT_INFO),
        ("what's the weather today?", INTENT_OFF_TOPIC),
        ("tell me a joke", INTENT_OFF_TOPIC),
        ("write me some python code", INTENT_OFF_TOPIC),
        ("which is out of stock right now?", INTENT_STOCK_OVERVIEW),
        ("what's out of stock?", INTENT_STOCK_OVERVIEW),
        ("show me out of stock products", INTENT_STOCK_OVERVIEW),
        ("chicken breast is out of stock", INTENT_FIND_REPLACEMENT),  # specific product → replacement
    ],
)
async def test_orchestrator_routing(settings, repo, message, intent):
    orch = Orchestrator(chat_provider=None, repo=repo, settings=settings)
    out = await orch({"message": message, "context": {}})
    assert out["intent"] == intent


@pytest.mark.parametrize(
    "message, product",
    [
        ("is Beef Mince 5% Fat 1kg in stock?", "Beef Mince 5% Fat 1kg"),
        ("find a replacement for Chicken Breast 2kg, I need 20", "Chicken Breast 2kg"),
        ("what's the price of Chicken Breast Premium", "Chicken Breast Premium"),
        ("do you have Beef Ribeye Steak 1kg", "Beef Ribeye Steak 1kg"),
        ("I want to find a replacement", ""),            # no product named → empty
        ("No, I want boiled chicken", "boiled chicken"),  # strip "No," + "I want"
    ],
)
def test_product_phrase_extraction(settings, message, product):
    orch = Orchestrator(chat_provider=None, repo=None, settings=settings)
    assert orch._extract_product(message) == product


# --- End-to-end via ChatService --------------------------------------------
async def test_greeting_guides_with_suggestions(service):
    resp = await service.handle(None, "hello")
    assert resp.intent == INTENT_GUIDE
    assert resp.suggestions
    assert resp.cards == []
    assert resp.session_id  # a session id is minted


async def test_off_topic_is_politely_refused(service):
    resp = await service.handle(None, "what's the weather in Paris?")
    assert resp.intent == INTENT_OFF_TOPIC
    assert resp.cards == []
    assert resp.suggestions
    assert "only help" in resp.reply.lower() or "substitution" in resp.reply.lower()


async def test_substitution_returns_ranked_replacement_cards(service):
    resp = await service.handle(None, "find a replacement for Chicken Breast 2kg, I need 20")
    assert resp.intent == INTENT_FIND_REPLACEMENT
    assert resp.cards, "expected replacement cards"
    assert all(c.type == "replacement" for c in resp.cards)
    assert all(c.rank and c.confidence_pct is not None for c in resp.cards)


async def test_in_stock_product_needs_no_replacement(service):
    # product_002 has 150 in stock; asking for 20 should short-circuit.
    resp = await service.handle(None, "replacement for Chicken Breast Premium, need 20")
    assert resp.intent == INTENT_FIND_REPLACEMENT
    assert resp.cards == []
    assert "in stock" in resp.reply.lower()


async def test_multiturn_asks_for_product_then_resolves(service):
    first = await service.handle(None, "I need a replacement")
    assert first.intent == INTENT_FIND_REPLACEMENT
    assert first.cards == []
    assert "which product" in first.reply.lower()

    second = await service.handle(first.session_id, "Chicken Breast 2kg")
    assert second.cards, "expected replacement cards after naming the product"
    assert all(c.type == "replacement" for c in second.cards)


async def test_product_info_returns_a_product_card(service):
    resp = await service.handle(None, "what's the price of Chicken Breast Premium")
    assert resp.intent == INTENT_PRODUCT_INFO
    assert len(resp.cards) == 1
    assert resp.cards[0].type == "product"


async def test_broad_stock_query_summarises_all_matches(service):
    # "chicken" matches several products → summarise stock for all, not disambiguate.
    resp = await service.handle(None, "how many chicken in stock?")
    assert resp.intent == INTENT_PRODUCT_INFO
    assert len(resp.cards) >= 2
    assert all(c.type == "product" for c in resp.cards)
    assert "which one" not in resp.reply.lower()


async def test_cancel_exits_a_pending_flow(service):
    first = await service.handle(None, "I need a replacement")
    assert "which product" in first.reply.lower()
    resp = await service.handle(first.session_id, "cancel")
    assert resp.intent == INTENT_GUIDE
    assert resp.cards == []


async def test_vague_replacement_asks_and_does_not_match_garbage(service):
    # "to find a replacement" must NOT substring-match unrelated products
    # (the 2-char prefix "to" used to match "Tomatoes").
    resp = await service.handle(None, "I want to find a replacement")
    assert resp.intent == INTENT_FIND_REPLACEMENT
    assert resp.cards == []
    assert "which product" in resp.reply.lower()
    assert "tomato" not in resp.reply.lower()


async def test_disambiguation_acknowledges_unstocked_attribute(service):
    asked = await service.handle(None, "find a replacement")
    assert "which product" in asked.reply.lower()
    disamb = await service.handle(asked.session_id, "chicken")  # several chicken variants
    refined = await service.handle(disamb.session_id, "No, I want boiled chicken")
    # Honest about the missing attribute instead of silently repeating the list.
    assert "boiled" in refined.reply.lower()


async def test_stock_overview_lists_out_of_stock(service):
    resp = await service.handle(None, "which is out of stock right now?")
    assert resp.intent == INTENT_STOCK_OVERVIEW
    assert resp.cards and all(c.type == "product" for c in resp.cards)
    assert "out of stock" in resp.reply.lower()
    assert any(c.name == "Chicken Breast 2kg" for c in resp.cards)  # the OOS item


async def test_stock_query_does_not_flag_command_words(service):
    # "check"/"how"/"many"/"still" must not be treated as missing product attributes.
    resp = await service.handle(None, "I want check how many still in stock for chicken")
    assert resp.intent == INTENT_PRODUCT_INFO
    assert "check option" not in resp.reply.lower()
    assert "don't stock a check" not in resp.reply.lower()
