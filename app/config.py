"""Application configuration.

All settings are sourced from environment variables (prefix ``SSE_``) or a local
``.env`` file, with sensible defaults so the service runs out of the box.

Scoring weights and business thresholds live here so the team can tune the
engine on Day 3 without touching code.
"""

from __future__ import annotations

from functools import lru_cache

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

    # --- Ollama connection ---
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "llama3.2"
    embedding_model: str = "qwen3-embedding:0.6b"
    ollama_timeout: float = 30.0

    # --- Feature toggles ---
    enable_embeddings: bool = True
    enable_llm_explanations: bool = True

    # --- LLM generation ---
    llm_temperature: float = 0.2
    llm_num_predict: int = 180

    # --- Scoring weights (max points per dimension) ---
    w_category: float = Field(default=30.0, ge=0)
    w_contract: float = Field(default=25.0, ge=0)
    w_price: float = Field(default=20.0, ge=0)
    w_stock: float = Field(default=10.0, ge=0)
    w_unit_pack: float = Field(default=8.0, ge=0)

    # --- Business thresholds ---
    max_price_increase_pct: float = Field(default=0.25, ge=0)
    allow_cross_category: bool = True
    category_semantic_threshold: float = Field(default=0.6, ge=0, le=1)
    default_max_results: int = Field(default=3, ge=1)

    @property
    def max_total_score(self) -> float:
        """Theoretical maximum achievable score (defaults to 93)."""
        return self.w_category + self.w_contract + self.w_price + self.w_stock + self.w_unit_pack


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
