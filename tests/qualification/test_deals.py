import pytest

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import ConsentState, Deal, DealEvent, DealStatus, FieldSource
from piscinow.qualification.deals import active_deal, mark_lost, open_deal_if_qualified
from piscinow.qualification.service import get_or_create_qualification, set_consent, set_field


def _comprador(db_session, name="Marina Duarte"):
    member = Member(profile_type=ProfileType.COMPRADOR, name=name, status=MemberStatus.APPROVED)
    db_session.add(member)
    db_session.flush()
    return member


def _fill(db_session, qualification, *, keys=("localizacao", "tipo_piscina", "prazo")):
    values = {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}
    for key in keys:
        set_field(db_session, qualification, key, values[key], source=FieldSource.CLIENTE, actor="t")


def test_consent_with_the_essential_data_opens_one_qualified_deal_with_its_first_event(db_session):
    member = _comprador(db_session)
    qualification = get_or_create_qualification(db_session, member)
    _fill(db_session, qualification)

    set_consent(db_session, qualification, True)

    deal = active_deal(db_session, member.id)
    assert deal.status == DealStatus.QUALIFIED
    assert deal.code.startswith("OP-")
    [event] = db_session.query(DealEvent).filter_by(deal_id=deal.id).all()
    assert (event.kind, event.to_status, event.actor) == ("created", "qualified", "sistema")


def test_no_deal_without_consent(db_session):
    member = _comprador(db_session)
    qualification = get_or_create_qualification(db_session, member)
    _fill(db_session, qualification)

    set_consent(db_session, qualification, False)

    assert qualification.consent == ConsentState.RECUSADO
    assert active_deal(db_session, member.id) is None


def test_no_deal_while_an_essential_field_is_missing(db_session):
    member = _comprador(db_session)
    qualification = get_or_create_qualification(db_session, member)
    _fill(db_session, qualification, keys=("localizacao", "tipo_piscina"))

    qualification.consent = ConsentState.CONCEDIDO
    assert open_deal_if_qualified(db_session, qualification) is None
    assert db_session.query(Deal).count() == 0


def test_opening_a_deal_twice_does_not_duplicate_it(db_session):
    member = _comprador(db_session)
    qualification = get_or_create_qualification(db_session, member)
    _fill(db_session, qualification)
    set_consent(db_session, qualification, True)

    assert open_deal_if_qualified(db_session, qualification) is None
    set_consent(db_session, qualification, True)

    assert db_session.query(Deal).filter_by(member_id=member.id).count() == 1


def test_marking_a_deal_as_lost_needs_a_reason_and_is_recorded(db_session):
    member = _comprador(db_session)
    qualification = get_or_create_qualification(db_session, member)
    _fill(db_session, qualification)
    set_consent(db_session, qualification, True)
    deal = active_deal(db_session, member.id)

    with pytest.raises(ValueError):
        mark_lost(db_session, deal, reason="   ", actor="admin:equipe@piscinow.com.br")
    assert deal.status == DealStatus.QUALIFIED

    mark_lost(db_session, deal, reason="Sem retorno após três contatos", actor="admin:equipe@piscinow.com.br")

    assert deal.status == DealStatus.LOST
    assert deal.lost_reason == "Sem retorno após três contatos"
    assert active_deal(db_session, member.id) is None
    last = db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="status_changed").one()
    assert (last.from_status, last.to_status) == ("qualified", "lost")
    assert last.note == "Sem retorno após três contatos"


def test_a_closed_deal_cannot_be_closed_again(db_session):
    member = _comprador(db_session)
    qualification = get_or_create_qualification(db_session, member)
    _fill(db_session, qualification)
    set_consent(db_session, qualification, True)
    deal = active_deal(db_session, member.id)
    mark_lost(db_session, deal, reason="Desistiu", actor="admin:x")

    with pytest.raises(ValueError):
        mark_lost(db_session, deal, reason="Outra vez", actor="admin:x")


def test_a_lost_deal_is_not_reopened_just_because_the_buyer_edits_the_briefing(db_session):
    member = _comprador(db_session)
    qualification = get_or_create_qualification(db_session, member)
    _fill(db_session, qualification)
    set_consent(db_session, qualification, True)
    mark_lost(db_session, active_deal(db_session, member.id), reason="Desistiu", actor="admin:x")

    set_field(db_session, qualification, "prazo", "sem_prazo", source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)

    assert active_deal(db_session, member.id) is None
    assert db_session.query(Deal).filter_by(member_id=member.id).count() == 1
