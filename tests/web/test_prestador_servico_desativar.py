from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.service import Service, ServiceKind
from tests.web.test_prestador_servicos import _prestador_logged_in


def test_desativar_servico_sets_active_false(client, db_session):
    prestador = _prestador_logged_in(client, db_session)
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Servico X", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(f"/prestador/servicos/{service.id}/desativar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(service)
    assert service.active is False


def test_desativar_servico_de_outro_prestador_retorna_404(client, db_session):
    _prestador_logged_in(client, db_session, email="prestador1@example.com")

    outro_prestador = Member(profile_type=ProfileType.PRESTADOR, name="Outro Prestador", status=MemberStatus.APPROVED)
    db_session.add(outro_prestador)
    db_session.flush()
    service = Service(
        member_id=outro_prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Nao Meu", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(f"/prestador/servicos/{service.id}/desativar")

    assert response.status_code == 404
