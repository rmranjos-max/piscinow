from piscinow.models.member import Member, ProfileType
from piscinow.models.service import Service, ServiceKind


def test_vitrine_servicos_lists_active_items_without_price(client, db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", region="Valinhos")
    db_session.add(prestador)
    db_session.flush()
    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.INSTALACAO,
        category="piscina de fibra",
        name="Instalacao completa",
        price_min=3000,
        price_max=8000,
    )
    db_session.add(service)
    db_session.flush()

    response = client.get("/vitrine/servicos")

    assert response.status_code == 200
    assert "Instalacao completa" in response.text
    assert "3000" not in response.text
    assert "8000" not in response.text


def test_vitrine_servicos_hides_inactive_items(client, db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.INSTALACAO,
        category="fibra",
        name="Servico Desativado",
        active=False,
    )
    db_session.add(service)
    db_session.flush()

    response = client.get("/vitrine/servicos")

    assert "Servico Desativado" not in response.text


def test_vitrine_servicos_filters_by_kind(client, db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    instalacao = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    manutencao = Service(member_id=prestador.id, kind=ServiceKind.MANUTENCAO, category="filtragem", name="Manutencao")
    db_session.add_all([instalacao, manutencao])
    db_session.flush()

    response = client.get("/vitrine/servicos", params={"kind": "manutencao"})

    assert "Manutencao" in response.text
    assert "Instalacao" not in response.text


def test_vitrine_servicos_filters_by_region(client, db_session):
    prestador_valinhos = Member(profile_type=ProfileType.PRESTADOR, name="Prestador Valinhos", region="Valinhos")
    prestador_campinas = Member(profile_type=ProfileType.PRESTADOR, name="Prestador Campinas", region="Campinas")
    db_session.add_all([prestador_valinhos, prestador_campinas])
    db_session.flush()
    servico_valinhos = Service(member_id=prestador_valinhos.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Servico V")
    servico_campinas = Service(member_id=prestador_campinas.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Servico C")
    db_session.add_all([servico_valinhos, servico_campinas])
    db_session.flush()

    response = client.get("/vitrine/servicos", params={"regiao": "Valinhos"})

    assert "Servico V" in response.text
    assert "Servico C" not in response.text


def test_vitrine_servicos_does_not_require_authentication(client):
    response = client.get("/vitrine/servicos")
    assert response.status_code == 200


def test_vitrine_servicos_shows_price_and_add_button_when_logged_in(client, db_session):
    from piscinow.models.member import MemberStatus

    comprador = Member(
        profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED, email="comprador@example.com"
    )
    comprador.set_password("senha-forte-123")
    db_session.add(comprador)
    db_session.flush()
    client.post("/comprador/login", data={"email": "comprador@example.com", "password": "senha-forte-123"})

    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.INSTALACAO,
        category="piscina de fibra",
        name="Instalacao completa",
        price_min=3000,
        price_max=8000,
    )
    db_session.add(service)
    db_session.flush()

    response = client.get("/vitrine/servicos")

    assert "3000" in response.text
    assert "8000" in response.text
    assert "Adicionar" in response.text


def test_vitrine_servicos_hides_price_when_not_logged_in(client, db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.INSTALACAO,
        category="piscina de fibra",
        name="Instalacao completa",
        price_min=3000,
        price_max=8000,
    )
    db_session.add(service)
    db_session.flush()

    response = client.get("/vitrine/servicos")

    assert "3000" not in response.text
    assert "8000" not in response.text
    assert "Adicionar" not in response.text
