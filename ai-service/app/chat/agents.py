"""Specialist agents — the LangGraph nodes the orchestrator dispatches to.

Each agent takes the graph ``state`` and returns the turn's answer
(``reply`` + ``suggestions`` + ``cards`` + updated ``context``). They reuse the
existing deterministic ``RecommendationEngine`` and the Atlas
``MongoCatalogRepository``; the LLM never picks replacements here.
"""

from __future__ import annotations

import re

from app.chat.state import (
    DEFAULT_QUANTITY,
    INTENT_FIND_REPLACEMENT,
    INTENT_PRODUCT_INFO,
    INTENT_SIMILAR,
)
from app.logging_config import get_logger
from app.schemas import (
    CandidateProduct,
    ChatCard,
    Company,
    ContractItem,
    ReplacementRequest,
    RequestedProduct,
)
from app.services.similarity import lexical_similarity

logger = get_logger(__name__)

_NO_CATALOG = (
    "I can't reach the product catalog right now, so I can't look that up. "
    "Please try again in a moment."
)
_INTENT_VERB = {
    INTENT_FIND_REPLACEMENT: "find a replacement for",
    INTENT_SIMILAR: "see alternatives for",
    INTENT_PRODUCT_INFO: "check",
}

# Filler / command words that must never be used as a product search term on
# their own (e.g. "to" must not substring-match "Tomatoes").
_STOPWORDS = {
    "a", "an", "the", "to", "i", "im", "me", "my", "some", "any", "of", "for", "on",
    "is", "are", "do", "you", "we", "have", "has", "want", "wants", "need", "needs",
    "require", "find", "get", "show", "give", "suggest", "recommend", "look", "search",
    "replacement", "replacements", "substitute", "substitutes", "substitution",
    "alternative", "alternatives", "similar", "comparable", "please", "stock", "in",
    "no", "nope", "nah", "none", "not", "actually", "instead", "rather", "well",
    "and", "or", "with", "that", "this", "it", "one", "ones", "item", "items",
    "product", "products", "thanks", "thank", "ok", "okay", "yes", "yeah", "sure",
}
# Phrases that mean "none of the options you showed me".
_REJECTIONS = {
    "no", "nope", "nah", "none", "neither", "none of these", "none of those",
    "not these", "not those", "not that", "other", "others", "something else",
    "different", "anything else",
}


class Agents:
    def __init__(self, engine=None, repo=None, settings=None) -> None:
        self._engine = engine
        self._repo = repo
        self._settings = settings

    # ====================================================================
    # Conversational agents
    # ====================================================================
    async def guide(self, state: dict) -> dict:
        context = dict(state.get("context") or {})
        msg = (state.get("message") or "").lower()
        greeted = msg.split()[0].strip(",.!?") in ("hi", "hello", "hey", "yo") if msg.split() else False
        lead = "👋 Hi! I'm your **Substitution Assistant**." if greeted else "Here's how I can help. 👇"
        reply = (
            f"{lead}\n\n"
            "When a product is **out of stock**, I find the best alternatives for you — "
            "no forms, just ask. I can:\n\n"
            "• 🔁 **Find a replacement** for an out-of-stock product\n"
            "• 🔍 **Show similar products** in the catalog\n"
            "• 📦 **Check stock & price** for any product\n\n"
            "Just name a product to get started."
        )
        suggestions = [
            "Find a replacement for Chicken Breast 2kg",
            "Show similar products to Beef Mince",
            "Check stock for Chicken Breast 2kg",
        ]
        return self._answer(reply, suggestions, [], context)

    async def refusal(self, state: dict) -> dict:
        context = dict(state.get("context") or {})
        reply = (
            "I'm the **Substitution Assistant** for this product catalog, so I can only help with "
            "**product substitutions, similar products, and stock or pricing**. "
            "I'm not able to help with that — but I'd be glad to find you a replacement or alternative."
        )
        suggestions = ["Find a replacement", "Show similar products", "What can you do?"]
        return self._answer(reply, suggestions, [], context)

    # ====================================================================
    # Catalog agents
    # ====================================================================
    async def substitution(self, state: dict) -> dict:
        slots = state.get("slots") or {}
        context = dict(state.get("context") or {})
        if self._repo is None:
            return self._answer(_NO_CATALOG, ["What can you do?"], [], context)

        query = (slots.get("product") or "").strip()
        product = context["last_product"] if (not query and context.get("last_product")) else None
        if product is None:
            product, disambig = await self._resolve(query)
            if product is None:
                return self._ask_product(INTENT_FIND_REPLACEMENT, query, disambig, context)

        company = await self._company(context, slots.get("company") or "")
        context["company_id"] = company.get("id")
        context["company_name"] = company.get("name", "")
        explicit_qty = slots.get("quantity") or context.get("quantity")
        qty = float(explicit_qty or DEFAULT_QUANTITY)
        context["quantity"] = qty
        context["last_product"] = product
        context.pop("disamb_ids", None)
        name = product.get("name", "the product")

        stock = await self._repo.get_stock(product["id"])
        if stock is not None and stock >= qty:
            reply = (
                f"✅ **{name}** is currently in stock — {int(stock)} available "
                f"(you need {int(qty)}), so no replacement is required."
            )
            suggestions = [f"Show similar products to {name}", "Check another product"]
            return self._answer(reply, suggestions, [], context)

        try:
            contract_items = await self._repo.get_contract_items(company["id"])
            contract_price = {c["product_id"]: c.get("contract_price") for c in contract_items}
            raw = await self._repo.get_candidates(product["category_id"], product["id"])
            candidates = [
                CandidateProduct(**{**c, "contract_price": contract_price.get(c["id"])}) for c in raw
            ]
            request = ReplacementRequest(
                company=Company(**company),
                requested_product=RequestedProduct(**product),
                requested_quantity=qty,
                contract_items=[ContractItem(**c) for c in contract_items],
                candidate_products=candidates,
                max_results=3,
                use_ai_explanation=True,
            )
            response = await self._engine.recommend(request)
        except Exception:  # pragma: no cover - live engine/Atlas failure path
            logger.warning("Substitution failed for %s", product.get("id"), exc_info=True)
            return self._answer(
                "Sorry — I hit a problem while looking up replacements. Please try again.",
                ["What can you do?"], [], context,
            )

        reps = response.replacements
        if not reps:
            reason = response.no_candidates_reason or "no in-stock candidate passed the safety checks."
            reply = f"I looked for replacements for **{name}**, but {self._lower_first(reason)}"
            suggestions = [f"Show similar products to {name}", "Check another product"]
            return self._answer(reply, suggestions, [], context)

        cards = [self._replacement_card(r, i, product.get("category_id")) for i, r in enumerate(reps, 1)]
        top = reps[0]
        plural = "s" if len(reps) > 1 else ""
        note = "" if explicit_qty else f" _(assuming {int(qty)} units — tell me the exact amount to refine.)_"
        reply = (
            f"**{name}** is short on stock. Here {'are' if len(reps) > 1 else 'is'} the top "
            f"{len(reps)} replacement{plural} — **{top.name}** leads at **{top.confidence_pct}% "
            f"confidence**.{note}"
        )
        suggestions = [
            f"Show similar products to {name}",
            f"Check stock for {top.name}",
            "Find another replacement",
        ]
        return self._answer(reply, suggestions, cards, context)

    async def similar(self, state: dict) -> dict:
        slots = state.get("slots") or {}
        context = dict(state.get("context") or {})
        retrieval = getattr(self._engine, "retrieval", None)
        vector_ok = bool(retrieval and retrieval.available)
        if self._repo is None and not vector_ok:
            return self._answer(_NO_CATALOG, ["What can you do?"], [], context)

        query = (slots.get("product") or "").strip()
        product = None
        if not query and context.get("last_product"):
            product = context["last_product"]
            query = product.get("name", "")
        elif self._repo is not None and query:
            product, disambig = await self._resolve(query)
            if product is None and disambig:
                return self._ask_product(INTENT_SIMILAR, query, disambig, context)
        if product:
            context["last_product"] = product
            context.pop("disamb_ids", None)
            query = query or product.get("name", "")

        cards: list[ChatCard] = []
        if vector_ok and query:
            try:
                hits = await retrieval.search_similar(
                    name=query,
                    category_id=(product or {}).get("category_id"),
                    top_k=6,
                    active_only=True,
                    exclude_ids=[product["id"]] if product else [],
                )
                cards = [self._similar_card(h) for h in hits]
            except Exception:  # pragma: no cover - live-server failure path
                logger.warning("Vector similar search failed; trying catalog.", exc_info=True)

        if not cards and product and self._repo is not None:
            raw = await self._repo.get_candidates(product["category_id"], product["id"])
            ranked = sorted(
                raw, key=lambda r: lexical_similarity(query, r.get("name", "")), reverse=True
            )[:6]
            cards = [
                self._similar_card(
                    {
                        "product_id": r["id"],
                        "name": r["name"],
                        "category_id": r["category_id"],
                        "score": lexical_similarity(query, r.get("name", "")),
                    }
                )
                for r in ranked
            ]

        if not cards:
            if product is None:
                return self._ask_product(INTENT_SIMILAR, query, [], context)
            reply = f"I couldn't find similar in-stock products for **{query}** right now."
            return self._answer(reply, ["Find a replacement", "Check another product"], [], context)

        name = (product or {}).get("name") or query
        reply = f"Here are products similar to **{name}**:"
        suggestions = [f"Find a replacement for {name}", "Check another product", "What can you do?"]
        return self._answer(reply, suggestions, cards, context)

    async def product_info(self, state: dict) -> dict:
        slots = state.get("slots") or {}
        context = dict(state.get("context") or {})
        if self._repo is None:
            return self._answer(_NO_CATALOG, ["What can you do?"], [], context)

        query = (slots.get("product") or "").strip()
        product = context["last_product"] if (not query and context.get("last_product")) else None
        if product is None:
            product, disambig = await self._resolve(query)
            if product is None:
                return self._ask_product(INTENT_PRODUCT_INFO, query, disambig, context)
        context["last_product"] = product
        context.pop("disamb_ids", None)

        stock = await self._repo.get_stock(product["id"])
        name = product.get("name", "")
        price = product.get("base_price")
        unit = product.get("unit") or "unit"
        in_stock = stock is not None and stock > 0
        status = "✅ in stock" if in_stock else "⚠️ out of stock"
        price_txt = f"{price:.2f}/{unit}" if isinstance(price, (int, float)) else "price unavailable"
        stock_txt = f"{int(stock)} available" if stock is not None else "stock unknown"
        reply = f"**{name}** — {status}. Price {price_txt}, {stock_txt}."
        card = self._product_card(product, stock)
        if in_stock:
            suggestions = [f"Show similar products to {name}", "Check another product"]
        else:
            suggestions = [f"Find a replacement for {name}", f"Show similar products to {name}"]
        return self._answer(reply, suggestions, [card], context)

    # ====================================================================
    # Helpers
    # ====================================================================
    async def _resolve(self, query: str):
        """``query -> (product | None, disambiguation[])``, robust to messy input."""
        query = (query or "").strip()
        if self._repo is None or not query:
            return None, []
        rows = await self._search_variants(query)
        if not rows:
            return None, []
        ranked, seen = [], set()
        for r in sorted(rows, key=lambda r: lexical_similarity(query, r.get("name", "")), reverse=True):
            if r.get("id") in seen:
                continue
            seen.add(r.get("id"))
            ranked.append(r)
        top_sim = lexical_similarity(query, ranked[0].get("name", ""))
        if len(ranked) == 1 or top_sim >= 0.85:
            return ranked[0], []
        second_sim = lexical_similarity(query, ranked[1].get("name", ""))
        if top_sim - second_sim >= 0.2:
            return ranked[0], []
        return None, ranked[:4]

    async def _search_variants(self, query: str) -> list[dict]:
        """Try the whole phrase, then shorter phrases / tokens built ONLY from
        meaningful words (so "to"/"a"/"replacement" never match stray products)."""
        rows = await self._repo.search_products(query, limit=8)
        if rows:
            return rows
        sig = [
            t for t in re.split(r"\s+", query.lower())
            if len(t) >= 3 and t not in _STOPWORDS
        ]
        for n in range(len(sig), 0, -1):  # longest meaningful prefix first
            rows = await self._repo.search_products(" ".join(sig[:n]), limit=8)
            if rows:
                return rows
        for t in sorted(sig, key=len, reverse=True):  # then individual words
            rows = await self._repo.search_products(t, limit=8)
            if rows:
                return rows
        return []

    async def _company(self, context: dict, mentioned: str) -> dict:
        if mentioned and self._repo is not None:
            try:
                for c in await self._repo.list_companies():
                    if mentioned.lower() in (c.get("name", "").lower()):
                        return c
            except Exception:  # pragma: no cover
                pass
        if context.get("company_id"):
            return {"id": context["company_id"], "name": context.get("company_name", "")}
        if self._repo is not None:
            try:
                companies = await self._repo.list_companies(limit=1)
                if companies:
                    return companies[0]
            except Exception:  # pragma: no cover
                pass
        return {"id": "company_001", "name": "your company"}

    def _ask_product(self, intent: str, query: str, disambig: list, context: dict) -> dict:
        context = dict(context)
        context["pending_intent"] = intent
        ql = (query or "").strip().lower().strip(".!?")
        is_rejection = ql in _REJECTIONS or any(
            ql.startswith(r + " ") or ql == r for r in ("no", "nope", "none", "not")
        )

        if disambig:
            ids = sorted(str(d.get("id")) for d in disambig)
            repeated = context.get("disamb_ids") == ids  # same list as last turn?
            context["pending_slot"] = "disambiguation"
            context["disambiguation"] = [{"id": d.get("id"), "name": d.get("name")} for d in disambig]
            context["disamb_ids"] = ids
            lines = "\n".join(f"{i}. {d.get('name')}" for i, d in enumerate(disambig, 1))
            # Be honest when the user asked for an attribute we don't carry
            # (e.g. "boiled" chicken) instead of silently re-listing.
            unmatched = self._unmatched_terms(query, disambig)
            note = f"I don't stock a **{unmatched[0]}** option specifically. " if unmatched else ""
            if repeated or is_rejection or unmatched:
                reply = (
                    f"{note}Here are the closest products I have — **tap one** below "
                    f"or type its exact name:\n\n{lines}"
                )
            else:
                reply = f"I found a few matches — which one did you mean?\n\n{lines}"
            suggestions = [d.get("name") for d in disambig][:4]
            return self._answer(reply, suggestions, [], context)

        # No candidates at all.
        context["pending_slot"] = "product"
        context.pop("disambiguation", None)
        context.pop("disamb_ids", None)
        verb = _INTENT_VERB.get(intent, "look up")
        if is_rejection:
            reply = "No problem — just tell me the product name you have in mind and I'll take it from there."
        elif query:
            reply = (
                f'I couldn\'t find a product matching **"{query}"** in the catalog. '
                "Try the exact product name, or pick one below."
            )
        else:
            reply = f"Sure — which product would you like to {verb}?"
        suggestions = ["Chicken Breast 2kg", "Beef Mince 5% Fat 1kg", "What can you do?"]
        return self._answer(reply, suggestions, [], context)

    @staticmethod
    def _unmatched_terms(query: str, options: list) -> list[str]:
        """Meaningful words in the query that appear in NONE of the option names."""
        names = " ".join((o.get("name") or "").lower() for o in options)
        out = []
        for t in re.split(r"\s+", (query or "").lower()):
            t = t.strip(",.!?")
            if len(t) >= 3 and t not in _STOPWORDS and t not in names:
                out.append(t)
        return out

    # -- card builders ----------------------------------------------------
    @staticmethod
    def _replacement_card(rep, rank: int, category_id=None) -> ChatCard:
        return ChatCard(
            type="replacement",
            product_id=rep.product_id,
            name=rep.name,
            category_id=category_id,
            brand=rep.brand,
            unit=rep.unit,
            rank=rank,
            final_score=rep.final_score,
            confidence_pct=rep.confidence_pct,
            confidence_label=rep.confidence_label,
            score_breakdown=rep.score_breakdown,
            explanation=rep.explanation,
            effective_price=rep.effective_price,
            stock_quantity=rep.stock_quantity,
            is_preferred=rep.is_preferred,
            is_under_contract=rep.is_under_contract,
        )

    @staticmethod
    def _similar_card(hit: dict) -> ChatCard:
        return ChatCard(
            type="similar",
            product_id=hit.get("product_id"),
            name=hit.get("name", ""),
            category_id=hit.get("category_id"),
            score=hit.get("score"),
        )

    @staticmethod
    def _product_card(product: dict, stock) -> ChatCard:
        return ChatCard(
            type="product",
            product_id=product.get("id"),
            name=product.get("name", ""),
            category_id=product.get("category_id"),
            brand=product.get("brand"),
            unit=product.get("unit"),
            base_price=product.get("base_price"),
            stock_quantity=stock,
            is_active=product.get("is_active", True),
        )

    @staticmethod
    def _lower_first(text: str) -> str:
        return text[:1].lower() + text[1:] if text else text

    @staticmethod
    def _answer(reply: str, suggestions: list, cards: list, context: dict) -> dict:
        return {"reply": reply, "suggestions": suggestions, "cards": cards, "context": context}
