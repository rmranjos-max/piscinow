import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from piscinow.web.origin_check import OriginCheckMiddleware


@pytest.fixture()
def client():
    app = FastAPI()
    app.add_middleware(OriginCheckMiddleware, extra_hosts=["piscinow.example"])

    @app.post("/acao")
    def acao():
        return {"ok": True}

    @app.get("/ler")
    def ler():
        return {"ok": True}

    return TestClient(app, base_url="http://app.local")


def test_post_from_a_foreign_origin_is_rejected(client):
    response = client.post("/acao", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403


def test_post_with_origin_null_is_rejected(client):
    response = client.post("/acao", headers={"Origin": "null"})

    assert response.status_code == 403


def test_post_from_the_same_origin_is_allowed(client):
    response = client.post("/acao", headers={"Origin": "http://app.local"})

    assert response.status_code == 200


def test_post_from_the_configured_public_host_is_allowed(client):
    response = client.post("/acao", headers={"Origin": "https://piscinow.example"})

    assert response.status_code == 200


def test_origin_takes_precedence_over_a_matching_referer(client):
    response = client.post(
        "/acao", headers={"Origin": "https://evil.example", "Referer": "http://app.local/qualquer"}
    )

    assert response.status_code == 403


def test_referer_is_checked_when_origin_is_absent(client):
    foreign = client.post("/acao", headers={"Referer": "https://evil.example/pagina"})
    same = client.post("/acao", headers={"Referer": "http://app.local/pagina"})

    assert foreign.status_code == 403
    assert same.status_code == 200


def test_post_without_origin_or_referer_is_allowed(client):
    response = client.post("/acao")

    assert response.status_code == 200


def test_safe_methods_are_never_blocked(client):
    response = client.get("/ler", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200
