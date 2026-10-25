from datetime import date, timedelta
from decimal import Decimal

from piscinow.matching.inbox import respond
from piscinow.matching.service import run_matching, save_profile, share_with_partners
from piscinow.models.admin import AdminUser
from piscinow.models.matching import MatchingDecision
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.proposal import FeasibilityCheck, MessageAuthor
from piscinow.models.qualification import FieldSource
from piscinow.proposals.rules import FEASIBILITY_ITEMS
from piscinow.proposals.service import post_message, submit_proposal
from piscinow.qualification.deals import active_deal
from piscinow.qualification.service import get_or_create_qualification, set_consent, set_field


def _admin_logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})


def _deal_with_proposal(db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="l@example.com")
    db_session.add(loja)
    db_session.flush()
    save_profile(db_session, loja, areas="Valinhos", pool_types=["fibra"], budget_bands=[], capacity=5, active=True, actor="t")
    buyer = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    db_session.add(buyer)
    db_session.flush()
    qualification = get_or_create_qualification(db_session, buyer)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)
    deal = active_deal(db_session, buyer.id)
    run_matching(db_session, deal, actor="admin:x")
    share_with_partners(db_session, deal, actor="admin:x")
    decision = db_session.query(MatchingDecision).filter_by(deal_id=deal.id).one()
    respond(db_session, decision, answer="em_analise", reason="")
    submit_proposal(
        db_session, decision, items=[("Piscina", Decimal("18000.00"))], scope="Completo", lead_time_days=40,
        valid_until=date.today() + timedelta(days=10),
    )
    post_message(db_session, decision, author=MessageAuthor.COMPRADOR, member=buyer, text="Consegue 30 dias?", revision=True)
    return deal, qualification


def _form(status="approved", notes="", **states):
    data = {"status": status, "notes": notes}
    for key in FEASIBILITY_ITEMS:
        data[f"state_{key}"] = states.get(key, "ok")
        data[f"note_{key}"] = "Declive leve" if states.get(key) == "ressalva" else ""
    return data


def test_the_viability_form_requires_an_admin_login(client, db_session):
    _, qualification = _deal_with_proposal(db_session)

    response = client.post(f"/admin/oportunidades/{qualification.id}/viabilidade", data=_form(), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_the_admin_approves_the_viability_and_it_records_who_and_when(client, db_session):
    _admin_logged_in(client, db_session)
    deal, qualification = _deal_with_proposal(db_session)

    response = client.post(f"/admin/oportunidades/{qualification.id}/viabilidade", data=_form(), follow_redirects=True)

    assert response.status_code == 200
    check = db_session.query(FeasibilityCheck).one()
    assert check.status.value == "approved"
    assert check.decided_by == "admin:equipe@piscinow.com.br" and check.decided_at is not None
    assert "Aprovada" in response.text


def test_a_conditional_approval_keeps_the_caveat_notes(client, db_session):
    _admin_logged_in(client, db_session)
    _, qualification = _deal_with_proposal(db_session)

    client.post(
        f"/admin/oportunidades/{qualification.id}/viabilidade", data=_form("conditionally_approved", terreno="ressalva")
    )

    items = db_session.query(FeasibilityCheck).one().items
    assert next(i for i in items if i["key"] == "terreno") == {"key": "terreno", "state": "ressalva", "note": "Declive leve"}


def test_an_inconsistent_decision_is_refused_and_nothing_is_saved(client, db_session):
    _admin_logged_in(client, db_session)
    _, qualification = _deal_with_proposal(db_session)

    response = client.post(f"/admin/oportunidades/{qualification.id}/viabilidade", data=_form("approved", terreno="pendente"))

    assert response.status_code == 400
    assert "todos os itens precisam estar ok" in response.text
    assert db_session.query(FeasibilityCheck).count() == 0


def test_a_rejection_needs_an_explanation(client, db_session):
    _admin_logged_in(client, db_session)
    _, qualification = _deal_with_proposal(db_session)

    refused = client.post(f"/admin/oportunidades/{qualification.id}/viabilidade", data=_form("rejected", acesso="impeditivo"))
    assert refused.status_code == 400

    client.post(
        f"/admin/oportunidades/{qualification.id}/viabilidade",
        data=_form("rejected", notes="Sem acesso para equipamentos", acesso="impeditivo"),
    )
    assert db_session.query(FeasibilityCheck).one().status.value == "rejected"


def test_an_unknown_state_in_the_form_is_a_validation_error_not_a_crash(client, db_session):
    _admin_logged_in(client, db_session)
    _, qualification = _deal_with_proposal(db_session)
    data = _form()
    data["state_acesso"] = "talvez"

    assert client.post(f"/admin/oportunidades/{qualification.id}/viabilidade", data=data).status_code == 400


def test_the_detail_shows_the_proposals_and_the_negotiation_of_every_store(client, db_session):
    _admin_logged_in(client, db_session)
    _, qualification = _deal_with_proposal(db_session)

    page = client.get(f"/admin/oportunidades/{qualification.id}").text

    assert "Propostas" in page
    assert "Studio Fibra Sul" in page and "R$ 18.000,00" in page and "Versão 1" in page
    assert "Consegue 30 dias?" in page and "Pedido de revisão" in page
    assert "Viabilidade" in page
