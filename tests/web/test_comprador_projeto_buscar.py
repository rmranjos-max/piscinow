from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.member import Member, ProfileType
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectService
from piscinow.web.deps import get_llm_provider
from tests.web.test_comprador_projeto import _comprador_logged_in


def test_buscar_sugestoes_shows_matching_products(client, db_session):
    _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", region="Valinhos")
    db_session.add(loja)
    db_session.flush()
    product = Product(
        member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra 6x3", price=18000
    )
    db_session.add(product)
    db_session.flush()

    provider = FakeLLMProvider(['{"kind": "piscina", "category": "fibra", "region": "Valinhos"}'])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/comprador/projeto/buscar", data={"text": "piscina de fibra em Valinhos"})

    assert response.status_code == 200
    assert "Piscina Fibra 6x3" in response.text


def test_buscar_sugestoes_shows_note_when_no_match(client, db_session):
    _comprador_logged_in(client, db_session)
    provider = FakeLLMProvider(["desculpe nao entendi"])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/comprador/projeto/buscar", data={"text": "algo confuso"})

    assert response.status_code == 200
    assert "Nao encontrei nada" in response.text


def test_buscar_sugestoes_never_persists_a_choice(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()

    provider = FakeLLMProvider(['{"kind": "piscina", "category": "fibra", "region": null}'])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    client.post("/comprador/projeto/buscar", data={"text": "piscina de fibra"})

    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    assert project.product_id is None
    assert db_session.query(ProjectService).filter(ProjectService.project_id == project.id).count() == 0
