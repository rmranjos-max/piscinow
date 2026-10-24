from decimal import Decimal

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment, PaymentAllocation
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectService, ProjectStatus
from piscinow.models.service import Service, ServiceKind
from tests.web.test_admin_pagamentos import _logged_in


def _confirmed_project_with_service(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add_all([comprador, loja, prestador])
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao completa")
    db_session.add(service)
    db_session.flush()
    db_session.add(ProjectService(project_id=project.id, service_id=service.id))
    db_session.flush()
    return project, product, service


def test_cronograma_form_shows_product_and_services(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.get(f"/admin/pagamentos/{project.id}/cronograma")

    assert response.status_code == 200
    assert "Piscina Fibra" in response.text
    assert "Instalacao completa" in response.text


def test_cronograma_form_rejects_non_confirmed_project(client, db_session):
    _logged_in(client, db_session)
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Rascunho", status=MemberStatus.APPROVED)
    db_session.add(comprador)
    db_session.flush()
    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()

    response = client.get(f"/admin/pagamentos/{project.id}/cronograma")

    assert response.status_code == 404


def test_cronograma_submit_creates_payment_and_allocations(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "18000",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    payment = db_session.query(Payment).filter(Payment.project_id == project.id).one()
    assert payment.total_amount == Decimal("21000")
    allocations = db_session.query(PaymentAllocation).filter(PaymentAllocation.payment_id == payment.id).all()
    assert len(allocations) == 2


def test_cronograma_submit_rejects_missing_stage(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "",
            f"amount_product_{product.id}": "18000",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
    )

    assert response.status_code == 400
    assert db_session.query(Payment).count() == 0


def test_cronograma_submit_rejects_invalid_amount(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "abc",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
    )

    assert response.status_code == 400
    assert db_session.query(Payment).count() == 0


def test_cronograma_submit_rejects_ambiguous_value_with_multiple_separators(client, db_session):
    """A value like "18.000,50" (pt-BR thousands dot + decimal comma) has two
    separator characters - rejected rather than guessed at, per the fix-wave
    decision to require a single, unambiguous decimal separator."""
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "18.000,50",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
    )

    assert response.status_code == 400
    assert db_session.query(Payment).count() == 0


def test_cronograma_submit_rejects_three_decimal_places(client, db_session):
    """"18.000" parses as the Decimal 18.000 (3 decimal places) if we accepted
    it as a lone-dot decimal - exactly the silent 1000x-smaller bug from
    Finding 3. Capping at 2 decimal places rejects it instead."""
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "18.000",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
    )

    assert response.status_code == 400
    assert db_session.query(Payment).count() == 0


def test_cronograma_submit_rejects_value_above_max(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "100000000",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
    )

    assert response.status_code == 400
    assert db_session.query(Payment).count() == 0


def test_cronograma_submit_rejects_total_above_max_even_if_each_item_is_within_limit(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "99999999,99",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "99999999,99",
        },
    )

    assert response.status_code == 400
    assert db_session.query(Payment).count() == 0


def test_cronograma_submit_total_matches_sum_of_rounded_allocations(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "18000,555",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000,005",
        },
    )

    # Both values have 3 decimal places, so both get rejected (max 2 allowed) -
    # this also proves the total-vs-allocations-sum consistency check below
    # never has a chance to run on bad data.
    assert response.status_code == 400
    assert db_session.query(Payment).count() == 0

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "18000,33",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000,33",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    payment = db_session.query(Payment).filter(Payment.project_id == project.id).one()
    allocations = db_session.query(PaymentAllocation).filter(PaymentAllocation.payment_id == payment.id).all()
    assert payment.total_amount == sum((a.amount for a in allocations), Decimal("0"))
    assert payment.total_amount == Decimal("21000.66")


def test_cronograma_submit_rejects_when_payment_already_exists(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)
    db_session.add(Payment(project_id=project.id, total_amount=18000))
    db_session.flush()

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "18000",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
    )

    assert response.status_code == 400
