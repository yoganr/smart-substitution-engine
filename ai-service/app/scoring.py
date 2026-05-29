from .schemas import CandidateProduct, ContractItem, RequestedProduct


def score_category(candidate: CandidateProduct, requested: RequestedProduct) -> int:
    return 30 if candidate.category_id == requested.category_id else 0


def score_contract(
    candidate: CandidateProduct, contract_items: list[ContractItem]
) -> int:
    contract_ids = {item.product_id for item in contract_items}
    return 25 if candidate.id in contract_ids else 0


def score_price(candidate: CandidateProduct, requested: RequestedProduct) -> int:
    # Guard: if base_price is 0, return neutral score
    if requested.base_price == 0:
        return 20
    diff_pct = (
        (candidate.base_price - requested.base_price) / requested.base_price * 100
    )
    if diff_pct <= 0:
        return 20
    # Each 1% increase above 0% deducts 2 points; 0 at +10%
    pts = 20 - int(diff_pct * 2)
    return max(0, pts)


def score_stock(candidate: CandidateProduct, requested_quantity: int) -> int:
    if candidate.stock_quantity >= requested_quantity * 2:
        return 10
    if candidate.stock_quantity >= requested_quantity:
        return 5
    return 0


def score_unit_pack(candidate: CandidateProduct, requested: RequestedProduct) -> int:
    same_unit = candidate.unit == requested.unit
    same_pack = candidate.pack_size == requested.pack_size
    if same_unit and same_pack:
        return 8
    if same_unit:
        return 4
    return 0


def compute_total_score(
    candidate: CandidateProduct,
    requested: RequestedProduct,
    contract_items: list[ContractItem],
    requested_quantity: int,
) -> tuple[int, dict]:
    breakdown = {
        "category_similarity": score_category(candidate, requested),
        "contract_match": score_contract(candidate, contract_items),
        "price_similarity": score_price(candidate, requested),
        "stock_availability": score_stock(candidate, requested_quantity),
        "unit_pack_similarity": score_unit_pack(candidate, requested),
    }
    total = sum(breakdown.values())
    return total, breakdown


def compute_confidence(score: int) -> tuple[int, str]:
    pct = round((score / 93) * 100)
    if pct >= 86:
        label = "Excellent"
    elif pct >= 65:
        label = "Good"
    elif pct >= 40:
        label = "Acceptable"
    else:
        label = "Poor"
    return pct, label
