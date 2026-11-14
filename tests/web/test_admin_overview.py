import re

from piscinow.installation.service import assign_installer, respond_assignment, save_installer_profile
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import FieldSource
from piscinow.overview.service import gather_overview
from piscinow.proposals.service import accept_proposal
from piscinow.qualification.deals import active_deal, mark_lost
from piscinow.qualification.service import get_or_create_qualification, request_attention, set_consent, set_field
from tests.proposals.test_service import _approve_feasibility, _loja, _send, _setup

ACTOR = "admin:equipe@piscinow.com.br"


def _admin(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})


def _qualified_deal(db_session, name, email):
    buyer = Member(profile_type=ProfileType.COMPRADOR, name=name, status=MemberStatus.APPROVED, email=email)
    db_session.add(buyer)
    db_session.flush()
    qualification = get_or_create_qualification(db_session, buyer)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)
    return buyer, qualification, active_deal(db_session, buyer.id)


def _funnel(overview):
    return {row["key"]: row["count"] for row in overview["funnel"]}


def test_an_empty_system_has_an_honest_overview(db_session):
    overview = gather_overview(db_session)

    assert overview["deals_total"] == 0
    assert all(count == 0 for count in _funnel(overview).values())
    assert overview["loss_reasons"] == [] and overview["avg_to_accept"] == "—"


def test_the_overview_counts_real_deals_by_state_and_lists_loss_reasons(db_session):
    _qualified_deal(db_session, "A", "a@example.com")
    _, _, lost = _qualified_deal(db_session, "B", "b@example.com")
    _, _, lost2 = _qualified_deal(db_session, "C", "c@example.com")
    mark_lost(db_session, lost, reason="Sem retorno", actor=ACTOR)
    mark_lost(db_session, lost2, reason="sem retorno", actor=ACTOR)

    overview = gather_overview(db_session)

    assert _funnel(overview)["qualified"] == 1 and _funnel(overview)["lost"] == 2
    assert overview["deals_total"] == 3
    assert overview["loss_reasons"] == [("Sem retorno", 2)]
    assert overview["qualifications_total"] == 3 and overview["consent_granted"] == 3


def test_attention_requests_and_the_admission_queue_are_counted(db_session):
    buyer = Member(profile_type=ProfileType.COMPRADOR, name="Carlos", status=MemberStatus.APPROVED)
    waiting = Member(profile_type=ProfileType.LOJA, name="Nova Loja", status=MemberStatus.WAITLISTED)
    db_session.add_all([buyer, waiting])
    db_session.flush()
    request_attention(get_or_create_qualification(db_session, buyer), "Dúvida sobre prazo")

    overview = gather_overview(db_session)

    assert overview["attention_open"] == 1 and overview["waitlist"] == 1


def test_accepted_deals_without_an_installer_or_waiting_for_the_answer_are_flagged(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    accept_proposal(db_session, _send(db_session, decisions[loja.id]), buyer)

    assert gather_overview(db_session)["accepted_without_installer"] == 1

    installer = Member(profile_type=ProfileType.PRESTADOR, name="Instalações Sul", status=MemberStatus.APPROVED)
    db_session.add(installer)
    db_session.flush()
    save_installer_profile(db_session, installer, areas="Valinhos", service_kinds=["instalacao"], active=True, actor=ACTOR)
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)
    overview = gather_overview(db_session)
    assert overview["accepted_without_installer"] == 0 and overview["installer_pending"] == 1

    respond_assignment(db_session, assignment, installer, answer="aceita", reason="")
    overview = gather_overview(db_session)
    assert overview["installer_pending"] == 0 and overview["accepted_without_installer"] == 0
    assert overview["avg_to_accept"] != "—"


def test_the_overview_page_requires_an_admin_and_renders_the_numbers(client, db_session):
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/admin/login"
    _admin(client, db_session)
    _qualified_deal(db_session, "A", "a@example.com")

    page = client.get("/admin")

    assert page.status_code == 200
    assert "Visão geral" in page.text and 'data-state="qualified"' in page.text
    assert 'href="/admin" aria-current="page"' in page.text


def test_an_empty_overview_page_says_there_is_no_data_instead_of_showing_invented_numbers(client, db_session):
    _admin(client, db_session)

    page = client.get("/admin")

    assert "Ainda não há oportunidades" in page.text


def test_the_governance_trail_requires_an_admin(client):
    assert client.get("/admin/governanca", follow_redirects=False).headers["location"] == "/admin/login"


def test_the_governance_trail_lists_events_with_who_did_what_and_links_to_the_opportunity(client, db_session):
    _admin(client, db_session)
    loja = _loja(db_session)
    buyer, qualification, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    accept_proposal(db_session, _send(db_session, decisions[loja.id]), buyer)

    page = client.get("/admin/governanca")

    assert page.status_code == 200
    assert deal.code in page.text
    assert "Contato liberado" in page.text and "Proposta aceita" in page.text
    assert ACTOR in page.text
    assert f"/admin/oportunidades/{qualification.id}" in page.text


def test_the_trail_can_be_filtered_by_kind_and_an_unknown_kind_shows_everything(client, db_session):
    _admin(client, db_session)
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    accept_proposal(db_session, _send(db_session, decisions[loja.id]), buyer)

    contact = client.get("/admin/governanca?tipo=contato").text
    assert "Contato liberado" in contact and "Viabilidade" not in contact.split("<tbody>")[1]

    assert "Contato liberado" in client.get("/admin/governanca?tipo=qualquer").text


def test_the_trail_is_paginated_and_a_bad_page_number_is_harmless(client, db_session):
    from piscinow.qualification.deals import record_event

    _admin(client, db_session)
    _, _, deal = _qualified_deal(db_session, "A", "a@example.com")
    for index in range(60):
        record_event(db_session, deal, "feasibility", actor=ACTOR, note=f"Viabilidade: teste {index}")

    first = client.get("/admin/governanca?tipo=viabilidade")
    second = client.get("/admin/governanca?tipo=viabilidade&pagina=2")

    oldest = re.compile(r"teste 0\b")
    assert first.status_code == 200 and "teste 59" in first.text and not oldest.search(first.text)
    assert oldest.search(second.text) and "teste 59" not in second.text
    assert client.get("/admin/governanca?pagina=abc").status_code == 200
    assert client.get("/admin/governanca?pagina=999").status_code == 200
