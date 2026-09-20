from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.service import Service


def _prestador_logged_in(client, db_session, *, email="prestador@example.com", password="senha-forte-123"):
    prestador = Member(
        profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.APPROVED, email=email
    )
    prestador.set_password(password)
    db_session.add(prestador)
    db_session.flush()
    client.post("/prestador/login", data={"email": email, "password": password})
    return prestador


def test_servicos_redirects_to_login_when_not_authenticated(client):
    response = client.get("/prestador/servicos", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/prestador/login"


def test_criar_servico_persists_and_lists(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={
            "kind": "instalacao",
            "category": "piscina de fibra",
            "name": "Instalacao completa",
            "price_min": "3000.00",
            "price_max": "8000.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    service = db_session.query(Service).filter(Service.name == "Instalacao completa").one()
    assert service.category == "piscina de fibra"
    assert service.active is True
    assert service.price_min == 3000
    assert service.price_max == 8000

    listing = client.get("/prestador/servicos")
    assert "Instalacao completa" in listing.text


def test_criar_servico_with_empty_price_range_persists(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={"kind": "manutencao", "category": "filtragem", "name": "Manutencao mensal", "price_min": "", "price_max": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303

    service = db_session.query(Service).filter(Service.name == "Manutencao mensal").one()
    assert service.price_min is None
    assert service.price_max is None


def test_criar_servico_with_invalid_kind_shows_error(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={"kind": "pintura", "category": "geral", "name": "Nao E Servico Valido", "price_min": "", "price_max": ""},
    )
    assert response.status_code == 400
    assert "tipo de servico" in response.text
    assert db_session.query(Service).count() == 0


def test_criar_servico_with_non_finite_price_shows_error(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={
            "kind": "instalacao",
            "category": "piscina de fibra",
            "name": "Instalacao",
            "price_min": "Infinity",
            "price_max": "",
        },
    )
    assert response.status_code == 400
    assert db_session.query(Service).count() == 0


def test_criar_servico_with_min_greater_than_max_shows_error(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={
            "kind": "instalacao",
            "category": "piscina de fibra",
            "name": "Instalacao",
            "price_min": "9000",
            "price_max": "3000",
        },
    )
    assert response.status_code == 400
    assert db_session.query(Service).count() == 0


def test_criar_servico_with_name_over_limit_shows_error(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={
            "kind": "instalacao",
            "category": "piscina de fibra",
            "name": "x" * 201,
            "price_min": "",
            "price_max": "",
        },
    )
    assert response.status_code == 400
    assert db_session.query(Service).count() == 0
