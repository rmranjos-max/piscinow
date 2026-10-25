import pytest
from sqlalchemy.exc import IntegrityError

from piscinow.models.conversation import Conversation
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import (
    ConsentState,
    Deal,
    DealEvent,
    DealStatus,
    FieldSource,
    LeadQualification,
    QualificationField,
    QualificationStatus,
    Verification,
)


def _comprador(db_session, name="Marina Duarte"):
    member = Member(profile_type=ProfileType.COMPRADOR, name=name, status=MemberStatus.APPROVED)
    db_session.add(member)
    db_session.flush()
    return member


def _qualification(db_session, member):
    qualification = LeadQualification(member_id=member.id)
    db_session.add(qualification)
    db_session.flush()
    return qualification


def test_a_new_qualification_starts_in_progress_with_no_consent_and_no_asks(db_session):
    qualification = _qualification(db_session, _comprador(db_session))
    db_session.refresh(qualification)

    assert qualification.status == QualificationStatus.EM_ANDAMENTO
    assert qualification.consent == ConsentState.NAO_RESPONDIDO
    assert qualification.asks == {}
    assert qualification.consent_at is None


def test_each_comprador_has_at_most_one_qualification(db_session):
    member = _comprador(db_session)
    _qualification(db_session, member)

    db_session.add(LeadQualification(member_id=member.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_field_carries_its_source_verification_and_date(db_session):
    qualification = _qualification(db_session, _comprador(db_session))
    db_session.add(QualificationField(qualification_id=qualification.id, key="localizacao", value="Valinhos"))
    db_session.flush()

    field = db_session.query(QualificationField).one()
    assert field.source == FieldSource.CLIENTE
    assert field.verification == Verification.DECLARADO
    assert field.updated_at is not None


def test_a_qualification_cannot_have_the_same_field_twice(db_session):
    qualification = _qualification(db_session, _comprador(db_session))
    db_session.add(QualificationField(qualification_id=qualification.id, key="prazo", value="ate_90_dias"))
    db_session.flush()

    db_session.add(QualificationField(qualification_id=qualification.id, key="prazo", value="sem_prazo"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_values_returns_the_fields_as_a_plain_dict(db_session):
    qualification = _qualification(db_session, _comprador(db_session))
    db_session.add_all([
        QualificationField(qualification_id=qualification.id, key="localizacao", value="Valinhos"),
        QualificationField(qualification_id=qualification.id, key="prazo", value="ate_90_dias"),
    ])
    db_session.flush()
    db_session.refresh(qualification)

    assert qualification.values() == {"localizacao": "Valinhos", "prazo": "ate_90_dias"}


def test_deals_get_a_sequential_number_and_a_readable_code(db_session):
    first_member, second_member = _comprador(db_session, "A"), _comprador(db_session, "B")
    first = Deal(member_id=first_member.id, qualification_id=_qualification(db_session, first_member).id)
    second = Deal(member_id=second_member.id, qualification_id=_qualification(db_session, second_member).id)
    db_session.add_all([first, second])
    db_session.flush()

    assert first.status == DealStatus.QUALIFIED
    assert second.number == first.number + 1
    assert first.code == f"OP-{first.number:04d}"


def test_a_comprador_can_have_only_one_active_deal(db_session):
    member = _comprador(db_session)
    qualification = _qualification(db_session, member)
    db_session.add(Deal(member_id=member.id, qualification_id=qualification.id))
    db_session.flush()

    db_session.add(Deal(member_id=member.id, qualification_id=qualification.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("closed", [DealStatus.LOST, DealStatus.CANCELLED])
def test_a_new_deal_is_allowed_once_the_previous_one_is_closed(db_session, closed):
    member = _comprador(db_session)
    qualification = _qualification(db_session, member)
    old = Deal(member_id=member.id, qualification_id=qualification.id)
    db_session.add(old)
    db_session.flush()
    old.status = closed
    db_session.flush()

    db_session.add(Deal(member_id=member.id, qualification_id=qualification.id))
    db_session.flush()

    assert db_session.query(Deal).filter(Deal.member_id == member.id).count() == 2


def test_deal_events_keep_the_history_in_order(db_session):
    member = _comprador(db_session)
    deal = Deal(member_id=member.id, qualification_id=_qualification(db_session, member).id)
    db_session.add(deal)
    db_session.flush()
    db_session.add_all([
        DealEvent(deal_id=deal.id, kind="created", to_status="qualified", actor="sistema"),
        DealEvent(deal_id=deal.id, kind="status_changed", from_status="qualified", to_status="lost",
                  note="Sem retorno", actor="admin:equipe@piscinow.com.br"),
    ])
    db_session.flush()

    events = db_session.query(DealEvent).filter(DealEvent.deal_id == deal.id).order_by(DealEvent.created_at).all()
    assert [e.kind for e in events] == ["created", "status_changed"]


def test_conversations_default_to_the_landing_purpose(db_session):
    conversation = Conversation()
    db_session.add(conversation)
    db_session.flush()
    db_session.refresh(conversation)

    assert conversation.purpose == "landing"
