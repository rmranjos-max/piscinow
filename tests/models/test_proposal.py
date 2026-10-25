from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.proposal import (
    DealMessage, FeasibilityCheck, FeasibilityStatus, MessageAuthor, Proposal, ProposalItem, ProposalStatus,
)
from piscinow.models.qualification import Deal, LeadQualification


def _member(db_session, profile, name):
    member = Member(profile_type=profile, name=name, status=MemberStatus.APPROVED)
    db_session.add(member)
    db_session.flush()
    return member


def _deal(db_session):
    buyer = _member(db_session, ProfileType.COMPRADOR, "Marina")
    qualification = LeadQualification(member_id=buyer.id)
    db_session.add(qualification)
    db_session.flush()
    deal = Deal(member_id=buyer.id, qualification_id=qualification.id)
    db_session.add(deal)
    db_session.flush()
    return deal, buyer


def _proposal(deal, loja, version=1, **overrides):
    values = dict(
        deal_id=deal.id, partner_member_id=loja.id, version=version, total=Decimal("21000.00"), scope="Instalação completa",
        lead_time_days=45, valid_until=date.today() + timedelta(days=15), created_by=f"loja:{loja.id}",
    )
    return Proposal(**{**values, **overrides})


def test_a_proposal_keeps_exact_decimal_values_and_starts_as_sent(db_session):
    deal, _ = _deal(db_session)
    loja = _member(db_session, ProfileType.LOJA, "Studio Fibra Sul")
    proposal = _proposal(deal, loja, total=Decimal("18000.30"))
    proposal.items = [ProposalItem(position=1, description="Piscina", amount=Decimal("18000.30"))]
    db_session.add(proposal)
    db_session.flush()
    db_session.expire_all()

    saved = db_session.query(Proposal).one()
    assert saved.status == ProposalStatus.ENVIADA
    assert saved.total == Decimal("18000.30")
    assert [(i.position, i.amount) for i in saved.items] == [(1, Decimal("18000.30"))]


def test_a_store_has_one_open_version_per_deal(db_session):
    deal, _ = _deal(db_session)
    loja = _member(db_session, ProfileType.LOJA, "Studio Fibra Sul")
    db_session.add(_proposal(deal, loja, 1))
    db_session.flush()

    db_session.add(_proposal(deal, loja, 2))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_new_version_is_fine_once_the_previous_is_superseded(db_session):
    deal, _ = _deal(db_session)
    loja = _member(db_session, ProfileType.LOJA, "Studio Fibra Sul")
    first = _proposal(deal, loja, 1)
    db_session.add(first)
    db_session.flush()
    first.status = ProposalStatus.SUBSTITUIDA
    db_session.flush()

    db_session.add(_proposal(deal, loja, 2))
    db_session.flush()

    assert db_session.query(Proposal).count() == 2


def test_the_same_version_number_cannot_repeat_for_a_store(db_session):
    deal, _ = _deal(db_session)
    loja = _member(db_session, ProfileType.LOJA, "Studio Fibra Sul")
    first = _proposal(deal, loja, 1, status=ProposalStatus.SUBSTITUIDA)
    db_session.add(first)
    db_session.flush()

    db_session.add(_proposal(deal, loja, 1))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_only_one_proposal_can_be_accepted_per_deal(db_session):
    deal, _ = _deal(db_session)
    a = _member(db_session, ProfileType.LOJA, "A")
    b = _member(db_session, ProfileType.LOJA, "B")
    db_session.add(_proposal(deal, a, status=ProposalStatus.ACEITA))
    db_session.flush()

    db_session.add(_proposal(deal, b, status=ProposalStatus.ACEITA))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("overrides", [dict(total=Decimal("0")), dict(lead_time_days=0), dict(version=0)])
def test_non_positive_totals_lead_times_and_versions_are_rejected_by_the_database(db_session, overrides):
    deal, _ = _deal(db_session)
    loja = _member(db_session, ProfileType.LOJA, "Studio Fibra Sul")
    db_session.add(_proposal(deal, loja, **overrides))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_non_positive_item_amount_is_rejected_by_the_database(db_session):
    deal, _ = _deal(db_session)
    loja = _member(db_session, ProfileType.LOJA, "Studio Fibra Sul")
    proposal = _proposal(deal, loja)
    proposal.items = [ProposalItem(position=1, description="Grátis", amount=Decimal("0"))]
    db_session.add(proposal)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_messages_are_kept_per_deal_and_store_with_the_revision_flag(db_session):
    deal, buyer = _deal(db_session)
    loja = _member(db_session, ProfileType.LOJA, "Studio Fibra Sul")
    db_session.add(DealMessage(
        deal_id=deal.id, partner_member_id=loja.id, author=MessageAuthor.COMPRADOR, author_member_id=buyer.id,
        is_revision_request=True, text="Consegue reduzir o prazo?",
    ))
    db_session.flush()

    message = db_session.query(DealMessage).one()
    assert message.is_revision_request is True
    assert message.created_at is not None


def test_a_deal_has_one_feasibility_check_that_starts_pending(db_session):
    deal, _ = _deal(db_session)
    db_session.add(FeasibilityCheck(deal_id=deal.id))
    db_session.flush()
    assert db_session.query(FeasibilityCheck).one().status == FeasibilityStatus.PENDING

    db_session.add(FeasibilityCheck(deal_id=deal.id))
    with pytest.raises(IntegrityError):
        db_session.flush()
