import pytest
from sqlalchemy.exc import IntegrityError

from piscinow.models.matching import MatchingDecision, MatchOverride, PartnerProfile, PartnerResponse
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import Deal, LeadQualification


def _loja(db_session, name="Studio Fibra Sul"):
    member = Member(profile_type=ProfileType.LOJA, name=name, status=MemberStatus.APPROVED)
    db_session.add(member)
    db_session.flush()
    return member


def _deal(db_session):
    buyer = Member(profile_type=ProfileType.COMPRADOR, name="Marina", status=MemberStatus.APPROVED)
    db_session.add(buyer)
    db_session.flush()
    qualification = LeadQualification(member_id=buyer.id)
    db_session.add(qualification)
    db_session.flush()
    deal = Deal(member_id=buyer.id, qualification_id=qualification.id)
    db_session.add(deal)
    db_session.flush()
    return deal


def test_a_profile_starts_active_with_empty_lists_and_a_default_capacity(db_session):
    db_session.add(PartnerProfile(member_id=_loja(db_session).id))
    db_session.flush()

    profile = db_session.query(PartnerProfile).one()
    assert (profile.active, profile.capacity) == (True, 3)
    assert (profile.service_areas, profile.pool_types, profile.budget_bands) == ([], [], [])


def test_a_store_has_one_profile(db_session):
    loja = _loja(db_session)
    db_session.add(PartnerProfile(member_id=loja.id))
    db_session.flush()

    db_session.add(PartnerProfile(member_id=loja.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_capacity_must_be_positive(db_session):
    db_session.add(PartnerProfile(member_id=_loja(db_session).id, capacity=0))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_decision_starts_without_override_not_shared_and_pending(db_session):
    db_session.add(MatchingDecision(
        deal_id=_deal(db_session).id, partner_member_id=_loja(db_session).id, eligible=True,
        criteria=[{"key": "cidade", "passed": True, "detail": "Atende Valinhos"}],
    ))
    db_session.flush()

    decision = db_session.query(MatchingDecision).one()
    assert decision.override == MatchOverride.NENHUM
    assert decision.response == PartnerResponse.PENDENTE
    assert decision.shared_at is None
    assert decision.criteria[0]["detail"] == "Atende Valinhos"


def test_a_store_is_evaluated_once_per_deal(db_session):
    deal, loja = _deal(db_session), _loja(db_session)
    db_session.add(MatchingDecision(deal_id=deal.id, partner_member_id=loja.id, eligible=True))
    db_session.flush()

    db_session.add(MatchingDecision(deal_id=deal.id, partner_member_id=loja.id, eligible=False))
    with pytest.raises(IntegrityError):
        db_session.flush()
