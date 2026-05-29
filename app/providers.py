"""Ollama integration: thin async wrappers around ``langchain-ollama``.

These adapters implement the ``EmbeddingsProvider`` / ``ChatProvider`` protocols
consumed by the service layer. Construction is lazy (no network call), so a
provider object can be created even when Ollama is down — failures surface at
call time and are handled by the service layer's fallbacks.
"""

from __future__ import annotations

from typing import Optional, Sequence

import httpx

from app.config import Settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class OllamaEmbeddingsProvider:
    """Async embeddings via ``langchain_ollama.OllamaEmbeddings``."""

    def __init__(self, model: str, base_url: str) -> None:
        from langchain_ollama import OllamaEmbeddings

        self.model = model
        self._embeddings = OllamaEmbeddings(model=model, base_url=base_url)

    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embeddings.aembed_documents(list(texts))


class OllamaChatProvider:
    """Async chat completion via ``langchain_ollama.ChatOllama``."""

    def __init__(
        self, model: str, base_url: str, temperature: float, num_predict: int
    ) -> None:
        from langchain_ollama import ChatOllama

        self.model = model
        self._chat = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=temperature,
            num_predict=num_predict,
        )

    async def acomplete(self, system: str, user: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await self._chat.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        content = response.content
        if isinstance(content, list):  # some backends return a list of parts
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content)


def build_providers(
    settings: Settings,
) -> tuple[Optional[OllamaEmbeddingsProvider], Optional[OllamaChatProvider]]:
    """Construct providers honouring the feature toggles. Returns ``None`` for a
    provider that is disabled or whose construction fails."""
    embeddings: Optional[OllamaEmbeddingsProvider] = None
    chat: Optional[OllamaChatProvider] = None

    if settings.enable_embeddings:
        try:
            embeddings = OllamaEmbeddingsProvider(settings.embedding_model, settings.ollama_base_url)
            logger.info("Embeddings enabled (model=%s).", settings.embedding_model)
        except Exception:
            logger.warning("Could not initialise Ollama embeddings; lexical fallback.", exc_info=True)

    if settings.enable_llm_explanations:
        try:
            chat = OllamaChatProvider(
                settings.chat_model,
                settings.ollama_base_url,
                settings.llm_temperature,
                settings.llm_num_predict,
            )
            logger.info("LLM explanations enabled (model=%s).", settings.chat_model)
        except Exception:
            logger.warning("Could not initialise Ollama chat; template fallback.", exc_info=True)

    return embeddings, chat


async def probe_ollama(settings: Settings) -> dict:
    """Best-effort health probe of the Ollama server (lists local models)."""
    url = settings.ollama_base_url.rstrip("/") + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            models = [m.get("name") for m in resp.json().get("models", [])]
        return {
            "reachable": True,
            "base_url": settings.ollama_base_url,
            "models_available": models,
            "chat_model": settings.chat_model,
            "chat_model_present": settings.chat_model in models
            or any((settings.chat_model + ":") in (m or "") for m in models),
            "embedding_model": settings.embedding_model,
            "embedding_model_present": settings.embedding_model in models,
        }
    except Exception as exc:
        return {"reachable": False, "base_url": settings.ollama_base_url, "error": str(exc)}
