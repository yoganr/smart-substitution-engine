"""Shared state + intent vocabulary for the chat graph."""

from __future__ import annotations

from typing import Optional, TypedDict

from app.schemas import ChatCard

# --- Intents (the orchestrator routes on exactly one of these) --------------
INTENT_GUIDE = "guide"
INTENT_FIND_REPLACEMENT = "find_replacement"
INTENT_SIMILAR = "similar_search"
INTENT_PRODUCT_INFO = "product_info"
INTENT_OFF_TOPIC = "off_topic"

ALL_INTENTS = frozenset(
    {INTENT_GUIDE, INTENT_FIND_REPLACEMENT, INTENT_SIMILAR, INTENT_PRODUCT_INFO, INTENT_OFF_TOPIC}
)

# Intents that need a concrete product to act on.
PRODUCT_INTENTS = frozenset({INTENT_FIND_REPLACEMENT, INTENT_SIMILAR, INTENT_PRODUCT_INFO})

# Default order quantity when the user does not state one (kept modest so the
# stock check stays meaningful; the bot tells the user it assumed this).
DEFAULT_QUANTITY = 10


class WorkingContext(TypedDict, total=False):
    """Per-session memory carried across turns."""

    company_id: str
    company_name: str
    last_product: dict          # the most recently resolved catalog product
    quantity: float
    pending_intent: str         # intent waiting on a slot to be filled
    pending_slot: str           # "product" | "quantity" | "disambiguation"
    disambiguation: list[dict]  # candidate products the user is choosing between


class ChatState(TypedDict, total=False):
    # --- input ---
    session_id: str
    message: str
    history: list[dict]         # [{"role": "...", "content": "..."}]
    context: WorkingContext

    # --- set by the orchestrator ---
    intent: str
    slots: dict                 # {"product": str, "quantity": float|None, "company": str}

    # --- set by an agent (the turn's answer) ---
    reply: str
    suggestions: list[str]
    cards: list[ChatCard]


def empty_context() -> WorkingContext:
    return {}


def clear_pending(context: WorkingContext) -> WorkingContext:
    """Return a copy of ``context`` with any pending slot/intent removed."""
    ctx = dict(context)
    ctx.pop("pending_intent", None)
    ctx.pop("pending_slot", None)
    ctx.pop("disambiguation", None)
    return ctx
