from unittest.mock import AsyncMock, MagicMock

import pytest

from piscinow.agent.llm_provider import ChatMessage
from piscinow.agent.providers.openai_provider import OpenAIProvider


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeEvent:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


async def _fake_stream(chunks):
    for c in chunks:
        yield _FakeEvent(c)


@pytest.mark.asyncio
async def test_openai_provider_streams_text():
    provider = OpenAIProvider(api_key="test-key")
    provider._client = MagicMock()
    provider._client.chat.completions.create = AsyncMock(return_value=_fake_stream(["Ola", " mundo"]))

    chunks = [
        c async for c in provider.stream([ChatMessage(role="user", content="oi")], system="seja gentil")
    ]

    assert "".join(chunks) == "Ola mundo"
    _, kwargs = provider._client.chat.completions.create.call_args
    assert kwargs["messages"][0] == {"role": "system", "content": "seja gentil"}
    assert kwargs["stream"] is True
