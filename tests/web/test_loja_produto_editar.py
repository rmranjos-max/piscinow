from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.product import Product, ProductKind
from tests.web.test_loja_produtos import _loja_logged_in


def test_editar_produto_form_shows_current_values(client, db_session):
    loja = _loja_logged_in(client, db_session)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Antigo", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.get(f"/loja/produtos/{product.id}/editar")

    assert response.status_code == 200
    assert "Antigo" in response.text


def test_editar_produto_updates_fields(client, db_session):
    loja = _loja_logged_in(client, db_session)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Antigo", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.post(
        f"/loja/produtos/{product.id}/editar",
        data={"kind": "piscina", "category": "fibra", "name": "Novo Nome", "price": "12000.00"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(product)
    assert product.name == "Novo Nome"
    assert product.price == 12000


def test_editar_produto_with_infinite_price_shows_error_and_does_not_save(client, db_session):
    loja = _loja_logged_in(client, db_session)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Antigo", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.post(
        f"/loja/produtos/{product.id}/editar",
        data={"kind": "piscina", "category": "fibra", "name": "Novo Nome", "price": "Infinity"},
    )

    assert response.status_code == 400
    assert "preco valido" in response.text
    db_session.refresh(product)
    assert product.name == "Antigo"


def test_editar_produto_de_outra_loja_retorna_404(client, db_session):
    _loja_logged_in(client, db_session, email="loja1@example.com")

    outra_loja = Member(profile_type=ProfileType.LOJA, name="Outra Loja", status=MemberStatus.APPROVED)
    db_session.add(outra_loja)
    db_session.flush()
    product = Product(member_id=outra_loja.id, kind=ProductKind.PISCINA, category="fibra", name="Nao Meu", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.post(
        f"/loja/produtos/{product.id}/editar",
        data={"kind": "piscina", "category": "fibra", "name": "Hackeado", "price": "1.00"},
    )

    assert response.status_code == 404
