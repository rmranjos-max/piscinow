from piscinow.agent.llm_provider import ChatMessage, LLMProvider
from piscinow.agent.memory_store import MemoryStore
from piscinow.models.conversation import Conversation
from piscinow.models.memory import MemoryKind, MemorySource

_SYSTEM_PROMPT = """Analise a conversa entre o concierge do Clube Piscinow e um
visitante. Se houver algum fato, objecao ou padrao reaproveitavel para
conversas futuras do mesmo perfil, escreva UMA frase curta e autocontida
resumindo esse aprendizado. Se nao houver nada relevante, responda apenas
com a palavra NADA."""


class Extractor:
    def __init__(self, llm: LLMProvider, memory: MemoryStore):
        self._llm = llm
        self._memory = memory

    async def process(self, conversation: Conversation) -> None:
        history = [
            ChatMessage(role="user" if m.role.value == "user" else "assistant", content=m.content)
            for m in conversation.messages
        ]
        if not history:
            return
        learning = (await self._llm.generate(history, system=_SYSTEM_PROMPT)).strip()
        if not learning or learning.upper() == "NADA":
            return
        self._memory.write(
            content=learning,
            kind=MemoryKind.FACT,
            source=MemorySource.AUTO,
            profile_type=conversation.profile_type_detected,
            confidence=0.4,
        )
