"""Application configuration.

All settings are sourced from environment variables (prefix ``SSE_``) or a local
``.env`` file, with sensible defaults so the service runs out of the box.

Scoring weights and business thresholds live here so the team can tune the
engine on Day 3 without touching code.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Service metadata ---
    service_name: str = "smart-substitution-engine"

    # --- Ollama (text generation only) ---
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "qwen3.5:0.8b"  # text generation (explanations) via Ollama
    ollama_timeout: float = 30.0

    # --- Embeddings (semantic similarity) ---
    # Backend: "sentence_transformers" (local, default) or "ollama".
    embedding_backend: str = "sentence_transformers"
    embedding_model: str = "BAAI/bge-m3"  # HF id for sentence-transformers; Ollama tag if backend=ollama
    embedding_device: Optional[str] = None  # None=auto (cuda if available), or "cpu"/"cuda"

    # --- Vector store (Milvus) ---
    enable_milvus: bool = True
    milvus_uri: str = "http://localhost:19530"
    milvus_token: str = ""  # "user:password" if auth is enabled
    milvus_collection: str = "product_embeddings"
    embedding_dim: int = 1024  # bge-m3 output dimension

    # --- Feature toggles ---
    enable_embeddings: bool = True
    enable_llm_explanations: bool = True

    # --- LLM generation ---
    llm_temperature: float = 0.2
    llm_num_predict: int = 180
    # Disable chain-of-thought for reasoning models (e.g. qwen3.5) so the small
    # model emits the answer directly instead of burning its token budget
    # "thinking" and returning empty content.
    llm_disable_reasoning: bool = True

    # --- Scoring weights (max points per dimension) ---
    w_category: float = Field(default=30.0, ge=0)
    w_contract: float = Field(default=25.0, ge=0)
    w_price: float = Field(default=20.0, ge=0)
    w_stock: float = Field(default=10.0, ge=0)
    w_unit_pack: float = Field(default=8.0, ge=0)

    # --- Business thresholds ---
    max_price_increase_pct: float = Field(default=0.25, ge=0)
    allow_cross_category: bool = True
    # Tuned for bge-m3: poultry vs chicken ~0.83 (accepted), vegetables vs
    # chicken ~0.63 (rejected). Raise/lower if you change the embedding model.
    category_semantic_threshold: float = Field(default=0.7, ge=0, le=1)
    default_max_results: int = Field(default=3, ge=1)
    # Allergen/dietary safety: a replacement must carry every dietary tag the
    # requested product has (e.g. can't substitute a gluten-free item with one
    # that isn't). No effect when the requested product has no tags.
    enforce_dietary_tags: bool = True

    @property
    def max_total_score(self) -> float:
        """Theoretical maximum achievable score (defaults to 93)."""
        return self.w_category + self.w_contract + self.w_price + self.w_stock + self.w_unit_pack


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
