import pytest
from fastapi.testclient import TestClient

from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.web.app import create_app
from piscinow.web.deps import get_db, get_llm_provider


@pytest.fixture()
def rate_limited_client(db_session, monkeypatch):
    monkeypatch.setenv("PISCINOW_CHAT_RATE_LIMIT_PER_MINUTE", "2")
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    return TestClient(app)


def test_chat_endpoint_blocks_after_rate_limit_exceeded(rate_limited_client):
    for _ in range(2):
        response = rate_limited_client.post("/api/chat/message", data={"message": "oi"})
        assert response.status_code == 200

    response = rate_limited_client.post("/api/chat/message", data={"message": "oi de novo"})
    assert response.status_code == 429
