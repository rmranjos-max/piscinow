import pytest
from sqlalchemy.exc import IntegrityError

from piscinow.models.member import Member, ProfileType
from piscinow.models.project import Project, ProjectService, ProjectStatus
from piscinow.models.service import Service, ServiceKind


def test_project_persists_with_default_status(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    db_session.add(comprador)
    db_session.flush()

    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()
    db_session.expunge(project)

    reloaded = db_session.get(Project, project.id)
    assert reloaded.status == ProjectStatus.RASCUNHO
    assert reloaded.product_id is None


def test_project_service_links_project_to_service(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add_all([comprador, prestador])
    db_session.flush()

    project = Project(member_id=comprador.id)
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    db_session.add_all([project, service])
    db_session.flush()

    link = ProjectService(project_id=project.id, service_id=service.id)
    db_session.add(link)
    db_session.flush()
    db_session.expunge(link)

    reloaded = db_session.get(ProjectService, link.id)
    assert reloaded.project_id == project.id
    assert reloaded.service_id == service.id


def test_project_member_id_is_unique(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    db_session.add(comprador)
    db_session.flush()

    project_a = Project(member_id=comprador.id)
    db_session.add(project_a)
    db_session.flush()

    project_b = Project(member_id=comprador.id)
    db_session.add(project_b)
    with pytest.raises(IntegrityError):
        db_session.flush()
