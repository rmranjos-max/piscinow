from piscinow.models.member import Member, ProfileType
from piscinow.models.product import Product, ProductKind


def test_vitrine_produtos_lists_active_items_without_price(client, db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", region="Valinhos")
    db_session.add(loja)
    db_session.flush()
    product = Product(
        member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra 6x3", price=18000
    )
    db_session.add(product)
    db_session.flush()

    response = client.get("/vitrine/produtos")

    assert response.status_code == 200
    assert "Piscina Fibra 6x3" in response.text
    assert "18000" not in response.text


def test_vitrine_produtos_hides_inactive_items(client, db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(
        member_id=loja.id,
        kind=ProductKind.PISCINA,
        category="fibra",
        name="Piscina Desativada",
        price=18000,
        active=False,
    )
    db_session.add(product)
    db_session.flush()

    response = client.get("/vitrine/produtos")

    assert "Piscina Desativada" not in response.text


def test_vitrine_produtos_filters_by_kind(client, db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    piscina = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    equipamento = Product(
        member_id=loja.id, kind=ProductKind.EQUIPAMENTO, category="filtragem", name="Filtro X", price=500
    )
    db_session.add_all([piscina, equipamento])
    db_session.flush()

    response = client.get("/vitrine/produtos", params={"kind": "equipamento"})

    assert "Filtro X" in response.text
    assert "Piscina Fibra" not in response.text


def test_vitrine_produtos_filters_by_region(client, db_session):
    loja_valinhos = Member(profile_type=ProfileType.LOJA, name="Loja Valinhos", region="Valinhos")
    loja_campinas = Member(profile_type=ProfileType.LOJA, name="Loja Campinas", region="Campinas")
    db_session.add_all([loja_valinhos, loja_campinas])
    db_session.flush()
    produto_valinhos = Product(
        member_id=loja_valinhos.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina V", price=1000
    )
    produto_campinas = Product(
        member_id=loja_campinas.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina C", price=1000
    )
    db_session.add_all([produto_valinhos, produto_campinas])
    db_session.flush()

    response = client.get("/vitrine/produtos", params={"regiao": "Valinhos"})

    assert "Piscina V" in response.text
    assert "Piscina C" not in response.text


def test_vitrine_produtos_does_not_require_authentication(client):
    response = client.get("/vitrine/produtos")
    assert response.status_code == 200
