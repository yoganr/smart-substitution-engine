from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    price_threshold_pct: float = 20.0
    max_results_default: int = 3
    ollama_model: str = "llama3.2:3b"
    ollama_base_url: str = "http://localhost:11434"


settings = Settings()
