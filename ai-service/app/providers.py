"""Ollama integration: thin async wrappers around ``langchain-ollama``.

These adapters implement the ``EmbeddingsProvider`` / ``ChatProvider`` protocols
consumed by the service layer. Construction is lazy (no network call), so a
provider object can be created even when Ollama is down - failures surface at
call time and are handled by the service layer's fallbacks.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Sequence

import httpx

from app.config import Settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class SentenceTransformerEmbeddingsProvider:
    """Local embeddings via ``sentence-transformers`` (no Ollama round-trip).

    Loads the model once (downloading from HuggingFace on first use) and runs
    inference in a worker thread so the async event loop is never blocked. Uses
    GPU automatically when available. Vectors are L2-normalised.
    """

    def __init__(self, model_name: str, device: Optional[str] = None) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device=device)
        self.device = str(self._model.device)
        logger.info("Loaded embedding model '%s' on %s.", model_name, self.device)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return vectors.tolist()

    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, list(texts))


class OllamaEmbeddingsProvider:
    """Async embeddings via ``langchain_ollama.OllamaEmbeddings`` (optional backend)."""

    def __init__(self, model: str, base_url: str) -> None:
        from langchain_ollama import OllamaEmbeddings

        self.model = model
        self._embeddings = OllamaEmbeddings(model=model, base_url=base_url)

    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embeddings.aembed_documents(list(texts))


class OllamaChatProvider:
    """Async chat completion via ``langchain_ollama.ChatOllama``."""

    def __init__(
        self,
        model: str,
        base_url: str,
        temperature: float,
        num_predict: int,
        disable_reasoning: bool = True,
    ) -> None:
        from langchain_ollama import ChatOllama

        self.model = model
        kwargs = dict(
            model=model,
            base_url=base_url,
            temperature=temperature,
            num_predict=num_predict,
        )
        # Turn off chain-of-thought for thinking models so a small model returns
        # the answer directly. Retry without the flag if the installed
        # langchain-ollama version doesn't support it.
        if disable_reasoning:
            try:
                self._chat = ChatOllama(reasoning=False, **kwargs)
                return
            except Exception:
                logger.warning(
                    "ChatOllama does not accept reasoning=False; continuing without it.",
                )
        self._chat = ChatOllama(**kwargs)

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
) -> tuple[Optional[object], Optional[OllamaChatProvider]]:
    """Construct providers honouring the feature toggles. Returns ``None`` for a
    provider that is disabled or whose construction fails (→ graceful fallback)."""
    embeddings: Optional[object] = None
    chat: Optional[OllamaChatProvider] = None

    if settings.enable_embeddings:
        try:
            if settings.embedding_backend == "ollama":
                embeddings = OllamaEmbeddingsProvider(
                    settings.embedding_model, settings.ollama_base_url
                )
            else:
                embeddings = SentenceTransformerEmbeddingsProvider(
                    settings.embedding_model, settings.embedding_device
                )
            logger.info(
                "Embeddings enabled (backend=%s, model=%s).",
                settings.embedding_backend,
                settings.embedding_model,
            )
        except Exception:
            logger.warning(
                "Could not initialise embeddings (backend=%s); lexical fallback.",
                settings.embedding_backend,
                exc_info=True,
            )

    if settings.enable_llm_explanations:
        try:
            chat = OllamaChatProvider(
                settings.chat_model,
                settings.ollama_base_url,
                settings.llm_temperature,
                settings.llm_num_predict,
                disable_reasoning=settings.llm_disable_reasoning,
            )
            logger.info("LLM explanations enabled (model=%s).", settings.chat_model)
        except Exception:
            logger.warning("Could not initialise Ollama chat; template fallback.", exc_info=True)

    return embeddings, chat


def _model_present(name: str, models: list[str]) -> bool:
    """Match a configured model name against Ollama's tag list, tolerating an
    implicit ``:latest`` (e.g. ``bge-m3`` matches ``bge-m3:latest``)."""
    for m in models:
        if not m:
            continue
        if m == name or m == f"{name}:latest" or m.split(":", 1)[0] == name:
            return True
    return False


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
            "chat_model_present": _model_present(settings.chat_model, models),
        }
    except Exception as exc:
        return {"reachable": False, "base_url": settings.ollama_base_url, "error": str(exc)}
