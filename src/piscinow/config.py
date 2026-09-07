from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PISCINOW_")

    database_url: str = "postgresql+psycopg://piscinow:piscinow@localhost:5432/piscinow"
    llm_provider: str = "fake"  # "anthropic" | "openai" | "fake"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    session_secret: str = "change-me-in-production"
    chat_rate_limit_per_minute: int = 20


def get_settings() -> Settings:
    return Settings()
