from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


class LLMProvider(ABC):
    """Provider-agnostic interface. Every adapter implements `stream`;
    `generate` is derived from it so adapters never duplicate accumulation logic."""

    @abstractmethod
    def stream(self, messages: list[ChatMessage], system: str) -> AsyncIterator[str]:
        """Yield response text chunks as they're generated."""
        raise NotImplementedError

    async def generate(self, messages: list[ChatMessage], system: str) -> str:
        chunks = []
        async for chunk in self.stream(messages, system):
            chunks.append(chunk)
        return "".join(chunks)
