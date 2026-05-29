import pytest
from app.schemas import (
    CandidateProduct,
    Company,
    ContractItem,
    ReplacementRequest,
    RequestedProduct,
)


@pytest.fixture
def requested_product() -> RequestedProduct:
    return RequestedProduct(
        id="product_001",
        name="Chicken Breast 2kg",
        category_id="cat_chicken",
        brand="Brand A",
        unit="kg",
        pack_size=2.0,
        base_price=10.0,
        dietary_tags=["halal"],
    )


@pytest.fixture
def contract_items() -> list[ContractItem]:
    return [
        ContractItem(product_id="product_001", contract_price=9.2, is_preferred=True),
        ContractItem(product_id="product_2033", contract_price=9.5, is_preferred=False),
    ]


@pytest.fixture
def base_candidate(requested_product) -> CandidateProduct:
    """A candidate that passes all hard filters and scores well."""
    return CandidateProduct(
        id="product_2033",
        name="Chicken Breast Premium 2kg",
        category_id="cat_chicken",
        brand="Brand B",
        unit="kg",
        pack_size=2.0,
        base_price=10.5,
        stock_quantity=150,
        contract_price=9.5,
        is_active=True,
        dietary_tags=["halal", "gluten-free"],
    )


@pytest.fixture
def sample_request(requested_product, contract_items, base_candidate) -> ReplacementRequest:
    return ReplacementRequest(
        company=Company(id="company_001", name="Marco's Italian Kitchen"),
        requested_product=requested_product,
        requested_quantity=20,
        contract_items=contract_items,
        candidate_products=[base_candidate],
        max_results=3,
        use_ai_explanation=False,
    )
