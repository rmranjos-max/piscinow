from piscinow.config import Settings


def test_settings_default_llm_provider_is_fake():
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "fake"


def test_settings_reads_env_prefix(monkeypatch):
    monkeypatch.setenv("PISCINOW_LLM_PROVIDER", "anthropic")
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "anthropic"
