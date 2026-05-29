from pydantic import BaseModel, ConfigDict


class Company(BaseModel):
    id: str
    name: str


class RequestedProduct(BaseModel):
    id: str
    name: str
    category_id: str
    brand: str
    unit: str
    pack_size: float
    base_price: float
    dietary_tags: list[str] = []


class ContractItem(BaseModel):
    product_id: str
    contract_price: float
    is_preferred: bool = False


class CandidateProduct(BaseModel):
    id: str
    name: str
    category_id: str
    brand: str
    unit: str
    pack_size: float
    base_price: float
    stock_quantity: int
    contract_price: float | None = None
    is_active: bool = True
    dietary_tags: list[str] = []


class ReplacementRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    company: Company
    requested_product: RequestedProduct
    requested_quantity: int
    contract_items: list[ContractItem] = []
    candidate_products: list[CandidateProduct] = []
    max_results: int = 3
    use_ai_explanation: bool = True


class ScoreBreakdown(BaseModel):
    category_similarity: int
    contract_match: int
    price_similarity: int
    stock_availability: int
    unit_pack_similarity: int


class Replacement(BaseModel):
    product_id: str
    name: str
    final_score: int
    confidence_pct: int
    confidence_label: str
    score_breakdown: ScoreBreakdown
    explanation: str


class RejectedCandidate(BaseModel):
    product_id: str
    name: str
    rejection_reason: str


class ReplacementResponse(BaseModel):
    replacements: list[Replacement] = []
    rejected_candidates: list[RejectedCandidate] = []
    no_candidates_reason: str | None = None
