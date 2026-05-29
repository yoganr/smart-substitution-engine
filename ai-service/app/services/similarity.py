"""Semantic + lexical similarity for category/product compatibility.

The engine prefers true semantic similarity using a BAAI BGE embedding model
(``BAAI/bge-m3`` via ``sentence-transformers``, GPU when available) and
gracefully falls back to a deterministic lexical measure when embeddings are
disabled or the model fails to load. This keeps unit tests fast and offline
while letting the live service be genuinely "smart".
"""

from __future__ import annotations

import asyncio
import math
from difflib import SequenceMatcher
from typing import Optional, Protocol, Sequence

from app.logging_config import get_logger
from app.schemas import CandidateProduct, RequestedProduct

logger = get_logger(__name__)


class EmbeddingsProvider(Protocol):
    """Minimal async embeddings interface (implemented by the Ollama wrapper)."""

    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


def cosine_similarity(u: Sequence[float], v: Sequence[float]) -> float:
    """Cosine similarity, clamped to [0, 1]."""
    dot = sum(a * b for a, b in zip(u, v))
    nu = math.sqrt(sum(a * a for a in u))
    nv = math.sqrt(sum(b * b for b in v))
    if nu == 0.0 or nv == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (nu * nv)))


def lexical_similarity(a: str, b: str) -> float:
    """Deterministic offline similarity: max of token-Jaccard and char-ratio."""
    a = (a or "").lower().strip()
    b = (b or "").lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    tokens_a, tokens_b = set(a.split()), set(b.split())
    union = tokens_a | tokens_b
    jaccard = len(tokens_a & tokens_b) / len(union) if union else 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    return max(jaccard, ratio)


def _describe(product) -> str:
    parts = [getattr(product, "name", "") or "", getattr(product, "category_id", "") or ""]
    return " ".join(p for p in parts if p).strip()


class SimilarityService:
    """Computes a category-similarity score in [0, 1] for each candidate.

    Exact ``category_id`` matches always score 1.0. For differing categories the
    service uses embeddings (if available) or lexical similarity as a proxy for
    "compatible category".
    """

    def __init__(self, embeddings: Optional[EmbeddingsProvider] = None, store=None) -> None:
        self._embeddings = embeddings
        self._store = store  # Optional MilvusVectorStore (embedding cache)

    @property
    def uses_embeddings(self) -> bool:
        return self._embeddings is not None

    @property
    def uses_milvus(self) -> bool:
        return self._store is not None

    @property
    def embedding_device(self) -> Optional[str]:
        """Device the embedding model runs on (e.g. 'cuda:0'), if available."""
        return getattr(self._embeddings, "device", None)

    async def _vectors_for(self, products: Sequence) -> dict[str, list[float]]:
        """Resolve embeddings for products, using Milvus as a cache: fetch cached
        vectors, embed only the misses, and write them back. Falls back to plain
        embedding when there is no store."""
        by_id = {p.id: p for p in products}
        ids = list(by_id)
        vectors: dict[str, list[float]] = {}

        if self._store is not None:
            try:
                vectors.update(await asyncio.to_thread(self._store.fetch_vectors, ids))
            except Exception:  # pragma: no cover - live-server failure path
                logger.warning("Milvus fetch failed; embedding fresh.", exc_info=True)

        missing = [pid for pid in ids if pid not in vectors]
        if missing and self._embeddings is not None:
            try:
                new = await self._embeddings.aembed_documents(
                    [_describe(by_id[pid]) for pid in missing]
                )
                new_map = dict(zip(missing, new))
                vectors.update(new_map)
                if self._store is not None:
                    rows = [
                        {
                            "id": pid,
                            "vector": new_map[pid],
                            "name": by_id[pid].name,
                            "category_id": by_id[pid].category_id,
                            "is_active": getattr(by_id[pid], "is_active", True),
                            "dietary_tags": getattr(by_id[pid], "dietary_tags", []),
                        }
                        for pid in missing
                    ]
                    try:
                        await asyncio.to_thread(self._store.upsert, rows)
                    except Exception:  # pragma: no cover
                        logger.warning("Milvus upsert failed.", exc_info=True)
            except Exception:  # pragma: no cover - network/runtime failure path
                logger.warning("Embedding failed; will use lexical similarity.", exc_info=True)
        return vectors

    async def category_similarities(
        self, requested: RequestedProduct, candidates: Sequence[CandidateProduct]
    ) -> dict[str, float]:
        """Return ``{candidate_id: similarity}`` for every candidate."""
        sims: dict[str, float] = {}
        non_exact: list[CandidateProduct] = []

        for cand in candidates:
            if cand.category_id == requested.category_id:
                sims[cand.id] = 1.0
            else:
                non_exact.append(cand)

        if not non_exact:
            return sims

        vectors = await self._vectors_for([requested, *non_exact])
        req_vec = vectors.get(requested.id)
        for cand in non_exact:
            cand_vec = vectors.get(cand.id)
            if req_vec is not None and cand_vec is not None:
                sims[cand.id] = cosine_similarity(req_vec, cand_vec)
            else:
                sims[cand.id] = lexical_similarity(requested.name, cand.name)
        return sims
