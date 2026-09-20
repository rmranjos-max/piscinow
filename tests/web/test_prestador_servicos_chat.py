from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.service import Service
from piscinow.web.deps import get_llm_provider
from tests.web.test_prestador_servicos import _prestador_logged_in


def test_servicos_chat_prefills_form_without_saving(client, db_session):
    _prestador_logged_in(client, db_session)
    provider = FakeLLMProvider(
        [
            '{"kind": "instalacao", "category": "piscina de fibra", "name": "Instalacao completa", '
            '"price_min": 3000, "price_max": 8000, "description": null}'
        ]
    )
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/prestador/servicos/chat", data={"text": "instalacao de piscina de fibra, de 3 a 8 mil"})

    assert response.status_code == 200
    assert "Instalacao completa" in response.text
    assert db_session.query(Service).count() == 0


def test_servicos_chat_shows_note_when_extraction_fails(client, db_session):
    _prestador_logged_in(client, db_session)
    provider = FakeLLMProvider(["desculpe nao entendi"])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/prestador/servicos/chat", data={"text": "algo confuso"})

    assert response.status_code == 200
    assert "Nao consegui entender" in response.text
    assert db_session.query(Service).count() == 0
