import pytest

from piscinow.agent.project_search import extract_search_filters
from piscinow.agent.providers.fake_provider import FakeLLMProvider


@pytest.mark.asyncio
async def test_extracts_search_filters_from_llm_json():
    provider = FakeLLMProvider(['{"kind": "piscina", "category": "fibra", "region": "Valinhos"}'])

    result = await extract_search_filters(provider, "piscina de fibra em Valinhos")

    assert result["kind"] == "piscina"
    assert result["category"] == "fibra"
    assert result["region"] == "Valinhos"


@pytest.mark.asyncio
async def test_extract_search_filters_returns_blank_fields_on_malformed_response():
    provider = FakeLLMProvider(["desculpe nao entendi"])

    result = await extract_search_filters(provider, "algo confuso")

    assert result == {"kind": "", "category": "", "region": ""}
