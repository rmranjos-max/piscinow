from collections.abc import AsyncIterator

from piscinow.agent.llm_provider import ChatMessage, LLMProvider


class FakeLLMProvider(LLMProvider):
    """Deterministic provider for tests: returns a scripted response queue,
    or echoes the last user message if the queue is empty."""

    def __init__(self, scripted_responses: list[str] | None = None):
        self._queue: list[str] = list(scripted_responses or [])

    def queue_response(self, text: str) -> None:
        self._queue.append(text)

    async def stream(self, messages: list[ChatMessage], system: str) -> AsyncIterator[str]:
        if self._queue:
            text = self._queue.pop(0)
        else:
            last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
            text = f"[fake reply to: {last_user}]"
        for chunk in text.split(" "):
            yield chunk + " "
