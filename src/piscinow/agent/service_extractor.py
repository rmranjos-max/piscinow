from piscinow.agent.json_extraction import parse_json_object
from piscinow.agent.llm_provider import ChatMessage, LLMProvider

_SYSTEM_PROMPT = """Voce ajuda um prestador de servico a cadastrar um servico
no Clube Piscinow a partir de uma descricao em texto livre. Extraia os campos
em JSON: {"kind": "instalacao", "manutencao" ou "reparo", "category": string,
"name": string, "price_min": numero ou null, "price_max": numero ou null,
"description": string ou null}.
Use null para campos que nao aparecem no texto. Responda APENAS com o JSON."""


async def extract_service_fields(llm: LLMProvider, text: str) -> dict:
    raw = await llm.generate([ChatMessage(role="user", content=text)], system=_SYSTEM_PROMPT)
    data = parse_json_object(raw)
    return {
        "kind": data.get("kind") or "",
        "category": data.get("category") or "",
        "name": data.get("name") or "",
        "price_min": str(data.get("price_min")) if data.get("price_min") is not None else "",
        "price_max": str(data.get("price_max")) if data.get("price_max") is not None else "",
        "description": data.get("description") or "",
    }
