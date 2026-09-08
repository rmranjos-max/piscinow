from piscinow.models.member import Member, ProfileType
from piscinow.referral import find_referrer, generate_referral_code, get_or_create_referral_code


def test_generate_referral_code_has_expected_length():
    assert len(generate_referral_code()) == 8


def test_get_or_create_referral_code_is_stable(db_session):
    member = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo")
    db_session.add(member)
    db_session.flush()

    first = get_or_create_referral_code(db_session, member)
    second = get_or_create_referral_code(db_session, member)

    assert first == second


def test_find_referrer_returns_matching_member(db_session):
    member = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo", referral_code="RM7X2K9A")
    db_session.add(member)
    db_session.flush()

    found = find_referrer(db_session, "RM7X2K9A")

    assert found is not None
    assert found.id == member.id


def test_find_referrer_returns_none_for_unknown_code(db_session):
    assert find_referrer(db_session, "UNKNOWN1") is None
