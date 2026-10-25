from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import ConsentState, DealStatus, FieldSource
from piscinow.qualification.deals import active_deal
from piscinow.qualification.service import get_or_create_qualification, request_attention, set_consent, set_field


def _admin_logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def _buyer(db_session, name="Marina Duarte", email="marina@example.com", phone="(19) 99999-0000"):
    member = Member(
        profile_type=ProfileType.COMPRADOR, name=name, status=MemberStatus.APPROVED, email=email, phone=phone,
        region="Campinas",
    )
    db_session.add(member)
    db_session.flush()
    return member


def _qualified_buyer(db_session, **kwargs):
    member = _buyer(db_session, **kwargs)
    qualification = get_or_create_qualification(db_session, member)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)
    return member, qualification


def test_the_list_requires_an_admin_login(client):
    response = client.get("/admin/oportunidades", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_the_list_shows_active_opportunities_with_code_buyer_and_briefing_summary(client, db_session):
    _admin_logged_in(client, db_session)
    _qualified_buyer(db_session)

    response = client.get("/admin/oportunidades")

    assert response.status_code == 200
    assert "OP-" in response.text
    assert "Marina Duarte" in response.text
    assert "Fibra" in response.text and "Valinhos" in response.text
    assert "Qualificada" in response.text


def test_the_list_filters_by_state_and_hides_lost_ones_by_default(client, db_session):
    _admin_logged_in(client, db_session)
    active_member, _ = _qualified_buyer(db_session, name="Ativa Souza", email="a@example.com")
    lost_member, lost_q = _qualified_buyer(db_session, name="Perdida Lima", email="b@example.com")
    client.post(f"/admin/oportunidades/{lost_q.id}/perdida", data={"motivo": "Desistiu"})

    default = client.get("/admin/oportunidades")
    lost_only = client.get("/admin/oportunidades?estado=lost")
    everything = client.get("/admin/oportunidades?estado=todas")

    assert "Ativa Souza" in default.text and "Perdida Lima" not in default.text
    assert "Perdida Lima" in lost_only.text and "Ativa Souza" not in lost_only.text
    assert "Ativa Souza" in everything.text and "Perdida Lima" in everything.text


def test_an_unknown_filter_falls_back_to_the_active_ones(client, db_session):
    _admin_logged_in(client, db_session)
    _qualified_buyer(db_session)

    assert "Marina Duarte" in client.get("/admin/oportunidades?estado=qualquer").text


def test_a_buyer_waiting_for_help_without_an_opportunity_is_listed_apart(client, db_session):
    _admin_logged_in(client, db_session)
    member = _buyer(db_session, name="Carlos Pereira", email="c@example.com")
    qualification = get_or_create_qualification(db_session, member)
    request_attention(qualification, "Sem resposta após 3 perguntas: Localização")

    response = client.get("/admin/oportunidades")

    assert "Aguardando ajuda da equipe" in response.text
    assert "Carlos Pereira" in response.text
    assert "Sem resposta após 3 perguntas" in response.text


def test_the_detail_shows_the_full_contact_briefing_history_and_transcript_to_the_team(client, db_session):
    _admin_logged_in(client, db_session)
    _, qualification = _qualified_buyer(db_session)

    response = client.get(f"/admin/oportunidades/{qualification.id}")

    assert response.status_code == 200
    assert "marina@example.com" in response.text
    assert "(19) 99999-0000" in response.text
    assert "Oportunidade criada" in response.text
    assert "assistente virtual" in response.text
    assert "Compartilhamento autorizado" in response.text


def test_the_detail_of_an_unknown_or_malformed_id_is_a_404(client, db_session):
    _admin_logged_in(client, db_session)

    assert client.get("/admin/oportunidades/nao-e-um-uuid").status_code == 404
    assert client.get("/admin/oportunidades/00000000-0000-0000-0000-000000000000").status_code == 404


def test_marking_lost_requires_a_reason_and_keeps_the_page_with_an_error(client, db_session):
    _admin_logged_in(client, db_session)
    member, qualification = _qualified_buyer(db_session)

    response = client.post(f"/admin/oportunidades/{qualification.id}/perdida", data={"motivo": "  "})

    assert response.status_code == 400
    assert "motivo da perda é obrigatório" in response.text
    assert active_deal(db_session, member.id).status == DealStatus.QUALIFIED


def test_marking_lost_records_the_reason_and_who_did_it(client, db_session):
    _admin_logged_in(client, db_session)
    member, qualification = _qualified_buyer(db_session)

    response = client.post(
        f"/admin/oportunidades/{qualification.id}/perdida",
        data={"motivo": "Sem retorno após três contatos"}, follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Perdida" in response.text
    assert "Sem retorno após três contatos" in response.text
    assert "admin:equipe@piscinow.com.br" in response.text
    assert active_deal(db_session, member.id) is None


def test_the_team_can_fill_a_missing_field_on_behalf_of_the_buyer_and_it_is_marked_as_theirs(client, db_session):
    _admin_logged_in(client, db_session)
    member = _buyer(db_session)
    qualification = get_or_create_qualification(db_session, member)

    response = client.post(
        f"/admin/oportunidades/{qualification.id}/campo",
        data={"key": "localizacao", "value": "Valinhos"}, follow_redirects=False,
    )

    assert response.status_code == 303
    [field] = qualification.fields
    assert field.source == FieldSource.ADMIN
    assert field.updated_by == "admin:equipe@piscinow.com.br"
    assert client.post(
        f"/admin/oportunidades/{qualification.id}/campo", data={"key": "prazo", "value": "ontem"}
    ).status_code == 400


def test_resolving_the_attention_request_clears_it(client, db_session):
    _admin_logged_in(client, db_session)
    member = _buyer(db_session)
    qualification = get_or_create_qualification(db_session, member)
    request_attention(qualification, "Dúvida do comprador: prazo de entrega")

    client.post(f"/admin/oportunidades/{qualification.id}/atencao/resolver")

    assert qualification.attention_at is None
    assert qualification.attention_note is None


def test_the_buyer_giving_consent_in_the_page_opens_the_opportunity_the_admin_then_sees(client, db_session):
    member = _buyer(db_session, email="comprador@example.com")
    member.set_password("senha-forte-123")
    qualification = get_or_create_qualification(db_session, member)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    client.post("/comprador/login", data={"email": "comprador@example.com", "password": "senha-forte-123"})

    client.post("/comprador/consultor/consentimento", data={"decisao": "autorizo"})

    assert qualification.consent == ConsentState.CONCEDIDO
    assert active_deal(db_session, member.id) is not None


def test_the_admin_menu_has_the_opportunities_item_and_it_is_active(client, db_session):
    _admin_logged_in(client, db_session)

    response = client.get("/admin/oportunidades")

    assert 'href="/admin/oportunidades" aria-current="page"' in response.text
