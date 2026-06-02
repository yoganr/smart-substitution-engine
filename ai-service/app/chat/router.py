"""The orchestrator: classify a user turn and extract its entities.

Strategy is a **hybrid** so it stays reliable on a tiny LLM:

1. If we're mid-flow (a slot is pending), treat the message as the answer -
   unless it clearly changes the subject.
2. Deterministic keyword routing handles the common, unambiguous cases with no
   LLM round-trip (fast).
3. Only genuinely ambiguous messages fall through to the LLM classifier.
4. A final heuristic decides between "probably a product" and "off-topic".

The orchestrator only decides intent + slots; the specialist agents do the work.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

from app.chat.prompts import ROUTER_SYSTEM, router_user
from app.chat.state import (
    ALL_INTENTS,
    INTENT_FIND_REPLACEMENT,
    INTENT_GUIDE,
    INTENT_OFF_TOPIC,
    INTENT_PRODUCT_INFO,
    INTENT_SIMILAR,
    INTENT_STOCK_OVERVIEW,
    PRODUCT_INTENTS,
    clear_pending,
)
from app.logging_config import get_logger

logger = get_logger(__name__)

# --- Keyword vocabularies ---------------------------------------------------
GREETINGS = {"hi", "hello", "hey", "yo", "hiya", "howdy", "greetings", "sup"}
HELP_PHRASES = (
    "help", "what can you", "what do you do", "what are you", "who are you",
    "how do i", "how does this", "how to use", "guide me", "get started",
    "capabilities", "menu", "options",
)
REPLACE_PHRASES = (
    "replace", "replacement", "substitut", "out of stock", "out-of-stock",
    "outofstock", "unavailable", "sold out", "soldout", "instead of",
    "can't get", "cant get", "cannot get", "no stock", "ran out", "not available",
)
SIMILAR_PHRASES = (
    "similar", "alternative", "comparable", "compare", "other option",
    "options for", "what else", "like this", "products like",
)
INFO_PHRASES = (
    "in stock", "stock of", "stock for", "stock level", "how much", "price of",
    "price for", "cost of", "do you have", "do you stock", "do you sell",
    "is there any", "available", "inventory", "details of", "info on",
)
OFF_TOPIC_TOKENS = {
    "weather", "joke", "jokes", "poem", "poems", "story", "stories", "song",
    "songs", "lyrics", "football", "soccer", "basketball", "sport", "sports",
    "news", "bitcoin", "crypto", "movie", "movies", "film", "films", "president",
    "recipe", "recipes", "translate", "translation", "python", "javascript",
    "code", "coding", "program", "programming", "algorithm", "math",
}
OFF_TOPIC_PHRASES = (
    "stock market", "capital of", "who is", "who was", "meaning of life",
    "what time", "what day", "2+2", "tell me a joke", "write code",
)
QUESTION_STARTS = (
    "who", "what", "when", "where", "why", "how", "is", "are", "can", "do",
    "does", "tell", "explain", "define",
)
CANCEL_WORDS = {
    "cancel", "never mind", "nevermind", "stop", "quit", "exit", "forget it",
    "start over", "reset",
}
# "What's out of stock?" - a listing question, NOT a specific-product replacement.
_OOS_TRIGGERS = (
    "out of stock", "out-of-stock", "outofstock", "sold out", "soldout",
    "unavailable", "low stock", "low on stock", "running low", "depleted",
)
_OOS_LISTY_STARTS = (
    "which", "what", "whats", "what's", "list", "show", "any", "anything",
    "is", "are", "do",
)

# Lead-in phrases stripped from the front of a message to recover the product.
_LEADINS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^(hi|hello|hey)[,!.\s]+",
        r"^(ok|okay|yeah|yes|sure)[,!.\s]+",
        r"^(no|nope|nah)[,!.\s]+",
        r"^(actually|instead|rather|well)[,!.\s]+",
        r"^(can|could|would|will)\s+you(\s+please)?\s+",
        r"^please\s+",
        r"^i(\s*'?m| am)?\s+(just\s+)?(looking for|searching for|trying to find|after)\s+(a|an|some|the)?\s*",
        r"^(i\s+)?(just\s+)?(would\s+like|want|need|require|wanna)\s+(to\s+\w+\s+)?(a|an|some|the)?\s*",
        r"^(to\s+)?(find|get|show|suggest|recommend|give|fetch|look\s+for|search\s+for)\s*(me)?\s*(a|an|some|the)?\s*",
        r"^(a|an|some|the)?\s*(good|suitable|cheaper|better|nice)?\s*(replacement|substitute|substitution|alternative|sub)s?\s*(for|to|of)?\s*",
        r"^(similar|comparable)\s*(products?|items?)?\s*(to|for|like)?\s*",
        r"^(what'?s|what is|what are)\s+the\s+(price|cost|stock|availability|details?)\s+(of|for)\s+",
        r"^(price|cost|stock|availability|details?|info|information)\s+(of|for|on)\s+",
        r"^(do|does)\s+(you|we)\s+(have|stock|sell|carry|got)\s+(any\s+)?",
        r"^(is\s+there\s+(any)?|have\s+you\s+got)\s+",
        r"^how\s+much\s+(is|are|does|do)\s*(a|an|the)?\s*",
        r"^how\s+(many|much)\s+(of\s+)?",
        r"^check\s+(if\s+|whether\s+|how\s+(many|much)\s+)?",
        r"^(tell|show)\s+me\s+(how\s+(many|much)\s+)?",
        r"^(out of stock|out-of-stock|unavailable|sold out)[:,]?\s+",
        r"^instead of\s+",
        r"^(is|are|was|were)\s+(the\s+)?",
    )
]
# Trailing "…in stock?", "…'s price", "… availability" clauses to drop.
_TRAILING_INFO = re.compile(
    r"(\s+(in\s+stock|available|on\s+hand|left|on\s+the\s+shelf)|('?s)?\s+(price|cost|stock|availability|details?|info))\s*\??$",
    re.IGNORECASE,
)
# Only treat a trailing "…, I need 20" as a quantity clause when a NUMBER follows -
# otherwise "…, I want boiled chicken" would be wrongly truncated to nothing.
_TRAILING_QTY = re.compile(
    r"[,;:]?\s*(please\s*)?(i\s*(need|want|require|will take)|need|want|require|order|buy|qty|quantity)\s+\d+\b.*$",
    re.IGNORECASE,
)
_TRAILING_X = re.compile(r"\s+x\s*\d+\s*$", re.IGNORECASE)
_QTY_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"(?:need|want|order|require|qty|quantity|buy|get)\s+(\d+(?:\.\d+)?)",
        r"\bx\s*(\d+(?:\.\d+)?)\b",
        r"(\d+(?:\.\d+)?)\s*(?:units?|pcs|pieces?|boxes?|packs?|cases?|cartons?)\b",
    )
]
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class Orchestrator:
    """LangGraph node: ``state -> {intent, slots, context}``."""

    def __init__(self, chat_provider=None, repo=None, settings=None) -> None:
        self._chat = chat_provider
        self._repo = repo
        self._timeout = getattr(settings, "ollama_timeout", 20.0)
        self._companies_cache: Optional[list[dict]] = None

    async def __call__(self, state: dict) -> dict:
        message = (state.get("message") or "").strip()
        context = dict(state.get("context") or {})
        slots = {"product": "", "quantity": None, "company": ""}

        if not message:
            return self._result(INTENT_GUIDE, slots, context)

        low = message.lower()

        # 0. Bail out of any in-progress flow on an explicit cancel.
        if low.strip(" .!?") in CANCEL_WORDS:
            return self._result(INTENT_GUIDE, slots, clear_pending(context))

        # 0b. "What's out of stock?" - a listing query. Checked early so the
        # "out of stock" phrase doesn't get routed to a specific-product replacement.
        if self._is_stock_overview(low):
            return self._result(INTENT_STOCK_OVERVIEW, slots, clear_pending(context))

        pending_intent = context.get("pending_intent")
        pending_slot = context.get("pending_slot")

        # 1. Mid-flow: is the user answering a question we asked?
        if pending_intent and pending_slot:
            strong = self._keyword_intent(low)
            if strong and strong != pending_intent:
                context = clear_pending(context)  # user changed the subject
            else:
                return self._fill_slot(message, low, pending_intent, pending_slot, context)

        # 2. Fast deterministic routing.
        slots["quantity"] = self._extract_quantity(low)
        slots["company"] = await self._match_company(low)

        kw = self._keyword_intent(low)
        if kw == INTENT_GUIDE:
            return self._result(INTENT_GUIDE, slots, context)
        if kw in PRODUCT_INTENTS:
            slots["product"] = self._extract_product(message)
            return self._result(kw, slots, context)
        if self._off_topic_signal(low):
            return self._result(INTENT_OFF_TOPIC, slots, context)

        # 3. Ambiguous → ask the LLM.
        llm = await self._classify_llm(message)
        if llm:
            intent = llm["intent"]
            if intent in PRODUCT_INTENTS:
                slots["product"] = self._extract_product(message, llm.get("product"))
                slots["quantity"] = slots["quantity"] or llm.get("quantity")
                return self._result(intent, slots, context)
            if intent in (INTENT_OFF_TOPIC, INTENT_GUIDE, INTENT_STOCK_OVERVIEW):
                return self._result(intent, slots, context)

        # 4. Final heuristic.
        if self._looks_like_question(low) and not self._looks_like_product(low):
            return self._result(INTENT_OFF_TOPIC, slots, context)
        if self._looks_like_product(low):
            slots["product"] = self._extract_product(message)
            return self._result(INTENT_PRODUCT_INFO, slots, context)
        return self._result(INTENT_GUIDE, slots, context)

    # -- slot filling (multi-turn) ---------------------------------------
    def _fill_slot(self, message, low, intent, slot, context):
        slots = {"product": "", "quantity": None, "company": ""}
        if slot in ("product", "disambiguation"):
            picked = self._resolve_disambiguation(message, low, context)
            # An exact pick wins; otherwise treat the turn as a refined product
            # query (cleaned), falling back to the raw message.
            slots["product"] = picked or self._extract_product(message) or message.strip()
            slots["quantity"] = self._extract_quantity(low) or context.get("quantity")
            return self._result(intent, slots, clear_pending(context))
        if slot == "quantity":
            qty = self._extract_quantity(low) or self._bare_number(low)
            if qty:
                context = dict(context)
                context["quantity"] = qty
            slots["quantity"] = qty
            return self._result(intent, slots, clear_pending(context))
        return self._result(intent, slots, clear_pending(context))

    def _resolve_disambiguation(self, message, low, context) -> Optional[str]:
        """If we offered a numbered choice, map the user's pick to a product name."""
        options = context.get("disambiguation") or []
        if not options:
            return None
        num = self._bare_number(low)
        if num is not None:
            idx = int(num) - 1
            if 0 <= idx < len(options):
                return options[idx].get("name")
        for opt in options:  # exact-ish name match
            name = (opt.get("name") or "").lower()
            if name and (name in low or low in name):
                return opt.get("name")
        return None

    # -- keyword routing --------------------------------------------------
    def _keyword_intent(self, low: str) -> Optional[str]:
        first = low.split()[0].strip(",.!?") if low.split() else ""
        if first in GREETINGS or low.startswith(("good morning", "good afternoon", "good evening")):
            if len(low.split()) <= 4:
                return INTENT_GUIDE
        if any(p in low for p in HELP_PHRASES):
            return INTENT_GUIDE
        if any(p in low for p in REPLACE_PHRASES):
            return INTENT_FIND_REPLACEMENT
        if any(p in low for p in SIMILAR_PHRASES):
            return INTENT_SIMILAR
        if any(p in low for p in INFO_PHRASES):
            return INTENT_PRODUCT_INFO
        return None

    def _is_stock_overview(self, low: str) -> bool:
        """True for general "what's out of stock?" questions (no specific product)."""
        if not any(t in low for t in _OOS_TRIGGERS):
            return False
        first = low.split()[0].strip(",.!?") if low.split() else ""
        if first in ("which", "what", "whats", "what's", "list", "show"):
            return True
        listy = (
            "anything", "everything", "any products", "what products",
            "which products", "any items", "is there any", "are there any",
            "do you have any",
        )
        return any(p in low for p in listy)

    def _off_topic_signal(self, low: str) -> bool:
        tokens = set(re.findall(r"[a-z0-9+]+", low))
        if tokens & OFF_TOPIC_TOKENS:
            return True
        return any(p in low for p in OFF_TOPIC_PHRASES)

    def _looks_like_question(self, low: str) -> bool:
        first = low.split()[0].strip(",.!?") if low.split() else ""
        return low.endswith("?") or first in QUESTION_STARTS

    def _looks_like_product(self, low: str) -> bool:
        words = low.split()
        if not (1 <= len(words) <= 6):
            return False
        if low.endswith("?") or (words[0].strip(",.!?") in QUESTION_STARTS):
            return False
        return bool(re.search(r"[a-z]", low))

    # -- entity extraction -----------------------------------------------
    def _extract_product(self, message: str, llm_product: Optional[str] = None) -> str:
        cand = (llm_product or "").strip().strip('"').strip()
        if cand and 1 <= len(cand) <= 60 and cand.lower() not in ("none", "null", "empty", "n/a"):
            return cand
        return self._strip_leadins(message)

    def _strip_leadins(self, message: str) -> str:
        text = message.strip()
        for _ in range(3):  # peel nested lead-ins, e.g. "can you find a substitute for ..."
            before = text
            for pat in _LEADINS:
                text = pat.sub("", text).strip()
            if text == before:
                break
        text = _TRAILING_QTY.sub("", text)
        text = _TRAILING_X.sub("", text)
        text = _TRAILING_INFO.sub("", text)
        return text.strip(" ,.?!\"'")

    def _extract_quantity(self, low: str) -> Optional[float]:
        for pat in _QTY_PATTERNS:
            m = pat.search(low)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    continue
        return None

    def _bare_number(self, low: str) -> Optional[float]:
        m = re.search(r"\b(\d+(?:\.\d+)?)\b", low)
        return float(m.group(1)) if m else None

    async def _match_company(self, low: str) -> str:
        if self._repo is None:
            return ""
        if self._companies_cache is None:
            try:
                self._companies_cache = await self._repo.list_companies()
            except Exception:  # pragma: no cover - depends on a live server
                self._companies_cache = []
        for c in self._companies_cache:
            name = (c.get("name") or "").lower()
            if name and len(name) >= 4 and name in low:
                return c.get("name", "")
        return ""

    # -- LLM fallback -----------------------------------------------------
    async def _classify_llm(self, message: str) -> Optional[dict]:
        if self._chat is None:
            return None
        try:
            raw = await asyncio.wait_for(
                self._chat.acomplete(ROUTER_SYSTEM, router_user(message)), timeout=self._timeout
            )
        except Exception:  # pragma: no cover - network/runtime failure path
            logger.warning("Router LLM call failed; using heuristic.", exc_info=True)
            return None
        data = self._parse_json(raw)
        if not isinstance(data, dict):
            return None
        intent = str(data.get("intent", "")).strip().lower()
        if intent not in ALL_INTENTS:
            return None
        qty = data.get("quantity")
        try:
            qty = float(qty) if qty not in (None, "", "null") else None
        except (TypeError, ValueError):
            qty = None
        return {
            "intent": intent,
            "product": str(data.get("product") or ""),
            "quantity": qty,
            "company": str(data.get("company") or ""),
        }

    @staticmethod
    def _parse_json(raw: str) -> Optional[dict]:
        text = _THINK_RE.sub("", raw or "")
        match = _JSON_RE.search(text)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _result(intent: str, slots: dict, context: dict) -> dict:
        return {"intent": intent, "slots": slots, "context": context}
