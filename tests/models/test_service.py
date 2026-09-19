from piscinow.models.member import Member, ProfileType
from piscinow.models.service import Service, ServiceKind


def test_service_persists_and_reloads(db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()

    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.INSTALACAO,
        category="piscina de fibra",
        name="Instalacao completa",
        price_min=3000.00,
        price_max=8000.00,
    )
    db_session.add(service)
    db_session.flush()
    db_session.expunge(service)

    reloaded = db_session.get(Service, service.id)

    assert reloaded.name == "Instalacao completa"
    assert reloaded.category == "piscina de fibra"
    assert reloaded.active is True
    assert reloaded.member_id == prestador.id
    assert reloaded.price_min == 3000
    assert reloaded.price_max == 8000


def test_service_allows_null_price_range(db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()

    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.MANUTENCAO,
        category="filtragem",
        name="Manutencao mensal",
    )
    db_session.add(service)
    db_session.flush()
    db_session.expunge(service)

    reloaded = db_session.get(Service, service.id)

    assert reloaded.price_min is None
    assert reloaded.price_max is None
