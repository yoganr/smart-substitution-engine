"""Conversational chatbot over the Smart Substitution Engine.

A single LLM **orchestrator** (``router.Orchestrator``) classifies each user turn
and dispatches to small specialist **agents** (``agents.Agents``) wired together
as a LangGraph state machine (``graph.build_chat_graph``). The agents reuse the
existing deterministic recommendation engine and Atlas catalog — the LLM only
routes and phrases, it never invents data or chooses replacements.
"""

from __future__ import annotations

from app.chat.service import ChatService, build_chat_service

__all__ = ["ChatService", "build_chat_service"]
