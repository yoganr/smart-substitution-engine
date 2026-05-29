"""Semantic + lexical similarity for category/product compatibility.

The engine prefers true semantic similarity using a BAAI BGE embedding model
(``BAAI/bge-m3`` via ``sentence-transformers``, GPU when available) and
gracefully falls back to a deterministic lexical measure when embeddings are
disabled or the model fails to load. This keeps unit tests fast and offline
while letting the live service be genuinely "smart".
"""

from __future__ import annotations

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

    def __init__(self, embeddings: Optional[EmbeddingsProvider] = None) -> None:
        self._embeddings = embeddings

    @property
    def uses_embeddings(self) -> bool:
        return self._embeddings is not None

    @property
    def embedding_device(self) -> Optional[str]:
        """Device the embedding model runs on (e.g. 'cuda:0'), if available."""
        return getattr(self._embeddings, "device", None)

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

        if self._embeddings is not None:
            try:
                query = _describe(requested)
                docs = [_describe(c) for c in non_exact]
                vectors = await self._embeddings.aembed_documents([query, *docs])
                query_vec, cand_vecs = vectors[0], vectors[1:]
                for cand, vec in zip(non_exact, cand_vecs):
                    sims[cand.id] = cosine_similarity(query_vec, vec)
                return sims
            except Exception:  # pragma: no cover - network/runtime failure path
                logger.warning(
                    "Embedding similarity failed; falling back to lexical similarity.",
                    exc_info=True,
                )

        # Lexical fallback for the non-exact candidates.
        for cand in non_exact:
            sims[cand.id] = lexical_similarity(requested.name, cand.name)
        return sims
