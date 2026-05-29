"""Assembles the recommendation engine: providers -> services -> graph."""

from __future__ import annotations

from typing import Optional

from app.config import Settings
from app.graph.workflow import build_workflow
from app.providers import build_providers
from app.schemas import ReplacementRequest, ReplacementResponse
from app.services.explanation import ExplanationService
from app.services.retrieval import RetrievalService
from app.services.similarity import SimilarityService
from app.vectorstore import build_vectorstore


class RecommendationEngine:
    """Stateless facade over the compiled LangGraph workflow."""

    def __init__(
        self,
        settings: Settings,
        similarity: SimilarityService,
        explainer: ExplanationService,
        retrieval: Optional[RetrievalService] = None,
    ) -> None:
        self.settings = settings
        self.similarity = similarity
        self.explainer = explainer
        self.retrieval = retrieval or RetrievalService()
        self._graph = build_workflow(settings, similarity, explainer)

    async def recommend(self, request: ReplacementRequest) -> ReplacementResponse:
        result = await self._graph.ainvoke({"request": request})
        return result["response"]


def build_engine(settings: Settings) -> RecommendationEngine:
    """Wire providers and services into a ready-to-use engine."""
    embeddings, chat = build_providers(settings)
    # Derive the true embedding dimension from the model when available.
    dim = getattr(getattr(embeddings, "_model", None), "get_sentence_embedding_dimension", None)
    embedding_dim = dim() if callable(dim) else settings.embedding_dim
    store = build_vectorstore(settings, dim=embedding_dim)

    similarity = SimilarityService(embeddings, store=store)
    explainer = ExplanationService(chat, per_call_timeout=settings.ollama_timeout)
    retrieval = RetrievalService(embeddings, store=store)
    return RecommendationEngine(settings, similarity, explainer, retrieval)
