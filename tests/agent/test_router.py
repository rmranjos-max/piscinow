import pytest

from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.agent.router import Router
from piscinow.models.member import ProfileType


@pytest.mark.asyncio
async def test_classifies_comprador_with_high_confidence():
    provider = FakeLLMProvider(['{"profile": "comprador", "confidence": 0.92}'])
    router = Router(provider)

    result = await router.classify("quero fazer uma piscina de alvenaria")

    assert result.profile_type == ProfileType.COMPRADOR
    assert result.confidence == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_low_confidence_returns_none_profile():
    provider = FakeLLMProvider(['{"profile": "loja", "confidence": 0.3}'])
    router = Router(provider)

    result = await router.classify("oi")

    assert result.profile_type is None


@pytest.mark.asyncio
async def test_malformed_response_returns_none_profile():
    provider = FakeLLMProvider(["desculpe nao entendi"])
    router = Router(provider)

    result = await router.classify("oi")

    assert result.profile_type is None


@pytest.mark.asyncio
async def test_unknown_profile_value_returns_none_profile():
    provider = FakeLLMProvider(['{"profile": "turista", "confidence": 0.9}'])
    router = Router(provider)

    result = await router.classify("oi")

    assert result.profile_type is None
