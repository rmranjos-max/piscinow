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
    return {
        "kind": data.get("kind") or "",
        "category": data.get("category") or "",
        "region": data.get("region") or "",
    }
