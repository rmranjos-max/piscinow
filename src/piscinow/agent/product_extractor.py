from piscinow.agent.json_extraction import parse_json_object
from piscinow.agent.llm_provider import ChatMessage, LLMProvider

_SYSTEM_PROMPT = """Voce ajuda uma loja a cadastrar um produto no Clube Piscinow
a partir de uma descricao em texto livre. Extraia os campos em JSON:
{"kind": "piscina" ou "equipamento", "category": string, "name": string,
"price": numero, "size_label": string ou null, "description": string ou null}.
Use null para campos que nao aparecem no texto. Responda APENAS com o JSON."""


async def extract_product_fields(llm: LLMProvider, text: str) -> dict:
    raw = await llm.generate([ChatMessage(role="user", content=text)], system=_SYSTEM_PROMPT)
    data = parse_json_object(raw)
    return {
        "kind": data.get("kind") or "",
        "category": data.get("category") or "",
        "name": data.get("name") or "",
        "price": str(data.get("price")) if data.get("price") is not None else "",
        "size_label": data.get("size_label") or "",
        "description": data.get("description") or "",
    }
