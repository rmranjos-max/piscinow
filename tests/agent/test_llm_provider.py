import pytest

from piscinow.agent.llm_provider import ChatMessage
from piscinow.agent.providers.fake_provider import FakeLLMProvider


@pytest.mark.asyncio
async def test_fake_provider_streams_scripted_response():
    provider = FakeLLMProvider(["Ola tudo bem"])
    chunks = [c async for c in provider.stream([ChatMessage(role="user", content="oi")], system="")]
    assert "".join(chunks).strip() == "Ola tudo bem"


@pytest.mark.asyncio
async def test_generate_accumulates_stream():
    provider = FakeLLMProvider(["resposta completa"])
    result = await provider.generate([ChatMessage(role="user", content="oi")], system="")
    assert result.strip() == "resposta completa"


@pytest.mark.asyncio
async def test_fake_provider_echoes_when_queue_empty():
    provider = FakeLLMProvider()
    result = await provider.generate([ChatMessage(role="user", content="teste")], system="")
    assert "teste" in result


@pytest.mark.asyncio
async def test_queue_response_appends_to_existing_queue():
    provider = FakeLLMProvider(["primeira"])
    provider.queue_response("segunda")
    first = await provider.generate([ChatMessage(role="user", content="a")], system="")
    second = await provider.generate([ChatMessage(role="user", content="b")], system="")
    assert first.strip() == "primeira"
    assert second.strip() == "segunda"
