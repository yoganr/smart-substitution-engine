"""Catalog indexing + similarity search backed by Milvus.

Powers the optional ``POST /index/products`` and ``POST /search/similar``
endpoints. Requires both an embedder (sentence-transformers) and a Milvus store;
if either is missing the endpoints report 503.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Sequence

from app.logging_config import get_logger

logger = get_logger(__name__)


def _text(name: str, category_id: Optional[str]) -> str:
    return " ".join(p for p in (name or "", category_id or "") if p).strip()


class RetrievalService:
    def __init__(self, embeddings=None, store=None) -> None:
        self._embeddings = embeddings
        self._store = store

    @property
    def available(self) -> bool:
        return self._store is not None and self._embeddings is not None

    def _require(self) -> None:
        if self._store is None:
            raise RuntimeError("Milvus vector store is not available.")
        if self._embeddings is None:
            raise RuntimeError("Embedding model is not available.")

    async def index_products(self, products: Sequence) -> int:
        """Embed and upsert a batch of products into Milvus."""
        self._require()
        products = list(products)
        if not products:
            return 0
        vectors = await self._embeddings.aembed_documents(
            [_text(p.name, p.category_id) for p in products]
        )
        rows = [
            {
                "id": p.id,
                "vector": vec,
                "name": p.name,
                "category_id": p.category_id,
                "is_active": getattr(p, "is_active", True),
                "dietary_tags": getattr(p, "dietary_tags", []),
            }
            for p, vec in zip(products, vectors)
        ]
        count = await asyncio.to_thread(self._store.upsert, rows)
        # Make the new rows immediately searchable (read-after-write).
        await asyncio.to_thread(self._store.flush)
        logger.info("Indexed %d products into Milvus.", count)
        return count

    async def search_similar(
        self,
        *,
        name: Optional[str] = None,
        category_id: Optional[str] = None,
        product_id: Optional[str] = None,
        top_k: int = 5,
        exclude_ids: Optional[Sequence[str]] = None,
        active_only: bool = True,
    ) -> list[dict]:
        """Find the most similar products in the catalog by vector search."""
        self._require()
        exclude = list(exclude_ids or [])

        query_vec: Optional[list[float]] = None
        # Prefer the product's own stored vector when an id is given.
        if product_id:
            cached = await asyncio.to_thread(self._store.fetch_vectors, [product_id])
            query_vec = cached.get(product_id)
            exclude.append(product_id)
        if query_vec is None:
            if not name:
                raise ValueError("Provide 'name' (and optionally 'category_id') or an indexed 'product_id'.")
            query_vec = (await self._embeddings.aembed_documents([_text(name, category_id)]))[0]

        return await asyncio.to_thread(
            self._store.search,
            query_vec,
            top_k,
            exclude_ids=exclude,
            active_only=active_only,
            category_id=category_id,
        )

    def count(self) -> int:
        return self._store.count() if self._store is not None else 0
