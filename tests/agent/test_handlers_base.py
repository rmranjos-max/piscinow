import pytest

from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.agent.llm_provider import ChatMessage
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.member import ProfileType


class _DummyHandler(ConversationHandler):
    profile_type = ProfileType.COMPRADOR
    role_description = "visitante de teste"
    required_fields = [
        FieldSpec("name", "pergunte o nome"),
        FieldSpec("contact", "pergunte o contato"),
    ]


def _handler(db_session, provider=None):
    provider = provider or FakeLLMProvider()
    return _DummyHandler(provider, MemoryStore(db_session)), provider


def test_missing_fields_lists_all_when_nothing_collected(db_session):
    handler, _ = _handler(db_session)
    missing = handler.missing_fields({})
    assert {f.name for f in missing} == {"name", "contact"}


def test_missing_fields_shrinks_as_data_collected(db_session):
    handler, _ = _handler(db_session)
    missing = handler.missing_fields({"name": "Marina"})
    assert {f.name for f in missing} == {"contact"}


@pytest.mark.asyncio
async def test_extract_fields_parses_llm_json(db_session):
    provider = FakeLLMProvider(['{"name": "Marina Duarte", "contact": "(19) 99999-0000"}'])
    handler, _ = _handler(db_session, provider)

    updated = await handler.extract_fields(
        [ChatMessage(role="user", content="sou a Marina Duarte, (19) 99999-0000")],
        collected={},
    )

    assert updated["name"] == "Marina Duarte"
    assert updated["contact"] == "(19) 99999-0000"


@pytest.mark.asyncio
async def test_extract_fields_keeps_previously_collected_values_when_llm_returns_null(db_session):
    provider = FakeLLMProvider(['{"name": null, "contact": "(19) 99999-0000"}'])
    handler, _ = _handler(db_session, provider)

    updated = await handler.extract_fields(
        [ChatMessage(role="user", content="(19) 99999-0000")],
        collected={"name": "Marina Duarte"},
    )

    assert updated["name"] == "Marina Duarte"
    assert updated["contact"] == "(19) 99999-0000"


@pytest.mark.asyncio
async def test_reply_system_prompt_names_missing_fields(db_session):
    handler, provider = _handler(db_session)
    captured = {}

    async def fake_generate(history, system):
        captured["system"] = system
        return "ok"

    provider.generate = fake_generate

    await handler.reply([ChatMessage(role="user", content="oi")], collected={"name": "Marina"})

    assert "contato" in captured["system"]
