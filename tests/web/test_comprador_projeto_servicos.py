from piscinow.models.member import Member, ProfileType
from piscinow.models.project import Project, ProjectService
from piscinow.models.service import Service, ServiceKind
from tests.web.test_comprador_projeto import _comprador_logged_in


def test_adicionar_servico_links_service_to_project(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    db_session.add(service)
    db_session.flush()

    response = client.post(f"/comprador/projeto/servicos/{service.id}/adicionar", follow_redirects=False)

    assert response.status_code == 303
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    link = db_session.query(ProjectService).filter(ProjectService.project_id == project.id).one()
    assert link.service_id == service.id


def test_adicionar_servico_duas_vezes_nao_duplica(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    db_session.add(service)
    db_session.flush()

    client.post(f"/comprador/projeto/servicos/{service.id}/adicionar")
    client.post(f"/comprador/projeto/servicos/{service.id}/adicionar")

    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    count = db_session.query(ProjectService).filter(ProjectService.project_id == project.id).count()
    assert count == 1


def test_adicionar_servico_inativo_retorna_404(client, db_session):
    _comprador_logged_in(client, db_session)
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Inativo", active=False
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(f"/comprador/projeto/servicos/{service.id}/adicionar")

    assert response.status_code == 404


def test_remover_servico_unlinks_service_from_project(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    db_session.add(service)
    db_session.flush()
    client.post(f"/comprador/projeto/servicos/{service.id}/adicionar")

    response = client.post(f"/comprador/projeto/servicos/{service.id}/remover", follow_redirects=False)

    assert response.status_code == 303
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    count = db_session.query(ProjectService).filter(ProjectService.project_id == project.id).count()
    assert count == 0
