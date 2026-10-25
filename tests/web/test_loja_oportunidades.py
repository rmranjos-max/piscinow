from piscinow.matching.service import run_matching, save_profile, set_override, share_with_partners
from piscinow.models.matching import MatchingDecision, MatchOverride, PartnerResponse
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import DealEvent, DealStatus, FieldSource
from piscinow.qualification.deals import active_deal, mark_lost
from piscinow.qualification.service import get_or_create_qualification, set_consent, set_field

BUYER_EMAIL = "marina.contato@example.com"
BUYER_PHONE = "(19) 99999-0000"


def _loja(db_session, name="Studio Fibra Sul", email="loja@example.com", areas="Valinhos"):
    loja = Member(profile_type=ProfileType.LOJA, name=name, status=MemberStatus.APPROVED, email=email)
    loja.set_password("senha-forte-123")
    db_session.add(loja)
    db_session.flush()
    save_profile(db_session, loja, areas=areas, pool_types=["fibra"], budget_bands=[], capacity=3, active=True, actor="t")
    return loja


def _login(client, email="loja@example.com"):
    client.post("/loja/login", data={"email": email, "password": "senha-forte-123"})


def _shared_deal(db_session, *, name="Marina Duarte"):
    buyer = Member(
        profile_type=ProfileType.COMPRADOR, name=name, status=MemberStatus.APPROVED,
        email=BUYER_EMAIL, phone=BUYER_PHONE, region="Campinas",
    )
    db_session.add(buyer)
    db_session.flush()
    qualification = get_or_create_qualification(db_session, buyer)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias", "dimensoes": "7 x 3 m"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)
    deal = active_deal(db_session, buyer.id)
    run_matching(db_session, deal, actor="admin:x")
    return buyer, qualification, deal


def _decision(db_session, deal, loja):
    return db_session.query(MatchingDecision).filter_by(deal_id=deal.id, partner_member_id=loja.id).one()


def test_the_inbox_requires_a_loja_login(client):
    response = client.get("/loja/oportunidades", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/loja/login"


def test_an_empty_inbox_says_so(client, db_session):
    _loja(db_session)
    _login(client)

    response = client.get("/loja/oportunidades")

    assert response.status_code == 200
    assert "Nenhuma oportunidade" in response.text


def test_a_store_does_not_see_an_opportunity_that_was_not_shared_yet(client, db_session):
    loja = _loja(db_session)
    _shared_deal(db_session)
    _login(client)

    assert "Cliente #" not in client.get("/loja/oportunidades").text


def test_a_shared_opportunity_shows_the_anonymous_briefing_and_never_the_contact(client, db_session):
    loja = _loja(db_session)
    buyer, _, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    _login(client)

    response = client.get("/loja/oportunidades")

    assert "Cliente #" in response.text
    assert "Valinhos" in response.text and "Fibra" in response.text and "7 x 3 m" in response.text
    for secret in ("Marina", "Duarte", BUYER_EMAIL, BUYER_PHONE, "Campinas", str(buyer.id)):
        assert secret not in response.text


def test_a_store_never_sees_an_opportunity_shared_only_with_another_store(client, db_session):
    mine = _loja(db_session, "Minha Loja", "minha@example.com", areas="Sorocaba")
    other = _loja(db_session, "Outra Loja", "outra@example.com", areas="Valinhos")
    _, _, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    _login(client, "minha@example.com")

    response = client.get("/loja/oportunidades")

    assert "Cliente #" not in response.text
    assert "Outra Loja" not in response.text


def test_an_excluded_store_does_not_receive_it_even_if_the_system_found_it_eligible(client, db_session):
    loja = _loja(db_session)
    _, _, deal = _shared_deal(db_session)
    set_override(db_session, _decision(db_session, deal, loja), MatchOverride.EXCLUIDA, reason="Sem estoque", actor="admin:x")
    other = _loja(db_session, "Outra Loja", "outra@example.com")
    run_matching(db_session, deal, actor="admin:x")
    share_with_partners(db_session, deal, actor="admin:x")
    _login(client)

    assert "Cliente #" not in client.get("/loja/oportunidades").text


def test_withdrawing_the_buyers_authorization_removes_it_from_the_inbox(client, db_session):
    loja = _loja(db_session)
    buyer, qualification, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    _login(client)
    assert "Cliente #" in client.get("/loja/oportunidades").text

    set_consent(db_session, qualification, False)

    assert "Cliente #" not in client.get("/loja/oportunidades").text


def test_a_lost_opportunity_leaves_the_inbox(client, db_session):
    loja = _loja(db_session)
    _, _, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    mark_lost(db_session, deal, reason="Desistiu", actor="admin:x")
    _login(client)

    assert "Cliente #" not in client.get("/loja/oportunidades").text


def test_the_store_can_say_it_will_analyze_and_the_team_sees_it_in_the_history(client, db_session):
    loja = _loja(db_session)
    _, _, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    decision = _decision(db_session, deal, loja)
    _login(client)

    response = client.post(f"/loja/oportunidades/{decision.id}/resposta", data={"decisao": "em_analise"}, follow_redirects=False)

    assert response.status_code == 303
    assert decision.response == PartnerResponse.EM_ANALISE
    assert decision.responded_at is not None
    event = db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="partner_response").one()
    assert event.actor == f"loja:{loja.id}"
    assert "Studio Fibra Sul" in event.note


def test_declining_needs_a_reason(client, db_session):
    loja = _loja(db_session)
    _, _, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    decision = _decision(db_session, deal, loja)
    _login(client)

    refused = client.post(f"/loja/oportunidades/{decision.id}/resposta", data={"decisao": "recusada", "motivo": " "})
    assert refused.status_code == 400
    assert decision.response == PartnerResponse.PENDENTE

    client.post(f"/loja/oportunidades/{decision.id}/resposta", data={"decisao": "recusada", "motivo": "Agenda cheia até dezembro"})
    assert decision.response == PartnerResponse.RECUSADA
    assert decision.response_reason == "Agenda cheia até dezembro"


def test_a_declined_opportunity_cannot_be_reopened_by_the_store(client, db_session):
    loja = _loja(db_session)
    _, _, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    decision = _decision(db_session, deal, loja)
    _login(client)
    client.post(f"/loja/oportunidades/{decision.id}/resposta", data={"decisao": "recusada", "motivo": "Sem agenda"})

    response = client.post(f"/loja/oportunidades/{decision.id}/resposta", data={"decisao": "em_analise"})

    assert response.status_code == 400
    assert decision.response == PartnerResponse.RECUSADA


def test_an_invalid_answer_is_rejected(client, db_session):
    loja = _loja(db_session)
    _, _, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    decision = _decision(db_session, deal, loja)
    _login(client)

    assert client.post(f"/loja/oportunidades/{decision.id}/resposta", data={"decisao": "pendente"}).status_code == 400
    assert client.post(f"/loja/oportunidades/{decision.id}/resposta", data={"decisao": "talvez"}).status_code == 400


def test_a_store_cannot_answer_for_another_store(client, db_session):
    mine = _loja(db_session, "Minha Loja", "minha@example.com")
    other = _loja(db_session, "Outra Loja", "outra@example.com")
    _, _, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    others = _decision(db_session, deal, other)
    _login(client, "minha@example.com")

    response = client.post(f"/loja/oportunidades/{others.id}/resposta", data={"decisao": "em_analise"})

    assert response.status_code == 404
    assert others.response == PartnerResponse.PENDENTE


def test_a_store_cannot_answer_an_opportunity_that_was_not_shared_to_it(client, db_session):
    loja = _loja(db_session)
    _, _, deal = _shared_deal(db_session)
    decision = _decision(db_session, deal, loja)
    _login(client)

    assert client.post(f"/loja/oportunidades/{decision.id}/resposta", data={"decisao": "em_analise"}).status_code == 404


def test_the_answer_appears_in_the_admin_matching_block(client, db_session):
    from piscinow.models.admin import AdminUser

    loja = _loja(db_session)
    _, qualification, deal = _shared_deal(db_session)
    share_with_partners(db_session, deal, actor="admin:x")
    decision = _decision(db_session, deal, loja)
    _login(client)
    client.post(f"/loja/oportunidades/{decision.id}/resposta", data={"decisao": "recusada", "motivo": "Agenda cheia"})
    client.post("/loja/logout")
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})

    response = client.get(f"/admin/oportunidades/{qualification.id}")

    assert "Não tem interesse" in response.text
    assert "Agenda cheia" in response.text


def test_the_loja_menu_has_the_inbox_and_marks_it_active(client, db_session):
    _loja(db_session)
    _login(client)

    assert 'href="/loja/oportunidades" aria-current="page"' in client.get("/loja/oportunidades").text
