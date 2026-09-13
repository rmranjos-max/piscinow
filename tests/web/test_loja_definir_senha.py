from piscinow.models.member import Member, MemberStatus, ProfileType


def test_definir_senha_form_rejects_invalid_token(client):
    response = client.get("/loja/definir-senha/token-invalido")
    assert response.status_code == 400


def test_definir_senha_sets_email_and_password(client, db_session):
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/loja/definir-senha/{token}",
        data={"email": "loja@example.com", "password": "senha-forte-123", "password_confirm": "senha-forte-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/loja/login"
    db_session.refresh(member)
    assert member.email == "loja@example.com"
    assert member.verify_password("senha-forte-123") is True
    assert member.set_password_token is None


def test_definir_senha_rejects_mismatched_passwords(client, db_session):
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/loja/definir-senha/{token}",
        data={"email": "loja@example.com", "password": "senha-forte-123", "password_confirm": "outra-senha"},
    )

    assert response.status_code == 400
    assert "nao coincidem" in response.text
    db_session.refresh(member)
    assert member.email is None


def test_definir_senha_rejects_duplicate_email(client, db_session):
    outra = Member(
        profile_type=ProfileType.LOJA, name="Outra Loja", status=MemberStatus.APPROVED, email="ja-usado@example.com"
    )
    db_session.add(outra)
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/loja/definir-senha/{token}",
        data={"email": "ja-usado@example.com", "password": "senha-forte-123", "password_confirm": "senha-forte-123"},
    )

    assert response.status_code == 400
    assert "ja esta em uso" in response.text
