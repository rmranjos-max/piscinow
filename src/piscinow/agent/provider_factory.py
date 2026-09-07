from piscinow.agent.llm_provider import LLMProvider
from piscinow.agent.providers.anthropic_provider import AnthropicProvider
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.agent.providers.openai_provider import OpenAIProvider
from piscinow.config import Settings


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("PISCINOW_ANTHROPIC_API_KEY is required for llm_provider=anthropic")
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("PISCINOW_OPENAI_API_KEY is required for llm_provider=openai")
        return OpenAIProvider(api_key=settings.openai_api_key)
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    raise ValueError(f"unknown llm_provider: {settings.llm_provider}")
