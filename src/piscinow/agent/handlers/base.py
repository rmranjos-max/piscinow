from dataclasses import dataclass

from piscinow.agent.json_extraction import parse_json_object
from piscinow.agent.llm_provider import ChatMessage, LLMProvider
from piscinow.agent.memory_store import MemoryStore
from piscinow.models.member import ProfileType


@dataclass
class FieldSpec:
    name: str
    ask_hint: str  # instrucao em portugues do que perguntar/extrair


class ConversationHandler:
    profile_type: ProfileType
    required_fields: list[FieldSpec] = []
    role_description: str = ""

    def __init__(self, llm: LLMProvider, memory: MemoryStore):
        self.llm = llm
        self.memory = memory

    def missing_fields(self, collected: dict) -> list[FieldSpec]:
        return [f for f in self.required_fields if not collected.get(f.name)]

    def _build_system_prompt(self, collected: dict, memory_items: list) -> str:
        missing = self.missing_fields(collected)
        missing_text = (
            "; ".join(f.ask_hint for f in missing)
            if missing
            else "todos os dados necessarios ja foram coletados"
        )
        memory_text = "\n".join(f"- {m.content}" for m in memory_items) or "nenhum aprendizado relevante ainda"
        return (
            f"Voce e o concierge do Clube Piscinow, falando com um(a) {self.role_description}.\n"
            f"Responda sempre em portugues, de forma direta e cordial.\n"
            f"Dados ainda faltando: {missing_text}.\n"
            f"Aprendizados relevantes:\n{memory_text}"
        )

    async def reply(self, history: list[ChatMessage], collected: dict) -> str:
        last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
        memory_items = self.memory.search(query=last_user, profile_type=self.profile_type, limit=5)
        system = self._build_system_prompt(collected, memory_items)
        return await self.llm.generate(history, system=system)

    async def extract_fields(self, history: list[ChatMessage], collected: dict) -> dict:
        field_names = [f.name for f in self.required_fields]
        instruction = (
            "Extraia do historico da conversa os seguintes campos, em JSON: "
            f"{field_names}. Use null para campos ainda nao informados. "
            "Responda APENAS com o JSON."
        )
        raw = await self.llm.generate(history, system=instruction)
        extracted = self._parse_json(raw)
        updated = dict(collected)
        for name in field_names:
            value = extracted.get(name)
            if value:
                updated[name] = value
        return updated

    @staticmethod
    def _parse_json(raw: str) -> dict:
        return parse_json_object(raw)
