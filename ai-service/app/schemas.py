"""Pydantic v2 schemas defining the shared API contract with the .NET backend.

Request/response shapes mirror the contract documented in HACKATHON.md. Response
objects carry a few additive diagnostic fields (e.g. ``effective_price``,
``is_under_contract``) that the .NET side may ignore safely.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Request models (.NET -> Python)
# ---------------------------------------------------------------------------
class Company(BaseModel):
    id: str = Field(..., examples=["company_001"])
    name: str = Field(..., examples=["ABC Restaurant"])


class RequestedProduct(BaseModel):
    id: str = Field(..., examples=["product_001"])
    name: str = Field(..., examples=["Chicken Breast 2kg"])
    category_id: str = Field(..., examples=["cat_chicken"])
    brand: Optional[str] = Field(default=None, examples=["Brand A"])
    unit: Optional[str] = Field(default=None, examples=["kg"])
    pack_size: Optional[float] = Field(default=None, ge=0, examples=[2])
    base_price: float = Field(..., ge=0, examples=[10.0])
    dietary_tags: list[str] = Field(default_factory=list, examples=[["halal", "gluten_free"]])


class ContractItem(BaseModel):
    product_id: str = Field(..., examples=["product_001"])
    contract_price: Optional[float] = Field(default=None, ge=0, examples=[9.2])
    is_preferred: bool = Field(default=False)


class CandidateProduct(BaseModel):
    id: str = Field(..., examples=["product_2033"])
    name: str = Field(..., examples=["Chicken Breast Premium 2kg"])
    category_id: str = Field(..., examples=["cat_chicken"])
    brand: Optional[str] = Field(default=None, examples=["Brand B"])
    unit: Optional[str] = Field(default=None, examples=["kg"])
    pack_size: Optional[float] = Field(default=None, ge=0, examples=[2])
    base_price: float = Field(..., ge=0, examples=[10.5])
    stock_quantity: float = Field(default=0, ge=0, examples=[150])
    contract_price: Optional[float] = Field(default=None, ge=0, examples=[9.5])
    is_active: bool = Field(default=True)
    dietary_tags: list[str] = Field(default_factory=list, examples=[["halal", "gluten_free"]])


class ReplacementRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company": {"id": "company_001", "name": "ABC Restaurant"},
                "requested_product": {
                    "id": "product_001",
                    "name": "Chicken Breast 2kg",
                    "category_id": "cat_chicken",
                    "brand": "Brand A",
                    "unit": "kg",
                    "pack_size": 2,
                    "base_price": 10.0,
                },
                "requested_quantity": 20,
                "contract_items": [
                    {"product_id": "product_001", "contract_price": 9.2, "is_preferred": True},
                    {"product_id": "product_2033", "contract_price": 9.5, "is_preferred": False},
                ],
                "candidate_products": [
                    {
                        "id": "product_2033",
                        "name": "Chicken Breast Premium 2kg",
                        "category_id": "cat_chicken",
                        "brand": "Brand B",
                        "unit": "kg",
                        "pack_size": 2,
                        "base_price": 10.5,
                        "stock_quantity": 150,
                        "contract_price": 9.5,
                    },
                    {
                        "id": "product_2099",
                        "name": "Organic Chicken Breast 2kg",
                        "category_id": "cat_chicken",
                        "brand": "Brand C",
                        "unit": "kg",
                        "pack_size": 2,
                        "base_price": 11.0,
                        "stock_quantity": 40,
                    },
                ],
                "max_results": 3,
                "use_ai_explanation": True,
            }
        }
    )

    company: Company
    requested_product: RequestedProduct
    requested_quantity: float = Field(..., gt=0, examples=[20])
    contract_items: list[ContractItem] = Field(default_factory=list)
    candidate_products: list[CandidateProduct] = Field(default_factory=list)
    max_results: int = Field(default=3, ge=1, le=50, examples=[3])
    use_ai_explanation: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Response models (Python -> .NET)
# ---------------------------------------------------------------------------
class ScoreBreakdown(BaseModel):
    category_similarity: int = Field(..., examples=[30])
    contract_match: int = Field(..., examples=[25])
    price_similarity: int = Field(..., examples=[20])
    stock_availability: int = Field(..., examples=[10])
    unit_pack_similarity: int = Field(..., examples=[8])


class Replacement(BaseModel):
    product_id: str
    name: str
    final_score: int = Field(..., description="Sum of score_breakdown (0-93)")
    confidence_pct: int = Field(..., ge=0, le=100, description="final_score as a percentage of the max")
    confidence_label: str = Field(..., examples=["Strong"], description="Human label for confidence_pct")
    score_breakdown: ScoreBreakdown
    explanation: str

    # --- Additive diagnostics (safe for .NET to ignore) ---
    brand: Optional[str] = None
    unit: Optional[str] = None
    pack_size: Optional[float] = None
    base_price: Optional[float] = None
    contract_price: Optional[float] = None
    effective_price: Optional[float] = None
    stock_quantity: Optional[float] = None
    is_under_contract: bool = False
    is_preferred: bool = False
    explanation_source: str = Field(default="template", description="'ollama' or 'template'")


class RejectedCandidateInfo(BaseModel):
    """A candidate that did not pass the hard filters (matches the .NET DTO)."""

    product_id: str
    name: str
    rejection_reason: str


class ReplacementResponse(BaseModel):
    replacements: list[Replacement] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidateInfo] = Field(default_factory=list)
    no_candidates_reason: Optional[str] = Field(
        default=None,
        description="Set when there are no replacements (else null).",
    )

    # --- Additive diagnostics (safe for .NET to ignore) ---
    requested_product_id: Optional[str] = None
    replacement_needed: bool = True
    candidates_evaluated: int = 0
    candidates_rejected: int = 0
    warnings: list[str] = Field(default_factory=list)


class RejectedCandidate(BaseModel):
    """Internal representation carrying the full list of rejection reasons."""

    id: str
    name: str
    reasons: list[str]


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str
    ollama: dict
    embeddings: dict
