from piscinow.agent.json_extraction import parse_json_object
from piscinow.agent.llm_provider import ChatMessage, LLMProvider

_SYSTEM_PROMPT = """Voce ajuda um comprador do Clube Piscinow a encontrar
produtos e servicos a partir de uma descricao em texto livre. Extraia os
filtros em JSON: {"kind": "piscina", "equipamento", "instalacao",
"manutencao" ou "reparo", "category": string, "region": string}.
Use null para campos que nao aparecem no texto. Responda APENAS com o JSON."""


async def extract_search_filters(llm: LLMProvider, text: str) -> dict:
    raw = await llm.generate([ChatMessage(role="user", content=text)], system=_SYSTEM_PROMPT)
    data = parse_json_object(raw)

    def _as_str(value) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value) if value is not None else ""

    return {
        "kind": _as_str(data.get("kind")),
        "category": _as_str(data.get("category")),
        "region": _as_str(data.get("region")),
    }
