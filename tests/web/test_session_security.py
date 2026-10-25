from piscinow.web.app import create_app
from tests.web.test_admin_liberar_fase import _paid_payment_with_allocation
from tests.web.test_comprador_pagamento import _confirmed_project_with_payment
from tests.web.test_comprador_projeto import _comprador_logged_in


def _session_middleware_kwargs(app):
    return next(m.kwargs for m in app.user_middleware if m.cls.__name__ == "SessionMiddleware")


def test_session_cookie_is_secure_and_samesite_lax_in_production(monkeypatch):
    monkeypatch.setenv("PISCINOW_ENVIRONMENT", "production")
    monkeypatch.setenv("PISCINOW_SESSION_SECRET", "s" * 40)

    kwargs = _session_middleware_kwargs(create_app())

    assert kwargs["https_only"] is True
    assert kwargs["same_site"] == "lax"


def test_session_cookie_is_not_secure_in_development_so_http_localhost_works(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)

    kwargs = _session_middleware_kwargs(create_app())

    assert kwargs["https_only"] is False
    assert kwargs["same_site"] == "lax"


def test_session_lifetime_is_configurable_and_shorter_than_the_framework_default(monkeypatch):
    monkeypatch.delenv("PISCINOW_SESSION_MAX_AGE_SECONDS", raising=False)
    default_kwargs = _session_middleware_kwargs(create_app())
    monkeypatch.setenv("PISCINOW_SESSION_MAX_AGE_SECONDS", "3600")
    custom_kwargs = _session_middleware_kwargs(create_app())

    assert default_kwargs["max_age"] == 7 * 24 * 3600
    assert custom_kwargs["max_age"] == 3600


def test_app_rejects_a_cross_site_post_before_reaching_any_route(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)
    client = TestClient(create_app(), base_url="http://app.local")

    response = client.post(
        "/comprador/login",
        data={"email": "x@example.com", "password": "whatever-123"},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403


def test_comprador_cannot_see_another_compradors_payment(client, db_session):
    _confirmed_project_with_payment(client, db_session)  # comprador A, with a payment
    _comprador_logged_in(client, db_session, email="outro@example.com")  # session now belongs to B

    response = client.get("/comprador/projeto/pagamento")

    assert response.status_code == 404


def test_pagar_without_login_redirects_to_comprador_login(client):
    response = client.post("/comprador/projeto/pagamento/pagar", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"


def test_liberar_fase_without_login_redirects_to_admin_login(client, db_session):
    payment, allocation = _paid_payment_with_allocation(db_session)

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
