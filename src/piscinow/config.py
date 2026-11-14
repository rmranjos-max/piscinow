from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PISCINOW_")

    environment: Literal["development", "production"] = "development"
    allow_payment_simulation: bool = False
    session_max_age_seconds: int = 7 * 24 * 3600
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: str = "postgresql+psycopg://piscinow:piscinow@localhost:5432/piscinow"
    llm_provider: str = "fake"  # "anthropic" | "openai" | "fake"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    session_secret: str = "change-me-in-production"
    chat_rate_limit_per_minute: int = 20
    public_base_url: str = "http://localhost:8000"

    # Catalog photos. "local" keeps files on disk (development); "s3" is any S3-compatible bucket.
    media_storage: Literal["local", "s3"] = "local"
    media_local_dir: str = "var/media"
    media_public_base_url: str | None = None
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "auto"


def get_settings() -> Settings:
    return Settings()
