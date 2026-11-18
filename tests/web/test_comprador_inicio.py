from sqlalchemy import select

from piscinow.models.payment import AllocationStatus, PaymentAllocation, PaymentStatus
from piscinow.models.project import Project
from piscinow.models.qualification import FieldSource, LeadQualification
from piscinow.proposals.service import accept_proposal
from piscinow.qualification.service import get_or_create_qualification, set_consent, set_field
from tests.proposals.test_service import _approve_feasibility, _loja, _send, _setup
from tests.web.test_comprador_pagamento import _confirmed_project_with_payment
from tests.web.test_comprador_projeto import _comprador_logged_in


def _login_as(client, db_session, buyer, email="jornada@example.com"):
    buyer.email = email
    buyer.set_password("senha-forte-123")
    db_session.flush()
    client.post("/comprador/login", data={"email": email, "password": "senha-forte-123"})


def test_inicio_redirects_to_login_when_not_authenticated(client):
    response = client.get("/comprador", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"


def test_a_new_comprador_is_greeted_and_invited_to_talk_to_the_assistant(client, db_session):
    _comprador_logged_in(client, db_session)

    response = client.get("/comprador")

    assert response.status_code == 200
    assert "<h1>Olá, Marina.</h1>" in response.text
    assert "Conte o que você imagina" in response.text
    assert 'href="/comprador/consultor"' in response.text
    for step in ["Briefing", "Propostas", "Aceite", "Pagamento por fases", "Obra"]:
        assert step in response.text


def test_opening_the_home_page_never_creates_anything(client, db_session):
    comprador = _comprador_logged_in(client, db_session)

    client.get("/comprador")

    assert db_session.scalar(select(Project).where(Project.member_id == comprador.id)) is None
    assert db_session.query(LeadQualification).count() == 0


def test_an_unfinished_briefing_asks_to_finish_it(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    qualification = get_or_create_qualification(db_session, comprador)
    set_field(db_session, qualification, "localizacao", "Valinhos", source=FieldSource.CLIENTE, actor="t")

    page = client.get("/comprador").text

    assert "Termine o seu briefing" in page and "Valinhos" in page


def test_a_shared_briefing_waits_for_the_team_to_pick_the_stores(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    qualification = get_or_create_qualification(db_session, comprador)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)

    page = client.get("/comprador").text

    assert "A equipe está escolhendo as lojas" in page
    assert "Compartilhado" in page


def test_open_proposals_become_the_next_step_with_the_viability(client, db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    _send(db_session, decisions[loja.id])
    _login_as(client, db_session, buyer)

    page = client.get("/comprador").text

    assert "Compare a proposta que chegou" in page
    assert 'href="/comprador/propostas"' in page
    assert "Viabilidade do terreno" in page and "Aprovada" in page


def test_after_the_acceptance_the_home_shows_the_project_and_waits_for_the_payment(client, db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    accept_proposal(db_session, _send(db_session, decisions[loja.id]), buyer)
    _login_as(client, db_session, buyer)

    page = client.get("/comprador").text

    assert "A equipe está preparando o pagamento" in page
    assert "Proposta aceita" in page and "Studio Fibra Sul" in page and "R$ 21.000,00" in page


def test_an_old_path_pending_payment_still_links_to_the_payment_page(client, db_session):
    _confirmed_project_with_payment(client, db_session)

    response = client.get("/comprador")

    assert "Pagamento pendente" in response.text
    assert 'href="/comprador/projeto/pagamento"' in response.text
    assert "R$ 18.000,00" in response.text


def test_an_old_path_paid_payment_points_to_the_work(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)
    payment.status = PaymentStatus.PAGO
    db_session.flush()

    response = client.get("/comprador")

    assert "Acompanhe a obra" in response.text
    assert 'href="/comprador/obra"' in response.text


def test_the_vitrine_is_offered_as_browsing_only(client, db_session):
    _comprador_logged_in(client, db_session)

    page = client.get("/comprador").text

    assert "Explorar piscinas" in page and "não muda nada no seu projeto" in page


def test_obra_redirects_to_login_when_not_authenticated(client):
    response = client.get("/comprador/obra", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"


def test_obra_without_a_schedule_explains_it_and_still_lists_the_four_stages(client, db_session):
    _comprador_logged_in(client, db_session)

    response = client.get("/comprador/obra")

    assert response.status_code == 200
    assert "ainda não foi montado pela equipe" in response.text
    for stage in ["Terraplanagem", "Estrutura", "Revestimento", "Acabamento"]:
        assert stage in response.text
    assert 'href="/comprador/projeto" aria-current="page"' in response.text


def test_obra_shows_retained_and_released_stages_from_the_real_allocations(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)

    retained = client.get("/comprador/obra").text
    assert "Valor retido" in retained and "Studio Fibra Sul" in retained and "R$ 18.000,00" in retained

    allocation = db_session.scalar(select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id))
    allocation.status = AllocationStatus.LIBERADO
    db_session.flush()

    released = client.get("/comprador/obra").text
    assert "Repasse liberado" in released


def test_a_comprador_never_sees_the_stages_or_values_of_another_comprador(client, db_session):
    _confirmed_project_with_payment(client, db_session)  # comprador A, with a schedule
    _comprador_logged_in(client, db_session, email="outro@example.com")  # session now belongs to B

    response = client.get("/comprador/obra")

    assert "Studio Fibra Sul" not in response.text
    assert "R$ 18.000,00" not in response.text
    assert "ainda não foi montado pela equipe" in response.text
