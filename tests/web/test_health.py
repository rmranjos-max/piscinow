from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from piscinow.web.app import create_app
from piscinow.web.deps import get_db


def test_healthz_answers_without_touching_the_database(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_ready_when_the_database_answers(client):
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readyz_returns_503_when_the_database_is_unreachable(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)
    app = create_app()
    unreachable = create_engine("postgresql+psycopg://nobody:nopass@127.0.0.1:1/none", connect_args={"connect_timeout": 2})
    factory = sessionmaker(bind=unreachable)

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    response = TestClient(app).get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
