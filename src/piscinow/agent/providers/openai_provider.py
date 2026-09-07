from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from piscinow.agent.llm_provider import ChatMessage, LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-5"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def stream(self, messages: list[ChatMessage], system: str) -> AsyncIterator[str]:
        openai_messages = [{"role": "system", "content": system}]
        openai_messages += [{"role": m.role, "content": m.content} for m in messages]
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,
            stream=True,
        )
        async for event in stream:
            delta = event.choices[0].delta.content
            if delta:
                yield delta
