from unittest.mock import MagicMock

import pytest

from piscinow.agent.llm_provider import ChatMessage
from piscinow.agent.providers.anthropic_provider import AnthropicProvider


class _FakeStreamCtx:
    def __init__(self, chunks):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _agen(self):
        for c in self._chunks:
            yield c

    @property
    def text_stream(self):
        return self._agen()


@pytest.mark.asyncio
async def test_anthropic_provider_streams_text():
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(return_value=_FakeStreamCtx(["Ola", " mundo"]))

    provider = AnthropicProvider(api_key="test-key")
    provider._client = fake_client

    chunks = [
        c async for c in provider.stream([ChatMessage(role="user", content="oi")], system="seja gentil")
    ]

    assert "".join(chunks) == "Ola mundo"
    fake_client.messages.stream.assert_called_once()
    _, kwargs = fake_client.messages.stream.call_args
    assert kwargs["system"] == "seja gentil"
    assert kwargs["messages"] == [{"role": "user", "content": "oi"}]
