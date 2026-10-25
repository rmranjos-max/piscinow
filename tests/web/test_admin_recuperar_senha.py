import uuid
from datetime import datetime, timedelta, timezone

import pytest

from piscinow.models.member import Member, MemberStatus, ProfileType
from tests.web.test_admin_pagamentos import _logged_in

AREAS = [
    (ProfileType.LOJA, "loja", "/admin/lojas"),
    (ProfileType.PRESTADOR, "prestador", "/admin/prestadores"),
    (ProfileType.COMPRADOR, "comprador", "/admin/compradores"),
]


def _active_member(db_session, profile_type, *, email="pessoa@example.com", password="senha-antiga-123"):
    member = Member(profile_type=profile_type, name="Pessoa Ativa", status=MemberStatus.APPROVED, email=email)
    member.set_password(password)
    db_session.add(member)
    db_session.flush()
    return member


@pytest.mark.parametrize("profile_type, area, list_path", AREAS)
def test_admin_generates_a_24h_link_for_an_active_member_and_sees_it_on_the_list(
    client, db_session, profile_type, area, list_path
):
    _logged_in(client, db_session)
    member = _active_member(db_session, profile_type)

    response = client.post(f"/admin/membros/{member.id}/novo-link-senha", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == list_path
    db_session.refresh(member)
    assert member.set_password_token is not None
    remaining = member.set_password_token_expires_at - datetime.now(timezone.utc)
    assert timedelta(hours=23) < remaining <= timedelta(hours=24)
    assert f"/{area}/definir-senha/{member.set_password_token}" in client.get(list_path).text


def test_the_old_password_keeps_working_until_the_new_one_is_set(client, db_session):
    _logged_in(client, db_session)
    member = _active_member(db_session, ProfileType.LOJA)

    client.post(f"/admin/membros/{member.id}/novo-link-senha")

    db_session.refresh(member)
    assert member.verify_password("senha-antiga-123") is True


def test_recovery_journey_new_password_replaces_the_old_and_the_link_is_single_use(client, db_session):
    _logged_in(client, db_session)
    member = _active_member(db_session, ProfileType.LOJA, email="loja@example.com")
    client.post(f"/admin/membros/{member.id}/novo-link-senha")
    db_session.refresh(member)
    token = member.set_password_token

    form = client.get(f"/loja/definir-senha/{token}")
    assert form.status_code == 200
    assert 'value="loja@example.com"' in form.text

    done = client.post(
        f"/loja/definir-senha/{token}",
        data={"email": "loja@example.com", "password": "senha-nova-456", "password_confirm": "senha-nova-456"},
        follow_redirects=False,
    )
    assert done.status_code == 303
    db_session.refresh(member)
    assert member.verify_password("senha-nova-456") is True
    assert member.verify_password("senha-antiga-123") is False
    assert member.set_password_token is None

    reuse = client.post(
        f"/loja/definir-senha/{token}",
        data={"email": "loja@example.com", "password": "outra-senha-789", "password_confirm": "outra-senha-789"},
    )
    assert reuse.status_code == 400
    db_session.refresh(member)
    assert member.verify_password("senha-nova-456") is True


def test_an_expired_recovery_link_is_refused(client, db_session):
    _logged_in(client, db_session)
    member = _active_member(db_session, ProfileType.PRESTADOR)
    client.post(f"/admin/membros/{member.id}/novo-link-senha")
    db_session.refresh(member)
    member.set_password_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()

    response = client.get(f"/prestador/definir-senha/{member.set_password_token}")

    assert response.status_code == 400


def test_generating_requires_an_admin_session(client, db_session):
    member = _active_member(db_session, ProfileType.LOJA)

    response = client.post(f"/admin/membros/{member.id}/novo-link-senha", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    db_session.refresh(member)
    assert member.set_password_token is None


def test_embaixador_and_unapproved_members_are_not_eligible(client, db_session):
    _logged_in(client, db_session)
    embaixador = Member(profile_type=ProfileType.EMBAIXADOR, name="Embaixador", status=MemberStatus.APPROVED)
    pendente = Member(profile_type=ProfileType.LOJA, name="Pendente", status=MemberStatus.WAITLISTED)
    db_session.add_all([embaixador, pendente])
    db_session.flush()

    assert client.post(f"/admin/membros/{embaixador.id}/novo-link-senha").status_code == 404
    assert client.post(f"/admin/membros/{pendente.id}/novo-link-senha").status_code == 404
    db_session.refresh(embaixador)
    db_session.refresh(pendente)
    assert embaixador.set_password_token is None
    assert pendente.set_password_token is None


@pytest.mark.parametrize("member_id", ["nao-e-um-uuid", str(uuid.uuid4())])
def test_unknown_or_malformed_member_id_returns_404(client, db_session, member_id):
    _logged_in(client, db_session)

    response = client.post(f"/admin/membros/{member_id}/novo-link-senha")

    assert response.status_code == 404
