import uuid

import pytest

from piscinow.models.member import Member, MemberStatus, ProfileType


def make_member(**kwargs):
    defaults = dict(profile_type=ProfileType.COMPRADOR, name="Teste")
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
