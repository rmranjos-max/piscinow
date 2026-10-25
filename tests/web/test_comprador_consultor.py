import json

from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import (
    ConsentState,
    FieldSource,
    LeadQualification,
    QualificationStatus,
)
from piscinow.qualification.service import find_qualification, get_or_create_qualification, set_field


def _comprador_logged_in(client, db_session, *, name="Marina Duarte", email="comprador@example.com"):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name=name, status=MemberStatus.APPROVED, email=email)
    comprador.set_password("senha-forte-123")
    db_session.add(comprador)
    db_session.flush()
    client.post("/comprador/login", data={"email": email, "password": "senha-forte-123"})
    return comprador


def _extraction(campos=None) -> str:
    return json.dumps({"campos": campos or {}, "duvida_para_equipe": None}, ensure_ascii=False)


def _fill_required(db_session, comprador):
    qualification = get_or_create_qualification(db_session, comprador)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="teste")
    return qualification


def test_the_consultor_requires_a_comprador_login(client):
    response = client.get("/comprador/consultor", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"


def test_opening_the_consultor_starts_the_conversation_with_a_virtual_assistant_greeting(client, db_session):
    comprador = _comprador_logged_in(client, db_session)

    response = client.get("/comprador/consultor")

    assert response.status_code == 200
    assert "assistente virtual" in response.text
    assert "Seu briefing" in response.text
    assert find_qualification(db_session, comprador) is not None


def test_opening_the_consultor_twice_keeps_a_single_conversation(client, db_session):
    comprador = _comprador_logged_in(client, db_session)

    client.get("/comprador/consultor")
    client.get("/comprador/consultor")

    assert db_session.query(LeadQualification).filter_by(member_id=comprador.id).count() == 1


def test_a_message_is_answered_and_the_briefing_panel_shows_what_was_understood(client, db_session):
    _comprador_logged_in(client, db_session)
    client.app.state.llm_provider = FakeLLMProvider([
        _extraction({"localizacao": "Valinhos", "tipo_piscina": "fibra"}),
        "Perfeito, fibra em Valinhos! Para quando você imagina a obra?",
    ])

    response = client.post(
        "/comprador/consultor/mensagem", data={"message": "Fibra, em Valinhos"}, follow_redirects=True
    )

    assert response.status_code == 200
    assert "Perfeito, fibra em Valinhos!" in response.text
    assert "Fibra, em Valinhos" in response.text
    assert "Valinhos" in response.text
    assert "Você informou" in response.text


def test_an_empty_message_is_ignored_without_calling_the_model(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    client.app.state.llm_provider = FakeLLMProvider([])

    response = client.post("/comprador/consultor/mensagem", data={"message": "   "}, follow_redirects=False)

    assert response.status_code == 303
    assert find_qualification(db_session, comprador) is None


def test_when_the_model_is_down_the_page_still_works_and_says_so(client, db_session):
    class Down(FakeLLMProvider):
        async def stream(self, messages, system):
            raise RuntimeError("down")
            yield ""  # pragma: no cover

    _comprador_logged_in(client, db_session)
    client.app.state.llm_provider = Down()

    response = client.post(
        "/comprador/consultor/mensagem", data={"message": "Fibra em Valinhos"}, follow_redirects=True
    )

    assert response.status_code == 200
    assert "indisponível" in response.text
    assert "Fibra em Valinhos" in response.text


def test_the_buyer_can_correct_a_field_and_it_stays_marked_as_theirs(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    _fill_required(db_session, comprador)

    response = client.post(
        "/comprador/consultor/campo", data={"key": "prazo", "value": "sem_prazo"}, follow_redirects=False
    )

    assert response.status_code == 303
    qualification = find_qualification(db_session, comprador)
    assert qualification.values()["prazo"] == "sem_prazo"


def test_an_unknown_field_or_an_invalid_value_is_rejected(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    _fill_required(db_session, comprador)

    assert client.post("/comprador/consultor/campo", data={"key": "cpf", "value": "123"}).status_code == 404
    assert client.post("/comprador/consultor/campo", data={"key": "prazo", "value": "ontem"}).status_code == 400
    assert find_qualification(db_session, comprador).values()["prazo"] == "ate_90_dias"


def test_consent_cannot_be_given_before_the_essential_data_exists(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    client.get("/comprador/consultor")

    response = client.post("/comprador/consultor/consentimento", data={"decisao": "autorizo"})

    assert response.status_code == 400
    assert find_qualification(db_session, comprador).consent == ConsentState.NAO_RESPONDIDO


def test_authorizing_marks_the_qualification_as_qualified(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    _fill_required(db_session, comprador)

    response = client.post(
        "/comprador/consultor/consentimento", data={"decisao": "autorizo"}, follow_redirects=False
    )

    assert response.status_code == 303
    qualification = find_qualification(db_session, comprador)
    assert qualification.consent == ConsentState.CONCEDIDO
    assert qualification.consent_at is not None
    assert qualification.status == QualificationStatus.QUALIFICADA


def test_preferring_to_talk_first_keeps_it_unqualified_and_can_be_changed_later(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    _fill_required(db_session, comprador)

    client.post("/comprador/consultor/consentimento", data={"decisao": "depois"})
    qualification = find_qualification(db_session, comprador)
    assert qualification.consent == ConsentState.RECUSADO
    assert qualification.status == QualificationStatus.EM_ANDAMENTO

    page = client.get("/comprador/consultor")
    assert "Autorizo compartilhar meu briefing, sem nome e sem contato, com lojas compatíveis" in page.text

    client.post("/comprador/consultor/consentimento", data={"decisao": "autorizo"})
    assert find_qualification(db_session, comprador).status == QualificationStatus.QUALIFICADA


def test_an_unknown_consent_decision_is_rejected(client, db_session):
    _comprador_logged_in(client, db_session)

    assert client.post("/comprador/consultor/consentimento", data={"decisao": "talvez"}).status_code == 400


def test_one_buyer_never_sees_another_buyers_briefing(client, db_session):
    first = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED, email="a@example.com")
    db_session.add(first)
    db_session.flush()
    _fill_required(db_session, first)

    _comprador_logged_in(client, db_session, name="Carlos Pereira", email="b@example.com")
    response = client.get("/comprador/consultor")

    assert "Valinhos" not in response.text
    assert "Marina" not in response.text


def test_the_consultor_is_in_the_menu_and_marked_active(client, db_session):
    _comprador_logged_in(client, db_session)

    response = client.get("/comprador/consultor")

    assert 'href="/comprador/consultor" aria-current="page"' in response.text


def test_the_buyer_can_withdraw_the_authorization_and_the_opportunity_stops(client, db_session):
    from piscinow.qualification.deals import active_deal

    comprador = _comprador_logged_in(client, db_session)
    _fill_required(db_session, comprador)
    client.post("/comprador/consultor/consentimento", data={"decisao": "autorizo"})
    assert active_deal(db_session, comprador.id) is not None
    assert "Retirar a autorização" in client.get("/comprador/consultor").text

    client.post("/comprador/consultor/consentimento", data={"decisao": "depois"})

    assert find_qualification(db_session, comprador).consent == ConsentState.RECUSADO
    assert active_deal(db_session, comprador.id) is None
