"""Root conftest — ensures the project root is importable and shares fixtures."""

from __future__ import annotations

import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Deterministic, fully-offline settings (no Ollama dependency)."""
    return Settings(
        enable_embeddings=False,
        enable_llm_explanations=False,
        enable_milvus=False,
        allow_cross_category=True,
        category_semantic_threshold=0.6,
        max_price_increase_pct=0.25,
    )
