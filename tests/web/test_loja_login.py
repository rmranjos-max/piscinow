from piscinow.models.member import Member, MemberStatus, ProfileType


def test_login_with_correct_credentials_redirects_to_produtos(client, db_session):
    member = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="loja@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post(
        "/loja/login", data={"email": "loja@example.com", "password": "senha-forte-123"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/loja/produtos"


def test_login_with_wrong_password_shows_error(client, db_session):
    member = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="loja@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post("/loja/login", data={"email": "loja@example.com", "password": "errada"})

    assert response.status_code == 401
    assert "invalidos" in response.text
