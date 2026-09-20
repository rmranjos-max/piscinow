from piscinow.models.member import Member, MemberStatus, ProfileType


def test_login_with_correct_credentials_redirects_to_servicos(client, db_session):
    member = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Instalacoes Sul",
        status=MemberStatus.APPROVED,
        email="prestador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post(
        "/prestador/login",
        data={"email": "prestador@example.com", "password": "senha-forte-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/prestador/servicos"


def test_login_with_wrong_password_shows_error(client, db_session):
    member = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Instalacoes Sul",
        status=MemberStatus.APPROVED,
        email="prestador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post("/prestador/login", data={"email": "prestador@example.com", "password": "errada"})

    assert response.status_code == 401
    assert "invalidos" in response.text


def test_login_blocks_after_rate_limit_exceeded(client, db_session):
    member = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Instalacoes Sul",
        status=MemberStatus.APPROVED,
        email="prestador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    for _ in range(5):
        response = client.post("/prestador/login", data={"email": "prestador@example.com", "password": "errada"})
        assert response.status_code == 401

    response = client.post("/prestador/login", data={"email": "prestador@example.com", "password": "errada"})
    assert response.status_code == 429
