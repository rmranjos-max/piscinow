from sqlalchemy import select

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import AllocationStatus, PaymentAllocation, PaymentStatus
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project
from tests.web.test_comprador_pagamento import _confirmed_project_with_payment
from tests.web.test_comprador_projeto import _comprador_logged_in, _confirm_project


def _product(db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    return product


def test_inicio_redirects_to_login_when_not_authenticated(client):
    response = client.get("/comprador", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"


def test_a_new_comprador_is_greeted_by_first_name_and_told_to_choose_a_product(client, db_session):
    _comprador_logged_in(client, db_session)

    response = client.get("/comprador")

    assert response.status_code == 200
    assert "<h1>Olá, Marina.</h1>" in response.text
    assert "Escolha o seu produto" in response.text
    assert 'href="/vitrine/produtos"' in response.text


def test_opening_the_home_page_never_creates_a_project(client, db_session):
    comprador = _comprador_logged_in(client, db_session)

    client.get("/comprador")

    assert db_session.scalar(select(Project).where(Project.member_id == comprador.id)) is None


def test_a_draft_with_a_product_is_told_to_review_and_confirm(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    product = _product(db_session)
    db_session.add(Project(member_id=comprador.id, product_id=product.id))
    db_session.flush()

    response = client.get("/comprador")

    assert "Revise e confirme o projeto" in response.text
    assert "Piscina Fibra" in response.text


def test_a_confirmed_project_without_a_schedule_says_it_is_waiting_for_the_team(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    _confirm_project(db_session, comprador, _product(db_session))

    response = client.get("/comprador")

    assert "Aguardando o cronograma" in response.text
    assert 'href="/comprador/projeto/pagamento"' not in response.text


def test_a_pending_payment_links_to_the_payment_page(client, db_session):
    _confirmed_project_with_payment(client, db_session)

    response = client.get("/comprador")

    assert "Pagamento pendente" in response.text
    assert 'href="/comprador/projeto/pagamento"' in response.text
    assert "R$ 18.000,00" in response.text


def test_a_paid_payment_points_to_the_stage_tracking(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)
    payment.status = PaymentStatus.PAGO
    db_session.flush()

    response = client.get("/comprador")

    assert "Acompanhe os repasses" in response.text
    assert 'href="/comprador/obra"' in response.text


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
