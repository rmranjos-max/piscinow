from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.product import Product


def _loja_logged_in(client, db_session, *, email="loja@example.com", password="senha-forte-123"):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email=email)
    loja.set_password(password)
    db_session.add(loja)
    db_session.flush()
    client.post("/loja/login", data={"email": email, "password": password})
    return loja


def test_produtos_redirects_to_login_when_not_authenticated(client):
    response = client.get("/loja/produtos", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/loja/login"


def test_criar_produto_persists_and_lists(client, db_session):
    _loja_logged_in(client, db_session)

    response = client.post(
        "/loja/produtos",
        data={
            "kind": "piscina",
            "category": "fibra",
            "name": "Piscina Fibra 6x3",
            "price": "18000.00",
            "size_label": "6x3m",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    product = db_session.query(Product).filter(Product.name == "Piscina Fibra 6x3").one()
    assert product.category == "fibra"
    assert product.active is True

    listing = client.get("/loja/produtos")
    assert "Piscina Fibra 6x3" in listing.text


def test_criar_produto_with_invalid_price_shows_error_and_does_not_save(client, db_session):
    _loja_logged_in(client, db_session)

    response = client.post(
        "/loja/produtos",
        data={"kind": "piscina", "category": "fibra", "name": "Piscina Fibra 6x3", "price": "abc"},
    )
    assert response.status_code == 400
    assert "preco valido" in response.text
    assert db_session.query(Product).count() == 0


def test_criar_produto_with_invalid_kind_shows_error(client, db_session):
    _loja_logged_in(client, db_session)

    response = client.post(
        "/loja/produtos",
        data={"kind": "barco", "category": "fibra", "name": "Nao E Piscina", "price": "1000"},
    )
    assert response.status_code == 400
    assert "tipo de produto" in response.text
    assert db_session.query(Product).count() == 0


def test_criar_produto_with_infinite_price_shows_error_and_does_not_save(client, db_session):
    _loja_logged_in(client, db_session)

    response = client.post(
        "/loja/produtos",
        data={"kind": "piscina", "category": "fibra", "name": "Piscina Fibra 6x3", "price": "Infinity"},
    )
    assert response.status_code == 400
    assert "preco valido" in response.text
    assert db_session.query(Product).count() == 0


def test_criar_produto_with_price_above_max_shows_error_and_does_not_save(client, db_session):
    _loja_logged_in(client, db_session)

    response = client.post(
        "/loja/produtos",
        data={"kind": "piscina", "category": "fibra", "name": "Piscina Fibra 6x3", "price": "999999999.99"},
    )
    assert response.status_code == 400
    assert "preco valido" in response.text
    assert db_session.query(Product).count() == 0


def test_criar_produto_with_name_too_long_shows_error_and_does_not_save(client, db_session):
    _loja_logged_in(client, db_session)

    response = client.post(
        "/loja/produtos",
        data={"kind": "piscina", "category": "fibra", "name": "A" * 201, "price": "1000"},
    )
    assert response.status_code == 400
    assert "excede o limite" in response.text
    assert db_session.query(Product).count() == 0
