from piscinow.models.payment import PaymentStatus
from piscinow.payment.providers.fake_provider import FakePaymentProvider
from piscinow.web.deps import get_payment_provider
from tests.web.test_comprador_pagamento import _confirmed_project_with_payment


def test_pagar_success_charges_and_marks_paid(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)

    response = client.post("/comprador/projeto/pagamento/pagar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(payment)
    assert payment.status == PaymentStatus.PAGO
    assert payment.external_charge_id is not None
    assert payment.paid_at is not None


def test_pagar_twice_returns_400(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)
    client.post("/comprador/projeto/pagamento/pagar")

    response = client.post("/comprador/projeto/pagamento/pagar")

    assert response.status_code == 400


def test_pagar_shows_error_when_provider_fails(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)
    provider = FakePaymentProvider(should_fail_charge=True)
    client.app.dependency_overrides[get_payment_provider] = lambda: provider

    response = client.post("/comprador/projeto/pagamento/pagar")

    assert response.status_code == 400
    assert "Nao foi possivel processar" in response.text
    db_session.refresh(payment)
    assert payment.status == PaymentStatus.PENDENTE
