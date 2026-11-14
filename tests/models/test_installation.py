import pytest
from sqlalchemy.exc import IntegrityError

from piscinow.models.installation import AssignmentStatus, InstallerAssignment, InstallerProfile
from piscinow.models.member import Member, MemberStatus, ProfileType
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
    return deal


def _assignment(deal, installer, **overrides):
    values = dict(deal_id=deal.id, installer_member_id=installer.id, assigned_reason="Atende a região", assigned_by="admin:x")
    return InstallerAssignment(**{**values, **overrides})


def test_a_profile_starts_active_with_empty_lists_and_is_unique_per_installer(db_session):
    installer = _member(db_session, ProfileType.PRESTADOR, "Instalações Sul")
    db_session.add(InstallerProfile(member_id=installer.id))
    db_session.flush()
    profile = db_session.query(InstallerProfile).one()
    assert (profile.active, profile.service_areas, profile.service_kinds) == (True, [], [])

    db_session.add(InstallerProfile(member_id=installer.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_an_assignment_starts_pending(db_session):
    deal, installer = _deal(db_session), _member(db_session, ProfileType.PRESTADOR, "Instalações Sul")
    db_session.add(_assignment(deal, installer))
    db_session.flush()

    assignment = db_session.query(InstallerAssignment).one()
    assert assignment.status == AssignmentStatus.PENDENTE
    assert assignment.assigned_at is not None


def test_a_deal_has_only_one_live_assignment(db_session):
    deal = _deal(db_session)
    a, b = _member(db_session, ProfileType.PRESTADOR, "A"), _member(db_session, ProfileType.PRESTADOR, "B")
    db_session.add(_assignment(deal, a))
    db_session.flush()

    db_session.add(_assignment(deal, b))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("closed", [AssignmentStatus.RECUSADA, AssignmentStatus.CANCELADA])
def test_a_new_assignment_is_allowed_once_the_previous_one_is_declined_or_cancelled(db_session, closed):
    deal = _deal(db_session)
    a, b = _member(db_session, ProfileType.PRESTADOR, "A"), _member(db_session, ProfileType.PRESTADOR, "B")
    old = _assignment(deal, a)
    db_session.add(old)
    db_session.flush()
    old.status = closed
    db_session.flush()

    db_session.add(_assignment(deal, b))
    db_session.flush()

    assert db_session.query(InstallerAssignment).count() == 2


def test_an_accepted_assignment_still_blocks_another_one(db_session):
    deal = _deal(db_session)
    a, b = _member(db_session, ProfileType.PRESTADOR, "A"), _member(db_session, ProfileType.PRESTADOR, "B")
    db_session.add(_assignment(deal, a, status=AssignmentStatus.ACEITA))
    db_session.flush()

    db_session.add(_assignment(deal, b))
    with pytest.raises(IntegrityError):
        db_session.flush()
