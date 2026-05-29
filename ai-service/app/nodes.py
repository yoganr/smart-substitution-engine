import asyncio
import logging

from langchain_ollama import ChatOllama

from .config import settings
from .schemas import (
    CandidateProduct,
    RejectedCandidate,
    Replacement,
    ScoreBreakdown,
)
from .scoring import compute_total_score, compute_confidence
from .state import RecommendationState

logger = logging.getLogger(__name__)

TEMPLATE_EXPLANATION = "{name}: compatible replacement based on category, contract, and price."


def validate_input(state: RecommendationState) -> RecommendationState:
    # Pydantic already validated the request at the FastAPI boundary.
    # Seed the candidates list from the request.
    return {
        "candidates": list(state["request"].candidate_products),
        "rejected": [],
        "scored": [],
        "replacements": [],
        "no_candidates_reason": None,
    }


def apply_hard_filters(state: RecommendationState) -> RecommendationState:
    req = state["request"]
    requested = req.requested_product
    # Normalize requested tags to lowercase for case-insensitive comparison
    requested_tags = {t.lower() for t in requested.dietary_tags}

    passing: list[CandidateProduct] = []
    rejected: list[RejectedCandidate] = list(state["rejected"])

    for c in state["candidates"]:
        reason = _hard_filter_reason(c, requested, requested_tags, req.requested_quantity)
        if reason:
            rejected.append(RejectedCandidate(product_id=c.id, name=c.name, rejection_reason=reason))
        else:
            passing.append(c)

    return {"candidates": passing, "rejected": rejected}


def _hard_filter_reason(
    c: CandidateProduct,
    requested,
    requested_tags: set[str],
    requested_quantity: int,
) -> str | None:
    if not c.is_active:
        return "product is inactive"
    if c.stock_quantity < requested_quantity:
        return f"insufficient stock ({c.stock_quantity} available, {requested_quantity} needed)"
    if c.category_id != requested.category_id:
        return f"category mismatch ({c.category_id} != {requested.category_id})"
    if c.id == requested.id:
        return "same product as requested"
    threshold = requested.base_price * (1 + settings.price_threshold_pct / 100)
    if requested.base_price > 0 and c.base_price > threshold:
        pct_over = round((c.base_price - requested.base_price) / requested.base_price * 100)
        return f"price {pct_over}% above original — exceeds {int(settings.price_threshold_pct)}% threshold"
    # Allergen filter: candidate must cover all requested dietary tags
    if requested_tags:
        candidate_tags = {t.lower() for t in c.dietary_tags}
        missing = requested_tags - candidate_tags
        if missing:
            return f"missing dietary tags: {', '.join(sorted(missing))}"
    return None


def score_candidates(state: RecommendationState) -> RecommendationState:
    req = state["request"]
    scored = []
    for c in state["candidates"]:
        score, breakdown = compute_total_score(
            c, req.requested_product, req.contract_items, req.requested_quantity
        )
        scored.append((c, score, breakdown))
    return {"scored": scored}


def rank_replacements(state: RecommendationState) -> RecommendationState:
    req = state["request"]
    max_results = req.max_results or settings.max_results_default

    sorted_scored = sorted(state["scored"], key=lambda x: x[1], reverse=True)
    top = sorted_scored[:max_results]

    replacements = []
    for c, score, breakdown in top:
        confidence_pct, confidence_label = compute_confidence(score)
        replacements.append(
            Replacement(
                product_id=c.id,
                name=c.name,
                final_score=score,
                confidence_pct=confidence_pct,
                confidence_label=confidence_label,
                score_breakdown=ScoreBreakdown(**breakdown),
                explanation=TEMPLATE_EXPLANATION.format(name=c.name),
            )
        )

    no_reason = None
    if not replacements and state["candidates"] == [] and state["scored"] == []:
        if state["rejected"]:
            no_reason = f"all {len(state['rejected'])} candidates were filtered out by hard filters"
        else:
            no_reason = "no candidate products were provided"

    return {"replacements": replacements, "no_candidates_reason": no_reason}


async def generate_ollama_explanations(state: RecommendationState) -> RecommendationState:
    if not state["replacements"]:
        return {}

    req = state["request"]
    if not req.use_ai_explanation:
        return {}

    llm = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        num_ctx=4096,
    )

    async def explain_one(replacement: Replacement) -> str:
        bd = replacement.score_breakdown
        original = req.requested_product.name
        price_diff = 0
        if req.requested_product.base_price > 0:
            # find the candidate to get base_price
            candidates_map = {c.id: c for c in req.candidate_products}
            cand = candidates_map.get(replacement.product_id)
            if cand:
                price_diff = round(
                    (cand.base_price - req.requested_product.base_price)
                    / req.requested_product.base_price
                    * 100
                )

        prompt = (
            f"You are a food service procurement assistant. Write ONE sentence explaining "
            f"why {replacement.name} is a {replacement.confidence_label} substitute for {original}.\n\n"
            f"Score context:\n"
            f"- Category match: {bd.category_similarity}/30\n"
            f"- Contract match: {bd.contract_match}/25\n"
            f"- Price similarity: {bd.price_similarity}/20 ({price_diff:+d}% price difference)\n"
            f"- Stock availability: {bd.stock_availability}/10\n"
            f"- Unit/pack match: {bd.unit_pack_similarity}/8\n"
            f"- Overall: {replacement.final_score}/93 ({replacement.confidence_pct}% confidence)\n\n"
            f"Rules: mention the strongest scoring dimension first, note any significant weakness, keep under 20 words."
        )
        try:
            result = await llm.ainvoke(prompt)
            text = result.content.strip()
            return text if text else TEMPLATE_EXPLANATION.format(name=replacement.name)
        except Exception as e:
            logger.warning("Ollama explanation failed for %s: %s", replacement.product_id, e)
            return TEMPLATE_EXPLANATION.format(name=replacement.name)

    # Run all explanation calls in parallel
    explanations = await asyncio.gather(
        *[explain_one(r) for r in state["replacements"]]
    )

    updated = [
        r.model_copy(update={"explanation": expl})
        for r, expl in zip(state["replacements"], explanations)
    ]
    return {"replacements": updated}


def return_result(state: RecommendationState) -> RecommendationState:
    # Terminal node — state is fully assembled, nothing to change.
    return {}
