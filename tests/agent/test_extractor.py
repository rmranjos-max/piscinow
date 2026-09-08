import pytest

from piscinow.agent.extractor import Extractor
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.conversation import Conversation, Message, MessageRole
from piscinow.models.member import ProfileType


@pytest.mark.asyncio
async def test_extractor_writes_learning_when_llm_finds_one(db_session):
    provider = FakeLLMProvider(["Compradores de Valinhos costumam perguntar sobre prazo antes de fechar."])
    memory = MemoryStore(db_session)
    extractor = Extractor(provider, memory)

    conversation = Conversation(profile_type_detected=ProfileType.COMPRADOR)
    db_session.add(conversation)
    db_session.flush()
    db_session.add(Message(conversation=conversation, role=MessageRole.USER, content="quanto tempo demora?"))
    db_session.flush()

    await extractor.process(conversation)

    results = memory.search(query="prazo de obra em Valinhos", profile_type=ProfileType.COMPRADOR, limit=5)
    assert any("prazo" in r.content.lower() for r in results)


@pytest.mark.asyncio
async def test_extractor_writes_nothing_when_llm_says_nada(db_session):
    provider = FakeLLMProvider(["NADA"])
    memory = MemoryStore(db_session)
    extractor = Extractor(provider, memory)

    conversation = Conversation(profile_type_detected=ProfileType.COMPRADOR)
    db_session.add(conversation)
    db_session.flush()
    db_session.add(Message(conversation=conversation, role=MessageRole.USER, content="oi"))
    db_session.flush()

    await extractor.process(conversation)

    results = memory.search(query="oi", profile_type=ProfileType.COMPRADOR, limit=5)
    assert results == []


@pytest.mark.asyncio
async def test_extractor_does_nothing_for_empty_conversation(db_session):
    provider = FakeLLMProvider(["nao deveria ser chamado"])
    memory = MemoryStore(db_session)
    extractor = Extractor(provider, memory)

    conversation = Conversation()
    db_session.add(conversation)
    db_session.flush()

    await extractor.process(conversation)

    results = memory.search(query="nao deveria ser chamado", limit=5)
    assert results == []
