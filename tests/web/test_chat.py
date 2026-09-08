from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.conversation import Conversation
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.memory import MemoryItem
from piscinow.web.deps import get_llm_provider


def test_send_message_creates_conversation_and_sets_session_cookie(client):
    provider = FakeLLMProvider(['{"profile": "comprador", "confidence": 0.9}'])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/api/chat/message", data={"message": "quero uma piscina"})

    assert response.status_code == 200
    assert response.cookies.get("piscinow_session") is not None


def test_second_message_reuses_same_conversation(client, db_session):
    provider = FakeLLMProvider()
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    provider.queue_response('{"profile": "comprador", "confidence": 0.9}')
    first = client.post("/api/chat/message", data={"message": "quero uma piscina"})
    session_cookie = first.cookies.get("piscinow_session")

    provider.queue_response('{"name": null, "contact": null, "region": null, "intent": null}')
    client.cookies.set("piscinow_session", session_cookie)
    client.post("/api/chat/message", data={"message": "ainda nao sei os detalhes"})

    conversations = db_session.query(Conversation).all()
    assert len(conversations) == 1
    assert len(conversations[0].messages) == 4  # 2 user + 2 agent


def test_referred_visitor_gets_auto_approved_member(client, db_session):
    referrer = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo", referral_code="RM7X2K9A")
    db_session.add(referrer)
    db_session.flush()

    provider = FakeLLMProvider()
    client.app.dependency_overrides[get_llm_provider] = lambda: provider
    client.cookies.set("piscinow_ref", "RM7X2K9A")

    provider.queue_response('{"profile": "comprador", "confidence": 0.9}')
    first = client.post("/api/chat/message", data={"message": "quero uma piscina"})
    client.cookies.set("piscinow_session", first.cookies.get("piscinow_session"))

    provider.queue_response(
        '{"name": "Joao Silva", "contact": "19988887777", "region": "Campinas", "intent": "vinil"}'
    )
    client.post("/api/chat/message", data={"message": "Joao Silva, 19988887777, Campinas, vinil"})

    member = db_session.query(Member).filter(Member.name == "Joao Silva").one()
    assert member.status == MemberStatus.APPROVED


def test_finalized_conversation_schedules_extractor(client, db_session):
    provider = FakeLLMProvider()
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    provider.queue_response('{"profile": "embaixador", "confidence": 0.9}')
    first = client.post("/api/chat/message", data={"message": "quero ser embaixador"})
    client.cookies.set("piscinow_session", first.cookies.get("piscinow_session"))

    provider.queue_response('{"name": "Ana Paula", "contact": "19977776666"}')
    # Consumed by the Extractor's background call after finalization:
    provider.queue_response("Visitantes que querem ser embaixador costumam ja ter indicacoes em mente.")
    client.post("/api/chat/message", data={"message": "Ana Paula, 19977776666"})

    from piscinow.agent.memory_store import MemoryStore
    from piscinow.models.member import ProfileType as PT

    memory = MemoryStore(db_session)
    results = memory.search(query="embaixador com indicacoes em mente", profile_type=PT.EMBAIXADOR, limit=5)
    assert any("indicacoes" in r.content for r in results)


def test_extractor_not_rescheduled_after_conversation_already_finalized(client, db_session):
    provider = FakeLLMProvider()
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    provider.queue_response('{"profile": "comprador", "confidence": 0.9}')
    first = client.post("/api/chat/message", data={"message": "quero uma piscina"})
    client.cookies.set("piscinow_session", first.cookies.get("piscinow_session"))

    provider.queue_response(
        '{"name": "Marina Duarte", "contact": "(19) 99999-0000", "region": "Valinhos", "intent": "alvenaria 6x3"}'
    )
    client.post(
        "/api/chat/message",
        data={"message": "Marina Duarte, (19) 99999-0000, em Valinhos, alvenaria 6x3"},
    )

    third = client.post("/api/chat/message", data={"message": "obrigado"})

    assert third.status_code == 200
    assert (
        "Sua conversa ja foi concluida; nossa equipe segue o atendimento a partir daqui."
        in third.text
    )
    # Extractor must have run exactly once (on the finalizing turn) and must
    # NOT have been rescheduled on this third, already-finalized message.
    assert db_session.query(MemoryItem).count() == 1
