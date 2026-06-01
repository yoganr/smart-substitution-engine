"""Direct MongoDB Atlas access for catalog data.

In the original MVP the engine was fed ``candidate_products`` by the .NET
backend (which owns Atlas). This module lets the Python service *also* read the
catalog straight from Atlas, powering ``POST /recommendations/auto``: give it a
``company_id`` + an out-of-stock ``product_id`` and it fetches everything itself
(company, product, inventory, contract, candidates) and runs the same engine.

It reads the **PascalCase** field names the .NET MongoDB driver writes
(``ProductId``, ``CategoryId``, ``IsActive`` …), mirroring the queries in the
backend's ``RecommendationController`` + ``CandidateProductService``.

pymongo is synchronous, so every call runs in a worker thread to keep the async
event loop free — the same pattern the Milvus wrapper uses.
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from app.config import Settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# Collection names — must match the .NET backend (RecommendationController.cs).
COMPANIES = "companies"
PRODUCTS = "products"
CONTRACTS = "contracts"
INVENTORY = "inventory"


def _product_to_dict(doc: dict) -> dict:
    """Map a PascalCase Mongo product document to the snake_case API shape."""
    return {
        "id": doc.get("ProductId"),
        "name": doc.get("Name", ""),
        "category_id": doc.get("CategoryId", ""),
        "brand": doc.get("Brand"),
        "unit": doc.get("Unit"),
        "pack_size": doc.get("PackSize"),
        "base_price": float(doc.get("BasePrice", 0) or 0),
        "is_active": bool(doc.get("IsActive", True)),
        "dietary_tags": list(doc.get("DietaryTags", []) or []),
    }


class MongoCatalogRepository:
    """Read-only catalog access over the .NET-owned Atlas database."""

    def __init__(self, uri: str, db_name: str) -> None:
        from pymongo import MongoClient

        # Construction is lazy (no network I/O); the first query connects.
        self._client = MongoClient(uri, serverSelectionTimeoutMS=5000, appname="sse-ai")
        self._db = self._client[db_name]
        self.db_name = db_name

    async def ping(self) -> bool:
        """Best-effort connectivity check (used by /health)."""
        try:
            await asyncio.to_thread(self._client.admin.command, "ping")
            return True
        except Exception as exc:  # pragma: no cover - depends on a live server
            logger.warning("MongoDB ping failed: %s", exc)
            return False

    # -- reads (each mirrors a step in the .NET RecommendationController) --
    async def get_company(self, company_id: str) -> Optional[dict]:
        doc = await asyncio.to_thread(self._db[COMPANIES].find_one, {"CompanyId": company_id})
        return {"id": doc["CompanyId"], "name": doc.get("Name", "")} if doc else None

    async def get_product(self, product_id: str) -> Optional[dict]:
        doc = await asyncio.to_thread(self._db[PRODUCTS].find_one, {"ProductId": product_id})
        return _product_to_dict(doc) if doc else None

    async def get_stock(self, product_id: str) -> Optional[int]:
        doc = await asyncio.to_thread(self._db[INVENTORY].find_one, {"ProductId": product_id})
        return int(doc.get("StockQuantity", 0)) if doc else None

    async def get_contract_items(self, company_id: str) -> list[dict]:
        doc = await asyncio.to_thread(self._db[CONTRACTS].find_one, {"CompanyId": company_id})
        items = (doc or {}).get("Items", []) or []
        return [
            {
                "product_id": it.get("ProductId"),
                "contract_price": it.get("ContractPrice"),
                "is_preferred": bool(it.get("IsPreferred", False)),
            }
            for it in items
        ]

    async def get_candidates(self, category_id: str, exclude_product_id: str) -> list[dict]:
        """Active, same-category, in-stock products (excluding the requested one).

        Mirrors ``CandidateProductService.GetCandidatesAsync``: the
        (CategoryId, IsActive) compound index covers the query; stock is joined
        from the inventory collection and only ``stock > 0`` is kept.
        """
        return await asyncio.to_thread(self._get_candidates_sync, category_id, exclude_product_id)

    def _get_candidates_sync(self, category_id: str, exclude_product_id: str) -> list[dict]:
        products = list(
            self._db[PRODUCTS].find(
                {
                    "CategoryId": category_id,
                    "IsActive": True,
                    "ProductId": {"$ne": exclude_product_id},
                }
            )
        )
        if not products:
            return []
        ids = [p.get("ProductId") for p in products]
        stock_map = {
            i["ProductId"]: i.get("StockQuantity", 0)
            for i in self._db[INVENTORY].find({"ProductId": {"$in": ids}})
        }
        candidates: list[dict] = []
        for p in products:
            stock = stock_map.get(p.get("ProductId"), 0) or 0
            if stock > 0:
                row = _product_to_dict(p)
                row["stock_quantity"] = int(stock)
                candidates.append(row)
        return candidates

    # -- chatbot helpers (free-text catalog lookup) ------------------------
    async def search_products(self, query: str, limit: int = 8) -> list[dict]:
        """Fuzzy product lookup by name (or product id) for the chatbot.

        Case-insensitive substring match on ``Name``/``ProductId`` so a user can
        type "chicken breast" and get concrete catalog products back, each with
        its live stock joined in. Ranking/disambiguation is left to the caller.
        """
        return await asyncio.to_thread(self._search_products_sync, query, limit)

    def _search_products_sync(self, query: str, limit: int) -> list[dict]:
        term = (query or "").strip()
        if not term:
            return []
        pattern = re.escape(term)
        products = list(
            self._db[PRODUCTS]
            .find(
                {
                    "$or": [
                        {"Name": {"$regex": pattern, "$options": "i"}},
                        {"ProductId": {"$regex": pattern, "$options": "i"}},
                    ]
                }
            )
            .limit(max(1, limit) * 3)  # over-fetch; caller re-ranks then trims
        )
        if not products:
            return []
        ids = [p.get("ProductId") for p in products]
        stock_map = {
            i["ProductId"]: i.get("StockQuantity", 0)
            for i in self._db[INVENTORY].find({"ProductId": {"$in": ids}})
        }
        rows: list[dict] = []
        for p in products:
            row = _product_to_dict(p)
            row["stock_quantity"] = int(stock_map.get(p.get("ProductId"), 0) or 0)
            rows.append(row)
        return rows[:limit] if limit else rows

    async def list_companies(self, limit: int = 50) -> list[dict]:
        """All companies as ``[{id, name}]`` (the bot defaults to the first)."""
        return await asyncio.to_thread(self._list_companies_sync, limit)

    def _list_companies_sync(self, limit: int) -> list[dict]:
        docs = self._db[COMPANIES].find().limit(max(1, limit))
        return [{"id": d.get("CompanyId"), "name": d.get("Name", "")} for d in docs if d.get("CompanyId")]

    async def list_categories(self) -> list[str]:
        """Distinct active category ids (for guiding the user)."""
        return await asyncio.to_thread(
            lambda: sorted(c for c in self._db[PRODUCTS].distinct("CategoryId") if c)
        )


def build_mongo_repo(settings: Settings) -> Optional[MongoCatalogRepository]:
    """Construct the repository, or return ``None`` for graceful degradation
    (mongo disabled, no URI configured, or pymongo not installed)."""
    if not settings.enable_mongo or not settings.mongo_uri:
        return None
    try:
        repo = MongoCatalogRepository(settings.mongo_uri, settings.mongo_db)
        logger.info("MongoDB catalog access enabled (db=%s).", settings.mongo_db)
        return repo
    except ImportError:
        logger.warning("pymongo is not installed; direct Atlas access disabled.")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not initialise MongoDB repo: %s", exc)
    return None
