from piscinow.agent.memory_store import MemoryStore
from piscinow.models.member import ProfileType
from piscinow.models.memory import MemoryKind, MemorySource


def test_write_and_search_returns_relevant_item(db_session):
    store = MemoryStore(db_session)
    store.write(
        content="Piscinas de alvenaria em Valinhos costumam levar 45 dias de obra.",
        kind=MemoryKind.FACT,
        source=MemorySource.AUTO,
    )
    store.write(
        content="A loja atende das 9h as 18h de segunda a sexta.",
        kind=MemoryKind.FAQ,
        source=MemorySource.AUTO,
    )

    results = store.search(query="quanto tempo demora construir piscina de alvenaria", limit=1)

    assert len(results) == 1
    assert "45 dias" in results[0].content


def test_human_sourced_memory_ranks_above_auto_for_similar_relevance(db_session):
    store = MemoryStore(db_session)
    store.write(
        content="Prazo medio de obra de piscina de alvenaria e 45 dias.",
        kind=MemoryKind.FACT,
        source=MemorySource.AUTO,
    )
    store.write(
        content="Prazo medio de obra de piscina de alvenaria e 45 dias, corrigido pela equipe.",
        kind=MemoryKind.CORRECTION,
        source=MemorySource.HUMAN,
        created_by="admin@piscinow.com.br",
    )

    results = store.search(query="quanto tempo demora a obra de uma piscina de alvenaria", limit=2)

    assert results[0].source == MemorySource.HUMAN


def test_search_filters_by_profile_type(db_session):
    store = MemoryStore(db_session)
    store.write(
        content="Lojas devem informar CNPJ no pre-cadastro.",
        kind=MemoryKind.RULE,
        source=MemorySource.AUTO,
        profile_type=ProfileType.LOJA,
    )
    store.write(
        content="Compradores devem informar a regiao da obra.",
        kind=MemoryKind.RULE,
        source=MemorySource.AUTO,
        profile_type=ProfileType.COMPRADOR,
    )

    results = store.search(query="quais dados preciso informar", profile_type=ProfileType.LOJA, limit=5)

    assert all(r.profile_type in (ProfileType.LOJA, None) for r in results)
    assert any("CNPJ" in r.content for r in results)


def test_search_ignores_superseded_items(db_session):
    store = MemoryStore(db_session)
    old = store.write(content="Prazo de obra e 30 dias.", kind=MemoryKind.FACT, source=MemorySource.AUTO)
    old.superseded_by = store.write(
        content="Prazo de obra e 45 dias (atualizado).", kind=MemoryKind.CORRECTION, source=MemorySource.HUMAN
    ).id

    results = store.search(query="qual o prazo de obra", limit=5)

    assert all("30 dias" not in r.content for r in results)
