import pytest

from piscinow.agent.product_extractor import extract_product_fields
from piscinow.agent.providers.fake_provider import FakeLLMProvider


@pytest.mark.asyncio
async def test_extracts_product_fields_from_llm_json():
    provider = FakeLLMProvider(
        [
            '{"kind": "piscina", "category": "fibra", "name": "Piscina Fibra 6x3", '
            '"price": 18000, "size_label": "6x3m", "description": null}'
        ]
    )

    result = await extract_product_fields(provider, "piscina de fibra 6x3, R$18 mil")

    assert result["kind"] == "piscina"
    assert result["category"] == "fibra"
    assert result["name"] == "Piscina Fibra 6x3"
    assert result["price"] == "18000"
    assert result["size_label"] == "6x3m"
    assert result["description"] == ""


@pytest.mark.asyncio
async def test_extract_product_fields_returns_blank_fields_on_malformed_response():
    provider = FakeLLMProvider(["desculpe nao entendi"])

    result = await extract_product_fields(provider, "algo confuso")

    assert result == {"kind": "", "category": "", "name": "", "price": "", "size_label": "", "description": ""}
