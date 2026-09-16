from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.product import Product
from piscinow.web.deps import get_llm_provider
from tests.web.test_loja_produtos import _loja_logged_in


def test_produtos_chat_prefills_form_without_saving(client, db_session):
    _loja_logged_in(client, db_session)
    provider = FakeLLMProvider(
        [
            '{"kind": "piscina", "category": "fibra", "name": "Piscina Fibra 6x3", '
            '"price": 18000, "size_label": "6x3m", "description": null}'
        ]
    )
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/loja/produtos/chat", data={"text": "piscina de fibra 6x3, R$18 mil"})

    assert response.status_code == 200
    assert "Piscina Fibra 6x3" in response.text
    assert db_session.query(Product).count() == 0


def test_produtos_chat_shows_note_when_extraction_fails(client, db_session):
    _loja_logged_in(client, db_session)
    provider = FakeLLMProvider(["desculpe nao entendi"])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/loja/produtos/chat", data={"text": "algo confuso"})

    assert response.status_code == 200
    assert "Nao consegui entender" in response.text
    assert db_session.query(Product).count() == 0
