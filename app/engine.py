"""Assembles the recommendation engine: providers -> services -> graph."""

from __future__ import annotations

from app.config import Settings
from app.graph.workflow import build_workflow
from app.providers import build_providers
from app.schemas import ReplacementRequest, ReplacementResponse
from app.services.explanation import ExplanationService
from app.services.similarity import SimilarityService


class RecommendationEngine:
    """Stateless facade over the compiled LangGraph workflow."""

    def __init__(
        self,
        settings: Settings,
        similarity: SimilarityService,
        explainer: ExplanationService,
    ) -> None:
        self.settings = settings
        self.similarity = similarity
        self.explainer = explainer
        self._graph = build_workflow(settings, similarity, explainer)

    async def recommend(self, request: ReplacementRequest) -> ReplacementResponse:
        result = await self._graph.ainvoke({"request": request})
        return result["response"]


def build_engine(settings: Settings) -> RecommendationEngine:
    """Wire providers and services into a ready-to-use engine."""
    embeddings, chat = build_providers(settings)
    similarity = SimilarityService(embeddings)
    explainer = ExplanationService(chat, per_call_timeout=settings.ollama_timeout)
    return RecommendationEngine(settings, similarity, explainer)
