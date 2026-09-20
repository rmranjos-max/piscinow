import pytest

from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.agent.service_extractor import extract_service_fields


@pytest.mark.asyncio
async def test_extracts_service_fields_from_llm_json():
    provider = FakeLLMProvider(
        [
            '{"kind": "instalacao", "category": "piscina de fibra", "name": "Instalacao completa", '
            '"price_min": 3000, "price_max": 8000, "description": null}'
        ]
    )

    result = await extract_service_fields(provider, "instalacao de piscina de fibra, de 3 a 8 mil")

    assert result["kind"] == "instalacao"
    assert result["category"] == "piscina de fibra"
    assert result["name"] == "Instalacao completa"
    assert result["price_min"] == "3000"
    assert result["price_max"] == "8000"
    assert result["description"] == ""


@pytest.mark.asyncio
async def test_extract_service_fields_returns_blank_fields_on_malformed_response():
    provider = FakeLLMProvider(["desculpe nao entendi"])

    result = await extract_service_fields(provider, "algo confuso")

    assert result == {"kind": "", "category": "", "name": "", "price_min": "", "price_max": "", "description": ""}
