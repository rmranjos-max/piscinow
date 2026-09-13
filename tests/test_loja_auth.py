import pytest
from fastapi import HTTPException
from starlette.requests import Request

from piscinow.loja_auth import LOJA_SESSION_KEY, login, logout


class _FakeSession(dict):
    pass


class _FakeRequest:
    def __init__(self):
        self.session = _FakeSession()


def test_login_sets_session_key_on_success(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="loja@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "loja@example.com", "senha-forte-123")

    assert result is True
    assert request.session[LOJA_SESSION_KEY] == str(member.id)


def test_login_fails_for_wrong_password(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="loja@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "loja@example.com", "errada")

    assert result is False
    assert LOJA_SESSION_KEY not in request.session


def test_login_fails_for_non_loja_profile(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.COMPRADOR, name="Marina", status=MemberStatus.APPROVED, email="marina@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "marina@example.com", "senha-forte-123")

    assert result is False


def test_logout_removes_session_key():
    request = _FakeRequest()
    request.session[LOJA_SESSION_KEY] = "some-id"
    logout(request)
    assert LOJA_SESSION_KEY not in request.session
