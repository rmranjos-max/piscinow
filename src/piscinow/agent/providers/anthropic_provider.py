from collections.abc import AsyncIterator

import anthropic

from piscinow.agent.llm_provider import ChatMessage, LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def stream(self, messages: list[ChatMessage], system: str) -> AsyncIterator[str]:
        anthropic_messages = [{"role": m.role, "content": m.content} for m in messages]
        async with self._client.messages.stream(
            model=self._model,
            system=system,
            messages=anthropic_messages,
            max_tokens=1024,
        ) as stream:
            async for text in stream.text_stream:
                yield text
