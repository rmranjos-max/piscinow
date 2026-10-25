from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PISCINOW_")

    environment: Literal["development", "production"] = "development"
    allow_payment_simulation: bool = False
    session_max_age_seconds: int = 7 * 24 * 3600

    database_url: str = "postgresql+psycopg://piscinow:piscinow@localhost:5432/piscinow"
    llm_provider: str = "fake"  # "anthropic" | "openai" | "fake"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    session_secret: str = "change-me-in-production"
    chat_rate_limit_per_minute: int = 20
    public_base_url: str = "http://localhost:8000"


def get_settings() -> Settings:
    return Settings()
