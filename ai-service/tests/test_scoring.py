import pytest
from app.scoring import (
    compute_confidence,
    compute_total_score,
    score_category,
    score_contract,
    score_price,
    score_stock,
    score_unit_pack,
)


# --- score_category ---

def test_category_exact_match(base_candidate, requested_product):
    assert score_category(base_candidate, requested_product) == 30


def test_category_no_match(base_candidate, requested_product):
    different = base_candidate.model_copy(update={"category_id": "cat_beef"})
    assert score_category(different, requested_product) == 0


# --- score_contract ---

def test_contract_in_items(base_candidate, contract_items):
    # base_candidate.id == "product_2033" which is in contract_items
    assert score_contract(base_candidate, contract_items) == 25


def test_contract_not_in_items(base_candidate, contract_items):
    unknown = base_candidate.model_copy(update={"id": "product_unknown"})
    assert score_contract(unknown, contract_items) == 0


# --- score_price ---

def test_price_zero_diff(base_candidate, requested_product):
    same_price = base_candidate.model_copy(update={"base_price": 10.0})
    assert score_price(same_price, requested_product) == 20


def test_price_ten_pct_diff(base_candidate, requested_product):
    # +10% => 10.0 * 1.10 = 11.0 => score = 20 - 10*2 = 0
    at_ten = base_candidate.model_copy(update={"base_price": 11.0})
    assert score_price(at_ten, requested_product) == 0


def test_price_cheaper(base_candidate, requested_product):
    cheaper = base_candidate.model_copy(update={"base_price": 9.0})
    assert score_price(cheaper, requested_product) == 20


def test_price_over_ten_pct(base_candidate, requested_product):
    over = base_candidate.model_copy(update={"base_price": 12.0})
    assert score_price(over, requested_product) == 0


def test_price_base_price_zero_guard(base_candidate, requested_product):
    zero_price = requested_product.model_copy(update={"base_price": 0.0})
    assert score_price(base_candidate, zero_price) == 20


def test_price_partial_diff(base_candidate, requested_product):
    # +5% => 20 - 5*2 = 10
    five_pct = base_candidate.model_copy(update={"base_price": 10.5})
    assert score_price(five_pct, requested_product) == 10


# --- score_stock ---

def test_stock_double_quantity(base_candidate):
    # stock 150 >= 20*2=40 → 10
    assert score_stock(base_candidate, 20) == 10


def test_stock_exact_quantity(base_candidate):
    # stock exactly equal to requested → 5
    exact = base_candidate.model_copy(update={"stock_quantity": 20})
    assert score_stock(exact, 20) == 5


def test_stock_below_quantity(base_candidate):
    # stock 10 < requested 20 → filtered before scoring, but score should be 0 if called
    low = base_candidate.model_copy(update={"stock_quantity": 10})
    assert score_stock(low, 20) == 0


# --- score_unit_pack ---

def test_unit_pack_both_match(base_candidate, requested_product):
    assert score_unit_pack(base_candidate, requested_product) == 8


def test_unit_only_match(base_candidate, requested_product):
    diff_pack = base_candidate.model_copy(update={"pack_size": 5.0})
    assert score_unit_pack(diff_pack, requested_product) == 4


def test_unit_pack_neither(base_candidate, requested_product):
    diff_both = base_candidate.model_copy(update={"unit": "g", "pack_size": 500.0})
    assert score_unit_pack(diff_both, requested_product) == 0


# --- compute_confidence ---

def test_confidence_excellent():
    pct, label = compute_confidence(85)  # 85/93*100 = 91% → Excellent
    assert label == "Excellent"
    assert pct >= 86


def test_confidence_good():
    pct, label = compute_confidence(62)  # 62/93*100 = 67% → Good
    assert label == "Good"
    assert 65 <= pct <= 85


def test_confidence_acceptable():
    pct, label = compute_confidence(46)  # 46/93*100 = 49% → Acceptable
    assert label == "Acceptable"
    assert 40 <= pct <= 64


def test_confidence_poor():
    pct, label = compute_confidence(30)  # 30/93*100 = 32% → Poor
    assert label == "Poor"
    assert pct < 40


def test_confidence_pct_formula():
    # round(88/93*100) = round(94.6) = 95
    pct, _ = compute_confidence(88)
    assert pct == 95


# --- compute_total_score ---

def test_total_score_full_match(base_candidate, requested_product, contract_items):
    # same category, contracted, exact price, double stock, same unit+pack
    same_price = base_candidate.model_copy(update={"base_price": 10.0, "stock_quantity": 150})
    score, breakdown = compute_total_score(same_price, requested_product, contract_items, 20)
    assert breakdown["category_similarity"] == 30
    assert breakdown["contract_match"] == 25
    assert breakdown["price_similarity"] == 20
    assert breakdown["stock_availability"] == 10
    assert breakdown["unit_pack_similarity"] == 8
    assert score == 93
