import uuid
from datetime import datetime, timedelta, timezone

import pytest

from piscinow.models.member import Member, MemberStatus, ProfileType


def make_member(**kwargs):
    defaults = dict(profile_type=ProfileType.COMPRADOR, name="Teste")
    defaults.update(kwargs)
    return Member(**defaults)


def make_loja_member(**kwargs):
    defaults = dict(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    defaults.update(kwargs)
    return Member(**defaults)


def test_new_member_starts_pending():
    assert make_member().status == MemberStatus.PENDING


def test_submit_for_review_moves_to_waitlisted():
    member = make_member()
    member.submit_for_review()
    assert member.status == MemberStatus.WAITLISTED


def test_submit_for_review_twice_raises():
    member = make_member()
    member.submit_for_review()
    with pytest.raises(ValueError):
        member.submit_for_review()


def test_approve_sets_approved_fields():
    member = make_member()
    member.submit_for_review()
    member.approve(approved_by="admin@piscinow.com.br")
    assert member.status == MemberStatus.APPROVED
    assert member.approved_by == "admin@piscinow.com.br"
    assert member.approved_at is not None


def test_reject_sets_rejected_status():
    member = make_member()
    member.submit_for_review()
    member.reject(approved_by="admin@piscinow.com.br")
    assert member.status == MemberStatus.REJECTED


def test_auto_approve_via_referral_requires_referrer():
    with pytest.raises(ValueError):
        make_member().auto_approve_via_referral()


def test_auto_approve_via_referral_sets_approved():
    member = make_member(referred_by_member_id=uuid.uuid4())
    member.auto_approve_via_referral()
    assert member.status == MemberStatus.APPROVED
    assert member.approved_by == "referral"


def test_member_persists_and_reloads(db_session):
    member = Member(
        profile_type=ProfileType.LOJA,
        name="Studio Fibra Sul",
        profile_details={"cnpj": "12.345.678/0001-90", "categories": ["fibra"]},
    )
    db_session.add(member)
    db_session.flush()
    db_session.expunge(member)

    reloaded = db_session.get(Member, member.id)

    assert reloaded.name == "Studio Fibra Sul"
    assert reloaded.profile_details["cnpj"] == "12.345.678/0001-90"


def test_generate_set_password_token_sets_token_and_future_expiry():
    member = make_loja_member()
    token = member.generate_set_password_token()
    assert member.set_password_token == token
    assert member.set_password_token_expires_at > datetime.now(timezone.utc)


def test_consume_set_password_token_accepts_valid_token():
    member = make_loja_member()
    token = member.generate_set_password_token()
    assert member.consume_set_password_token(token) is True


def test_consume_set_password_token_rejects_wrong_token():
    member = make_loja_member()
    member.generate_set_password_token()
    assert member.consume_set_password_token("token-errado") is False


def test_consume_set_password_token_rejects_expired_token():
    member = make_loja_member()
    token = member.generate_set_password_token()
    member.set_password_token_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    assert member.consume_set_password_token(token) is False


def test_consume_set_password_token_rejects_when_none_set():
    member = make_loja_member()
    assert member.consume_set_password_token("qualquer-coisa") is False


def test_set_password_hashes_and_clears_token():
    member = make_loja_member()
    member.generate_set_password_token()
    member.set_password("senha-forte-123")
    assert member.password_hash is not None
    assert member.password_hash != "senha-forte-123"
    assert member.set_password_token is None
    assert member.set_password_token_expires_at is None


def test_verify_password_accepts_correct_password():
    member = make_loja_member()
    member.set_password("senha-forte-123")
    assert member.verify_password("senha-forte-123") is True


def test_verify_password_rejects_wrong_password():
    member = make_loja_member()
    member.set_password("senha-forte-123")
    assert member.verify_password("errada") is False


def test_verify_password_returns_false_when_no_password_set():
    member = make_loja_member()
    assert member.verify_password("qualquer-coisa") is False
