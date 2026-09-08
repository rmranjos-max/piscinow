from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType


def _logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def test_fila_redirects_to_login_when_not_authenticated(client):
    response = client.get("/admin/fila", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_fila_lists_waitlisted_members(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    response = client.get("/admin/fila")

    assert "Marina Duarte" in response.text


def test_aprovar_sets_member_status_approved(client, db_session):
    admin = _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    response = client.post(f"/admin/fila/{member.id}/aprovar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(member)
    assert member.status == MemberStatus.APPROVED
    assert member.approved_by == admin.email


def test_recusar_sets_member_status_rejected(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    response = client.post(f"/admin/fila/{member.id}/recusar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(member)
    assert member.status == MemberStatus.REJECTED
