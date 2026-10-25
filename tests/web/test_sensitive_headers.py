import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from piscinow.web.sensitive_headers import SensitivePathHeadersMiddleware


@pytest.fixture()
def client():
    app = FastAPI()
    app.add_middleware(SensitivePathHeadersMiddleware)

    @app.get("/loja/definir-senha/{token}")
    def definir_senha(token: str):
        return {"ok": True}

    @app.get("/vitrine/produtos")
    def vitrine():
        return {"ok": True}

    return TestClient(app)


def test_set_password_pages_are_never_cached_and_send_no_referrer(client):
    response = client.get("/loja/definir-senha/abc123")

    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_other_pages_are_left_alone(client):
    response = client.get("/vitrine/produtos")

    assert "referrer-policy" not in response.headers
    assert "cache-control" not in response.headers
