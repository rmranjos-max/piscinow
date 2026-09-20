from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.service import Service, ServiceKind
from tests.web.test_prestador_servicos import _prestador_logged_in


def test_editar_servico_form_shows_current_values(client, db_session):
    prestador = _prestador_logged_in(client, db_session)
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Antigo", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.get(f"/prestador/servicos/{service.id}/editar")

    assert response.status_code == 200
    assert "Antigo" in response.text


def test_editar_servico_updates_fields(client, db_session):
    prestador = _prestador_logged_in(client, db_session)
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Antigo", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(
        f"/prestador/servicos/{service.id}/editar",
        data={
            "kind": "manutencao",
            "category": "filtragem",
            "name": "Novo Nome",
            "price_min": "1000",
            "price_max": "2000",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(service)
    assert service.name == "Novo Nome"
    assert service.kind == ServiceKind.MANUTENCAO
    assert service.price_min == 1000
    assert service.price_max == 2000


def test_editar_servico_with_non_finite_price_shows_error(client, db_session):
    prestador = _prestador_logged_in(client, db_session)
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Antigo", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(
        f"/prestador/servicos/{service.id}/editar",
        data={"kind": "instalacao", "category": "piscina de fibra", "name": "Antigo", "price_min": "inf", "price_max": ""},
    )

    assert response.status_code == 400
    db_session.refresh(service)
    assert service.name == "Antigo"


def test_editar_servico_de_outro_prestador_retorna_404(client, db_session):
    _prestador_logged_in(client, db_session, email="prestador1@example.com")

    outro_prestador = Member(profile_type=ProfileType.PRESTADOR, name="Outro Prestador", status=MemberStatus.APPROVED)
    db_session.add(outro_prestador)
    db_session.flush()
    service = Service(
        member_id=outro_prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Nao Meu", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(
        f"/prestador/servicos/{service.id}/editar",
        data={"kind": "instalacao", "category": "piscina de fibra", "name": "Hackeado", "price_min": "1", "price_max": ""},
    )

    assert response.status_code == 404
