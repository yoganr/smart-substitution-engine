"""ChatService — the facade the API calls: one message in, one answer out.

It owns the compiled graph + per-session memory, mints a session id on the first
turn, and degrades gracefully if a turn blows up. The LLM router uses the SAME
``qwen3.5`` chat model as the rest of the service, via a lightweight
``OllamaChatProvider`` (no embedding model is loaded here).
"""

from __future__ import annotations

import uuid
from typing import Optional

from app.chat.agents import Agents
from app.chat.graph import build_chat_graph
from app.chat.memory import SessionStore
from app.chat.router import Orchestrator
from app.config import Settings
from app.logging_config import get_logger
from app.providers import OllamaChatProvider
from app.schemas import ChatResponse

logger = get_logger(__name__)


class ChatService:
    def __init__(self, graph, store: SessionStore) -> None:
        self._graph = graph
        self._store = store

    async def handle(self, session_id: Optional[str], message: str) -> ChatResponse:
        sid = session_id or uuid.uuid4().hex
        state = {
            "session_id": sid,
            "message": message,
            "history": self._store.get_history(sid),
            "context": self._store.get_context(sid),
        }
        try:
            result = await self._graph.ainvoke(state)
        except Exception:  # pragma: no cover - defensive: never 500 the widget
            logger.exception("Chat graph failed for session %s", sid)
            return ChatResponse(
                session_id=sid,
                reply="Sorry — something went wrong on my side. Please try again.",
                suggestions=["What can you do?"],
                intent="guide",
            )

        reply = result.get("reply") or ""
        self._store.append(sid, "user", message)
        self._store.append(sid, "assistant", reply)
        self._store.set_context(sid, result.get("context") or {})
        return ChatResponse(
            session_id=sid,
            reply=reply,
            suggestions=result.get("suggestions") or [],
            cards=result.get("cards") or [],
            intent=result.get("intent") or "guide",
        )


def build_chat_service(settings: Settings, engine, repo) -> ChatService:
    """Wire the orchestrator + agents + memory into a ready ChatService.

    ``engine`` is the already-built ``RecommendationEngine`` (shares the loaded
    embedding model); ``repo`` is the optional Atlas catalog repository.
    """
    chat = None
    if settings.enable_llm_explanations:
        try:
            chat = OllamaChatProvider(
                settings.chat_model,
                settings.ollama_base_url,
                settings.llm_temperature,
                num_predict=256,
                disable_reasoning=settings.llm_disable_reasoning,
            )
        except Exception:  # pragma: no cover - graceful degradation to heuristics
            logger.warning("Could not init chat LLM for the bot; heuristic routing only.", exc_info=True)

    orchestrator = Orchestrator(chat_provider=chat, repo=repo, settings=settings)
    agents = Agents(engine=engine, repo=repo, settings=settings)
    graph = build_chat_graph(orchestrator, agents)
    logger.info(
        "Chat service ready (llm_router=%s, catalog=%s).", chat is not None, repo is not None
    )
    return ChatService(graph, store=SessionStore())
