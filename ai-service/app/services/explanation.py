"""Natural-language explanations for ranked replacements.

Per the MVP rule, the LLM does *not* choose replacements - Python ranks them
deterministically, and Ollama only writes a short, human-friendly justification
*after* ranking. The model is fed verified facts only (never asked to invent
numbers) to keep explanations grounded. If Ollama is disabled or unavailable, a
deterministic template explanation is used instead.
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional, Protocol

from app.logging_config import get_logger
from app.schemas import RequestedProduct
from app.services.scoring import ScoredCandidate

logger = get_logger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

SYSTEM_PROMPT = (
    "You are a procurement assistant for a B2B food-supply platform. A requested "
    "product is unavailable and the system has already chosen a replacement using "
    "deterministic scoring. Write ONE concise sentence (max 30 words) explaining why "
    "the replacement is a good fit. Use ONLY the facts provided - never invent prices, "
    "brands, or numbers. Be factual and business-like. No markdown, no preamble."
)


class ChatProvider(Protocol):
    """Minimal async chat interface (implemented by the Ollama wrapper)."""

    async def acomplete(self, system: str, user: str) -> str: ...


def _money(value: float) -> str:
    return f"{value:.2f}"


def template_explanation(requested: RequestedProduct, scored: ScoredCandidate) -> str:
    """Deterministic, always-available explanation built from the score facts."""
    f = scored.facts
    cand = scored.candidate
    bits: list[str] = []

    if f.same_category:
        bits.append("same product category")
    elif f.category_similarity >= 0.6:
        bits.append("closely related category")

    if f.is_preferred:
        bits.append("preferred contract supplier")
    elif f.is_under_contract:
        bits.append("covered by an existing contract")

    if f.cheaper_or_equal:
        if f.candidate_effective_price < f.requested_effective_price:
            bits.append(
                f"cheaper at {_money(f.candidate_effective_price)} vs "
                f"{_money(f.requested_effective_price)}"
            )
        else:
            bits.append("same price")
    else:
        bits.append(f"price within {f.price_delta_pct * 100:.0f}% of the original")

    if f.stock_ratio >= 1:
        bits.append("sufficient stock available")

    reason = "; ".join(bits) if bits else "best available match"
    return (
        f"'{cand.name}' is a strong replacement for '{requested.name}' "
        f"(score {scored.final_score}/93): {reason}."
    )


def _user_prompt(requested: RequestedProduct, scored: ScoredCandidate) -> str:
    f = scored.facts
    cand = scored.candidate
    lines = [
        f"Requested (unavailable): {requested.name}",
        f"Proposed replacement: {cand.name}" + (f" by {cand.brand}" if cand.brand else ""),
        f"Total fit score: {scored.final_score} out of 93",
        f"Same category: {'yes' if f.same_category else f'no (similarity {f.category_similarity:.2f})'}",
        f"Under contract: {'yes' if f.is_under_contract else 'no'}"
        + (" (preferred supplier)" if f.is_preferred else ""),
        f"Replacement price: {_money(f.candidate_effective_price)}; "
        f"original price: {_money(f.requested_effective_price)} "
        f"({'cheaper or equal' if f.cheaper_or_equal else f'{f.price_delta_pct * 100:.0f}% more'})",
        f"Stock vs demand ratio: {f.stock_ratio:.1f}x",
        f"Same unit of measure: {'yes' if f.same_unit else 'no'}; "
        f"same pack size: {'yes' if f.same_pack else 'no'}",
    ]
    return "Facts:\n" + "\n".join(f"- {line}" for line in lines)


class ExplanationService:
    """Generates explanations for a list of ranked candidates."""

    def __init__(self, chat: Optional[ChatProvider] = None, per_call_timeout: float = 20.0) -> None:
        self._chat = chat
        self._timeout = per_call_timeout

    @property
    def uses_llm(self) -> bool:
        return self._chat is not None

    async def annotate(
        self,
        requested: RequestedProduct,
        ranked: list[ScoredCandidate],
        use_ai: bool,
    ) -> list[ScoredCandidate]:
        """Attach an ``explanation``/``explanation_source`` to each candidate.

        LLM calls run concurrently; any individual failure falls back to the
        template for that candidate without affecting the others.
        """
        if not ranked:
            return ranked

        if not (use_ai and self._chat is not None):
            for scored in ranked:
                scored.explanation = template_explanation(requested, scored)
                scored.explanation_source = "template"
            return ranked

        async def _one(scored: ScoredCandidate) -> None:
            try:
                raw = await asyncio.wait_for(
                    self._chat.acomplete(SYSTEM_PROMPT, _user_prompt(requested, scored)),
                    timeout=self._timeout,
                )
                text = _THINK_RE.sub("", raw or "").strip().strip('"')
                if not text:
                    raise ValueError("empty completion")
                scored.explanation = text
                scored.explanation_source = "ollama"
            except Exception:  # pragma: no cover - network/runtime failure path
                logger.warning(
                    "Ollama explanation failed for %s; using template.",
                    scored.candidate.id,
                    exc_info=True,
                )
                scored.explanation = template_explanation(requested, scored)
                scored.explanation_source = "template"

        await asyncio.gather(*(_one(scored) for scored in ranked))
        return ranked
