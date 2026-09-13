from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType


def _logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def test_aprovar_loja_generates_set_password_token(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    client.post(f"/admin/fila/{member.id}/aprovar")

    db_session.refresh(member)
    assert member.set_password_token is not None


def test_aprovar_comprador_does_not_generate_token(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    client.post(f"/admin/fila/{member.id}/aprovar")

    db_session.refresh(member)
    assert member.set_password_token is None


def test_lojas_page_shows_set_password_link_when_pending(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.get("/admin/lojas")

    assert "Studio Fibra Sul" in response.text
    assert f"/loja/definir-senha/{token}" in response.text


def test_lojas_page_redirects_to_login_when_not_authenticated(client):
    response = client.get("/admin/lojas", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
