"""Unit tests for the explanation layer (template + Ollama path with fakes)."""

from __future__ import annotations

from app.services.explanation import ExplanationService, template_explanation
from app.services.scoring import build_contract_lookup, score_candidate
from app.schemas import ContractItem
from tests.factories import make_candidate, make_requested


def _score(settings, **cand_kw):
    req = make_requested()
    cand = make_candidate(**cand_kw)
    contract = build_contract_lookup(
        [ContractItem(product_id=cand.id, contract_price=cand.contract_price, is_preferred=True)]
        if cand.contract_price is not None
        else []
    )
    return req, score_candidate(
        req,
        cand,
        category_similarity=1.0,
        requested_effective_price=10.0,
        contract_lookup=contract,
        requested_quantity=20,
        settings=settings,
    )


def test_template_mentions_name_and_score(settings):
    req, scored = _score(settings, contract_price=9.0)
    text = template_explanation(req, scored)
    assert scored.candidate.name in text
    assert str(scored.final_score) in text


async def test_no_llm_uses_template(settings):
    req, scored = _score(settings)
    svc = ExplanationService(chat=None)
    out = await svc.annotate(req, [scored], use_ai=True)
    assert out[0].explanation_source == "template"
    assert out[0].explanation


class _FakeChat:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    async def acomplete(self, system, user):
        self.calls += 1
        return self.reply


async def test_llm_path_sets_ollama_source(settings):
    req, scored = _score(settings)
    chat = _FakeChat("This is a great substitute with stock on hand.")
    svc = ExplanationService(chat=chat)
    out = await svc.annotate(req, [scored], use_ai=True)
    assert out[0].explanation_source == "ollama"
    assert out[0].explanation == "This is a great substitute with stock on hand."
    assert chat.calls == 1


async def test_llm_think_tags_are_stripped(settings):
    req, scored = _score(settings)
    chat = _FakeChat("<think>reasoning here</think>Clean answer.")
    svc = ExplanationService(chat=chat)
    out = await svc.annotate(req, [scored], use_ai=True)
    assert out[0].explanation == "Clean answer."


async def test_use_ai_false_skips_llm(settings):
    req, scored = _score(settings)
    chat = _FakeChat("should not be called")
    svc = ExplanationService(chat=chat)
    out = await svc.annotate(req, [scored], use_ai=False)
    assert chat.calls == 0
    assert out[0].explanation_source == "template"


class _BrokenChat:
    async def acomplete(self, system, user):
        raise RuntimeError("ollama down")


async def test_llm_failure_falls_back_to_template(settings):
    req, scored = _score(settings)
    svc = ExplanationService(chat=_BrokenChat())
    out = await svc.annotate(req, [scored], use_ai=True)
    assert out[0].explanation_source == "template"
    assert out[0].explanation
