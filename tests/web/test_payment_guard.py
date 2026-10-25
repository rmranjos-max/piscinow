import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from piscinow.models.payment import AllocationStatus, PaymentStatus
from piscinow.rate_limit import limiter
from piscinow.web.app import create_app
from piscinow.web.deps import get_db
from tests.web.test_admin_liberar_fase import _paid_payment_with_allocation
from tests.web.test_admin_pagamentos import _logged_in
from tests.web.test_comprador_pagamento import _confirmed_project_with_payment

STRONG_SECRET = "s" * 40


def _production_env(monkeypatch, *, allow_simulation=False, secret=STRONG_SECRET):
    monkeypatch.setenv("PISCINOW_ENVIRONMENT", "production")
    monkeypatch.setenv("PISCINOW_SESSION_SECRET", secret)
    if allow_simulation:
        monkeypatch.setenv("PISCINOW_ALLOW_PAYMENT_SIMULATION", "true")


def _production_client(db_session, monkeypatch, *, allow_simulation=False):
    _production_env(monkeypatch, allow_simulation=allow_simulation)
    limiter.reset()
    app = create_app()

    def override_get_db():
        yield db_session
        db_session.commit()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_production_refuses_to_start_with_the_default_session_secret(monkeypatch):
    _production_env(monkeypatch, secret="change-me-in-production")

    with pytest.raises(RuntimeError, match="PISCINOW_SESSION_SECRET"):
        create_app()


def test_unknown_environment_value_is_rejected_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("PISCINOW_ENVIRONMENT", "prod")

    with pytest.raises(ValidationError):
        create_app()


def test_development_keeps_simulated_payments_enabled(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)

    app = create_app()

    assert app.state.payments_enabled is True
    assert app.state.payments_simulated is True


def test_production_disables_simulated_payments_by_default(monkeypatch):
    _production_env(monkeypatch)

    app = create_app()

    assert app.state.payments_enabled is False
    assert app.state.payments_simulated is True


def test_production_enables_simulated_payments_only_when_explicitly_allowed(monkeypatch):
    _production_env(monkeypatch, allow_simulation=True)

    app = create_app()

    assert app.state.payments_enabled is True


def test_pagar_returns_503_in_production_and_does_not_mark_as_paid(db_session, monkeypatch):
    client = _production_client(db_session, monkeypatch)
    comprador, payment = _confirmed_project_with_payment(client, db_session)

    response = client.post("/comprador/projeto/pagamento/pagar", follow_redirects=False)

    assert response.status_code == 503
    db_session.refresh(payment)
    assert payment.status == PaymentStatus.PENDENTE
    assert payment.external_charge_id is None


def test_pagamento_page_hides_the_pay_button_in_production(db_session, monkeypatch):
    client = _production_client(db_session, monkeypatch)
    _confirmed_project_with_payment(client, db_session)

    response = client.get("/comprador/projeto/pagamento")

    assert response.status_code == 200
    assert "/comprador/projeto/pagamento/pagar" not in response.text


def test_liberar_fase_returns_503_in_production_and_keeps_allocation_retido(db_session, monkeypatch):
    client = _production_client(db_session, monkeypatch)
    _logged_in(client, db_session)
    payment, allocation = _paid_payment_with_allocation(db_session)

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar", follow_redirects=False)

    assert response.status_code == 503
    db_session.refresh(allocation)
    assert allocation.status == AllocationStatus.RETIDO


def test_pagar_works_in_production_when_simulation_is_explicitly_allowed(db_session, monkeypatch):
    client = _production_client(db_session, monkeypatch, allow_simulation=True)
    comprador, payment = _confirmed_project_with_payment(client, db_session)

    response = client.post("/comprador/projeto/pagamento/pagar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(payment)
    assert payment.status == PaymentStatus.PAGO
