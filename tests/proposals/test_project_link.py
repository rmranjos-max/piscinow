from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStage
from piscinow.models.project import Project, ProjectStatus
from piscinow.models.qualification import DealEvent
from piscinow.proposals.project_link import ScheduleError, build_schedule_from_proposal
from piscinow.proposals.service import accept_proposal
from tests.proposals.test_service import _approve_feasibility, _catalog_product, _loja, _send, _setup


def _accepted(db_session, items=None):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    proposal = _send(db_session, decisions[loja.id], **({"items": items} if items else {}))
    return buyer, deal, loja, proposal


def _project(db_session, buyer):
    return db_session.query(Project).filter_by(member_id=buyer.id).one()


def test_accepting_creates_a_confirmed_project_that_points_to_the_proposal(db_session):
    buyer, deal, _, proposal = _accepted(db_session)

    accept_proposal(db_session, proposal, buyer)

    project = _project(db_session, buyer)
    assert (project.proposal_id, project.status) == (proposal.id, ProjectStatus.CONFIRMADO)
    assert db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="project_confirmed").count() == 1


def test_the_project_takes_the_catalog_product_of_the_first_linked_item(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    product = _catalog_product(db_session, loja)
    proposal = _send(db_session, decisions[loja.id], items=[("Instalação", Decimal("3000.00"), None), ("", None, str(product.id))])

    accept_proposal(db_session, proposal, buyer)

    assert _project(db_session, buyer).product_id == product.id


def test_an_existing_draft_project_is_reused_instead_of_duplicated(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    draft = Project(member_id=buyer.id)
    db_session.add(draft)
    db_session.flush()
    _approve_feasibility(db_session, deal)
    proposal = _send(db_session, decisions[loja.id])

    accept_proposal(db_session, proposal, buyer)

    assert db_session.query(Project).filter_by(member_id=buyer.id).count() == 1
    assert (draft.proposal_id, draft.status) == (proposal.id, ProjectStatus.CONFIRMADO)


def test_a_project_that_already_has_a_payment_is_never_changed_by_an_acceptance(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    legacy = Project(member_id=buyer.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(legacy)
    db_session.flush()
    db_session.add(Payment(project_id=legacy.id, total_amount=Decimal("5000.00")))
    db_session.flush()
    _approve_feasibility(db_session, deal)
    proposal = _send(db_session, decisions[loja.id])

    accept_proposal(db_session, proposal, buyer)

    assert legacy.proposal_id is None
    event = db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="project_not_linked").one()
    assert "pagamento" in event.note


def _phases(**amounts):
    return {stage: Decimal(amounts.get(stage.value, "0")) for stage in PaymentStage}


def test_the_schedule_splits_the_accepted_total_into_phases_all_paid_to_the_store(db_session):
    buyer, _, loja, proposal = _accepted(db_session)
    accept_proposal(db_session, proposal, buyer)
    project = _project(db_session, buyer)

    payment = build_schedule_from_proposal(
        db_session, project, _phases(terraplanagem="3000.00", estrutura="12000.00", revestimento="4000.00", acabamento="2000.00")
    )

    assert payment.total_amount == proposal.total == Decimal("21000.00")
    allocations = db_session.query(PaymentAllocation).filter_by(payment_id=payment.id).all()
    assert {a.stage for a in allocations} == set(PaymentStage)
    assert {a.recipient_member_id for a in allocations} == {loja.id}
    assert {a.proposal_id for a in allocations} == {proposal.id}
    assert all(a.status == AllocationStatus.RETIDO and a.product_id is None and a.service_id is None for a in allocations)


def test_a_phase_with_zero_is_simply_left_out(db_session):
    buyer, _, _, proposal = _accepted(db_session)
    accept_proposal(db_session, proposal, buyer)

    payment = build_schedule_from_proposal(db_session, _project(db_session, buyer), _phases(estrutura="21000.00"))

    assert [a.stage for a in db_session.query(PaymentAllocation).filter_by(payment_id=payment.id)] == [PaymentStage.ESTRUTURA]


@pytest.mark.parametrize("amounts,message", [
    (dict(estrutura="20000.00"), "igual ao total"),
    (dict(estrutura="22000.00", acabamento="-1000.00"), "negativo"),
    (dict(), "igual ao total"),
])
def test_a_schedule_that_does_not_add_up_or_has_negative_values_is_refused(db_session, amounts, message):
    buyer, _, _, proposal = _accepted(db_session)
    accept_proposal(db_session, proposal, buyer)
    project = _project(db_session, buyer)

    with pytest.raises(ScheduleError) as raised:
        build_schedule_from_proposal(db_session, project, _phases(**amounts))

    assert message in str(raised.value)
    assert db_session.query(Payment).count() == 0


def test_a_project_gets_only_one_schedule(db_session):
    buyer, _, _, proposal = _accepted(db_session)
    accept_proposal(db_session, proposal, buyer)
    project = _project(db_session, buyer)
    build_schedule_from_proposal(db_session, project, _phases(estrutura="21000.00"))

    with pytest.raises(ScheduleError):
        build_schedule_from_proposal(db_session, project, _phases(estrutura="21000.00"))


def test_a_project_without_an_accepted_proposal_cannot_use_this_schedule(db_session):
    buyer, _, _, _ = _accepted(db_session)
    project = Project(member_id=buyer.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()

    with pytest.raises(ScheduleError):
        build_schedule_from_proposal(db_session, project, _phases(estrutura="21000.00"))


def test_the_database_requires_exactly_one_origin_for_each_allocation(db_session):
    buyer, _, loja, proposal = _accepted(db_session)
    accept_proposal(db_session, proposal, buyer)
    payment = build_schedule_from_proposal(db_session, _project(db_session, buyer), _phases(estrutura="21000.00"))

    db_session.add(PaymentAllocation(
        payment_id=payment.id, stage=PaymentStage.ACABAMENTO, recipient_member_id=loja.id, amount=Decimal("1.00"),
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()
