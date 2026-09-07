import pytest

from piscinow.agent.provider_factory import build_llm_provider
from piscinow.agent.providers.anthropic_provider import AnthropicProvider
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.agent.providers.openai_provider import OpenAIProvider
from piscinow.config import Settings


def test_builds_fake_provider_by_default():
    settings = Settings(_env_file=None, llm_provider="fake")
    assert isinstance(build_llm_provider(settings), FakeLLMProvider)


def test_builds_anthropic_provider_when_configured():
    settings = Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key="test-key")
    assert isinstance(build_llm_provider(settings), AnthropicProvider)


def test_builds_openai_provider_when_configured():
    settings = Settings(_env_file=None, llm_provider="openai", openai_api_key="test-key")
    assert isinstance(build_llm_provider(settings), OpenAIProvider)


def test_raises_when_anthropic_key_missing():
    settings = Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key=None)
    with pytest.raises(ValueError):
        build_llm_provider(settings)


def test_raises_for_unknown_provider():
    settings = Settings(_env_file=None, llm_provider="unknown")
    with pytest.raises(ValueError):
        build_llm_provider(settings)
