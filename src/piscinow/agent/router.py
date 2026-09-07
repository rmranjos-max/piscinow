import json
import re
from dataclasses import dataclass

from piscinow.agent.llm_provider import ChatMessage, LLMProvider
from piscinow.models.member import ProfileType

CONFIDENCE_THRESHOLD = 0.6

_SYSTEM_PROMPT = """Voce e o classificador de perfil do Clube Piscinow.
Leia a mensagem do visitante e decida qual perfil ele tem: comprador, loja,
prestador ou embaixador. Responda APENAS com um JSON de uma linha no formato
{"profile": "<comprador|loja|prestador|embaixador>", "confidence": <0.0 a 1.0>}
sem nenhum texto adicional."""


@dataclass
class ClassificationResult:
    profile_type: ProfileType | None
    confidence: float


class Router:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def classify(self, message: str) -> ClassificationResult:
        raw = await self._llm.generate(
            [ChatMessage(role="user", content=message)],
            system=_SYSTEM_PROMPT,
        )
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> ClassificationResult:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return ClassificationResult(profile_type=None, confidence=0.0)
        try:
            data = json.loads(match.group(0))
            profile = ProfileType(data["profile"])
            confidence = float(data["confidence"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return ClassificationResult(profile_type=None, confidence=0.0)
        if confidence < CONFIDENCE_THRESHOLD:
            return ClassificationResult(profile_type=None, confidence=confidence)
        return ClassificationResult(profile_type=profile, confidence=confidence)
