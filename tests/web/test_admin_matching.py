from piscinow.matching.service import get_profile, run_matching, save_profile
from piscinow.models.admin import AdminUser
from piscinow.models.matching import MatchingDecision, MatchOverride
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import DealStatus, FieldSource
from piscinow.qualification.deals import active_deal
from piscinow.qualification.service import get_or_create_qualification, set_consent, set_field


def _admin_logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def _loja(db_session, name="Studio Fibra Sul", *, profile=True, areas="Valinhos"):
    loja = Member(profile_type=ProfileType.LOJA, name=name, status=MemberStatus.APPROVED, email=f"{name[:4]}@x.com")
    db_session.add(loja)
    db_session.flush()
    if profile:
        save_profile(db_session, loja, areas=areas, pool_types=["fibra"], budget_bands=[], capacity=3, active=True, actor="t")
    return loja


def _deal(db_session):
    buyer = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    db_session.add(buyer)
    db_session.flush()
    qualification = get_or_create_qualification(db_session, buyer)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)
    return active_deal(db_session, buyer.id), qualification


def test_the_profile_form_requires_an_admin_login(client, db_session):
    loja = _loja(db_session, profile=False)

    response = client.get(f"/admin/lojas/{loja.id}/atendimento", follow_redirects=False)

    assert response.status_code == 303


def test_the_profile_form_shows_the_saved_values(client, db_session):
    _admin_logged_in(client, db_session)
    loja = _loja(db_session, areas="Valinhos, Campinas")

    response = client.get(f"/admin/lojas/{loja.id}/atendimento")

    assert response.status_code == 200
    assert "Valinhos, Campinas" in response.text
    assert "Studio Fibra Sul" in response.text


def test_the_admin_saves_a_store_profile(client, db_session):
    _admin_logged_in(client, db_session)
    loja = _loja(db_session, profile=False)

    response = client.post(
        f"/admin/lojas/{loja.id}/atendimento",
        data={"areas": "Valinhos, Vinhedo", "pool_types": ["fibra", "vinil"], "budget_bands": ["30_a_50_mil"],
              "capacity": "4", "active": "on"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    profile = get_profile(db_session, loja.id)
    assert profile.service_areas == ["Valinhos", "Vinhedo"]
    assert profile.pool_types == ["fibra", "vinil"]
    assert profile.budget_bands == ["30_a_50_mil"]
    assert (profile.capacity, profile.active) == (4, True)
    assert profile.updated_by == "admin:equipe@piscinow.com.br"


def test_an_unchecked_active_box_deactivates_the_profile(client, db_session):
    _admin_logged_in(client, db_session)
    loja = _loja(db_session)

    client.post(f"/admin/lojas/{loja.id}/atendimento", data={"areas": "Valinhos", "capacity": "3"})

    assert get_profile(db_session, loja.id).active is False


def test_an_invalid_profile_shows_the_error_and_saves_nothing(client, db_session):
    _admin_logged_in(client, db_session)
    loja = _loja(db_session, profile=False)

    response = client.post(f"/admin/lojas/{loja.id}/atendimento", data={"areas": " ", "capacity": "3"})

    assert response.status_code == 400
    assert "ao menos uma cidade" in response.text
    assert get_profile(db_session, loja.id) is None


def test_a_non_numeric_capacity_is_a_validation_error_not_a_crash(client, db_session):
    _admin_logged_in(client, db_session)
    loja = _loja(db_session, profile=False)

    response = client.post(f"/admin/lojas/{loja.id}/atendimento", data={"areas": "Valinhos", "capacity": "muitas"})

    assert response.status_code == 400


def test_the_profile_form_only_exists_for_stores(client, db_session):
    _admin_logged_in(client, db_session)
    buyer = Member(profile_type=ProfileType.COMPRADOR, name="Marina", status=MemberStatus.APPROVED)
    db_session.add(buyer)
    db_session.flush()

    assert client.get(f"/admin/lojas/{buyer.id}/atendimento").status_code == 404
    assert client.get("/admin/lojas/nao-uuid/atendimento").status_code == 404


def test_the_stores_list_links_to_each_profile(client, db_session):
    _admin_logged_in(client, db_session)
    loja = _loja(db_session)

    assert f"/admin/lojas/{loja.id}/atendimento" in client.get("/admin/lojas").text


def test_running_the_matching_from_the_detail_shows_each_store_with_the_reasons(client, db_session):
    _admin_logged_in(client, db_session)
    _loja(db_session, "Studio Fibra Sul")
    _loja(db_session, "Longe Demais", areas="Sorocaba")
    _, qualification = _deal(db_session)

    response = client.post(f"/admin/oportunidades/{qualification.id}/matching/executar", follow_redirects=True)

    assert response.status_code == 200
    assert "Studio Fibra Sul" in response.text
    assert "Longe Demais" in response.text
    assert "Atende Valinhos" in response.text
    assert "Não atende Valinhos" in response.text
    assert "Lojas indicadas" in response.text


def test_an_override_without_a_reason_is_refused_and_one_with_a_reason_is_applied(client, db_session):
    _admin_logged_in(client, db_session)
    far = _loja(db_session, "Longe Demais", areas="Sorocaba")
    deal, qualification = _deal(db_session)
    run_matching(db_session, deal, actor="t")
    decision = db_session.query(MatchingDecision).filter_by(partner_member_id=far.id).one()
    url = f"/admin/oportunidades/{qualification.id}/matching/{decision.id}/revisao"

    refused = client.post(url, data={"decisao": "incluida", "motivo": ""})
    assert refused.status_code == 400
    assert decision.override == MatchOverride.NENHUM

    client.post(url, data={"decisao": "incluida", "motivo": "Atende por parceria"}, follow_redirects=False)
    assert decision.override == MatchOverride.INCLUIDA


def test_an_unknown_override_value_is_rejected(client, db_session):
    _admin_logged_in(client, db_session)
    loja = _loja(db_session)
    deal, qualification = _deal(db_session)
    run_matching(db_session, deal, actor="t")
    decision = db_session.query(MatchingDecision).filter_by(partner_member_id=loja.id).one()

    response = client.post(
        f"/admin/oportunidades/{qualification.id}/matching/{decision.id}/revisao", data={"decisao": "talvez", "motivo": "x"}
    )

    assert response.status_code == 400


def test_a_decision_of_another_opportunity_cannot_be_changed_through_this_url(client, db_session):
    _admin_logged_in(client, db_session)
    loja = _loja(db_session)
    deal, _ = _deal(db_session)
    run_matching(db_session, deal, actor="t")
    decision = db_session.query(MatchingDecision).filter_by(partner_member_id=loja.id).one()
    other_buyer = Member(profile_type=ProfileType.COMPRADOR, name="Outro", status=MemberStatus.APPROVED)
    db_session.add(other_buyer)
    db_session.flush()
    other_q = get_or_create_qualification(db_session, other_buyer)

    response = client.post(
        f"/admin/oportunidades/{other_q.id}/matching/{decision.id}/revisao", data={"decisao": "excluida", "motivo": "x"}
    )

    assert response.status_code == 404
    assert decision.override == MatchOverride.NENHUM


def test_sharing_moves_the_opportunity_to_partner_review(client, db_session):
    _admin_logged_in(client, db_session)
    _loja(db_session)
    deal, qualification = _deal(db_session)
    run_matching(db_session, deal, actor="t")

    response = client.post(f"/admin/oportunidades/{qualification.id}/matching/encaminhar", follow_redirects=True)

    assert response.status_code == 200
    assert deal.status == DealStatus.PARTNER_REVIEW
    assert "Em análise pela loja" in response.text


def test_sharing_with_no_eligible_store_shows_the_error(client, db_session):
    _admin_logged_in(client, db_session)
    _loja(db_session, areas="Sorocaba")
    deal, qualification = _deal(db_session)
    run_matching(db_session, deal, actor="t")

    response = client.post(f"/admin/oportunidades/{qualification.id}/matching/encaminhar")

    assert response.status_code == 400
    assert "Nenhuma loja elegível" in response.text
    assert deal.status == DealStatus.MATCHED


def test_matching_is_not_offered_before_the_opportunity_exists(client, db_session):
    _admin_logged_in(client, db_session)
    buyer = Member(profile_type=ProfileType.COMPRADOR, name="Sem Deal", status=MemberStatus.APPROVED)
    db_session.add(buyer)
    db_session.flush()
    qualification = get_or_create_qualification(db_session, buyer)

    assert client.post(f"/admin/oportunidades/{qualification.id}/matching/executar").status_code == 404
