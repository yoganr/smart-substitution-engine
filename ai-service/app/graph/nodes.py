"""LangGraph node implementations.

Nodes are bound to their dependencies (settings + service objects) via the
``RecommendationNodes`` container so the graph itself stays free of globals and
is easy to test with fakes.
"""

from __future__ import annotations

from app.config import Settings
from app.graph.state import GraphState
from app.logging_config import get_logger
from app.schemas import (
    RejectedCandidateInfo,
    Replacement,
    ReplacementResponse,
)
from app.services.explanation import ExplanationService
from app.services.filters import apply_hard_filters
from app.services.scoring import (
    ScoredCandidate,
    build_contract_lookup,
    confidence,
    effective_price,
    rank_candidates,
    score_candidate,
)
from app.services.similarity import SimilarityService

logger = get_logger(__name__)


class RecommendationNodes:
    def __init__(
        self,
        settings: Settings,
        similarity: SimilarityService,
        explainer: ExplanationService,
    ) -> None:
        self.settings = settings
        self.similarity = similarity
        self.explainer = explainer

    # -- 1. validate_input ------------------------------------------------
    async def validate_input(self, state: GraphState) -> dict:
        request = state["request"]
        warnings: list[str] = []

        contract_lookup = build_contract_lookup(request.contract_items)
        requested_contract = contract_lookup.get(request.requested_product.id)
        requested_effective_price = effective_price(
            request.requested_product.base_price,
            requested_contract.contract_price if requested_contract else None,
        )

        if not request.candidate_products:
            warnings.append("No candidate products were supplied.")

        logger.info(
            "validate_input: company=%s product=%s qty=%s candidates=%d",
            request.company.id,
            request.requested_product.id,
            request.requested_quantity,
            len(request.candidate_products),
        )
        return {
            "contract_lookup": contract_lookup,
            "requested_effective_price": requested_effective_price,
            "warnings": warnings,
        }

    # -- 2. apply_hard_filters -------------------------------------------
    async def apply_hard_filters(self, state: GraphState) -> dict:
        request = state["request"]
        # Similarities are needed both for category compatibility and scoring.
        category_similarities = await self.similarity.category_similarities(
            request.requested_product, request.candidate_products
        )
        accepted, rejected = apply_hard_filters(
            request.requested_product,
            request.candidate_products,
            requested_quantity=request.requested_quantity,
            requested_effective_price=state["requested_effective_price"],
            category_similarities=category_similarities,
            contract_lookup=state["contract_lookup"],
            settings=self.settings,
        )
        logger.info(
            "apply_hard_filters: accepted=%d rejected=%d (embeddings=%s)",
            len(accepted),
            len(rejected),
            self.similarity.uses_embeddings,
        )
        return {
            "category_similarities": category_similarities,
            "accepted": accepted,
            "rejected": rejected,
        }

    # -- 3. score_candidates ---------------------------------------------
    def score_candidates(self, state: GraphState) -> dict:
        request = state["request"]
        sims = state["category_similarities"]
        scored: list[ScoredCandidate] = [
            score_candidate(
                request.requested_product,
                cand,
                category_similarity=sims.get(cand.id, 0.0),
                requested_effective_price=state["requested_effective_price"],
                contract_lookup=state["contract_lookup"],
                requested_quantity=request.requested_quantity,
                settings=self.settings,
            )
            for cand in state["accepted"]
        ]
        logger.info("score_candidates: scored=%d", len(scored))
        return {"scored": scored}

    # -- 4. rank_replacements --------------------------------------------
    def rank_replacements(self, state: GraphState) -> dict:
        request = state["request"]
        ranked = rank_candidates(state["scored"], request.max_results)
        logger.info(
            "rank_replacements: top=%d scores=%s",
            len(ranked),
            [s.final_score for s in ranked],
        )
        return {"ranked": ranked}

    # -- 5. generate_ollama_explanations ---------------------------------
    async def generate_explanations(self, state: GraphState) -> dict:
        request = state["request"]
        ranked = await self.explainer.annotate(
            request.requested_product,
            state.get("ranked", []),
            use_ai=request.use_ai_explanation,
        )
        sources = {s.explanation_source for s in ranked}
        logger.info("generate_explanations: count=%d sources=%s", len(ranked), sources or "-")
        return {"ranked": ranked}

    # -- 6. return_result -------------------------------------------------
    def return_result(self, state: GraphState) -> dict:
        request = state["request"]
        ranked = state.get("ranked", [])
        rejected = state.get("rejected", [])

        replacements = [self._to_replacement(s) for s in ranked]
        rejected_info = [
            RejectedCandidateInfo(
                product_id=r.id,
                name=r.name,
                rejection_reason="; ".join(r.reasons),
            )
            for r in rejected
        ]
        no_candidates_reason = self._no_candidates_reason(request, replacements, rejected)

        response = ReplacementResponse(
            replacements=replacements,
            rejected_candidates=rejected_info,
            no_candidates_reason=no_candidates_reason,
            requested_product_id=request.requested_product.id,
            replacement_needed=True,
            candidates_evaluated=len(request.candidate_products),
            candidates_rejected=len(rejected),
            warnings=state.get("warnings", []),
        )
        return {"response": response}

    @staticmethod
    def _no_candidates_reason(request, replacements, rejected) -> str | None:
        if replacements:
            return None
        if not request.candidate_products:
            return "No candidate products were supplied."
        if rejected:
            return f"All {len(rejected)} candidate(s) were filtered out as incompatible."
        return "No suitable replacement was found."

    # -- helpers ----------------------------------------------------------
    def _to_replacement(self, scored: ScoredCandidate) -> Replacement:
        cand = scored.candidate
        contract_price = cand.contract_price
        if contract_price is None:
            contract_price = (
                scored.facts.candidate_effective_price
                if scored.facts.is_under_contract
                else None
            )
        pct, label = confidence(scored.final_score, self.settings.max_total_score)
        return Replacement(
            product_id=cand.id,
            name=cand.name,
            final_score=scored.final_score,
            confidence_pct=pct,
            confidence_label=label,
            score_breakdown=scored.breakdown,
            explanation=scored.explanation,
            brand=cand.brand,
            unit=cand.unit,
            pack_size=cand.pack_size,
            base_price=cand.base_price,
            contract_price=contract_price,
            effective_price=scored.facts.candidate_effective_price,
            stock_quantity=cand.stock_quantity,
            is_under_contract=scored.facts.is_under_contract,
            is_preferred=scored.facts.is_preferred,
            explanation_source=scored.explanation_source,
        )


# --- Conditional routing ----------------------------------------------------
def has_accepted_candidates(state: GraphState) -> str:
    """Skip scoring/ranking/explanation when nothing survived the filters."""
    return "score" if state.get("accepted") else "empty"
