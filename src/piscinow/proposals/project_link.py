from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.payment import Payment, PaymentAllocation, PaymentStage
from piscinow.models.project import Project, ProjectStatus
from piscinow.models.proposal import Proposal
from piscinow.models.qualification import Deal
from piscinow.qualification.deals import record_event

MAX_PAYMENT_AMOUNT = Decimal("99999999.99")


class ScheduleError(ValueError):
    """The schedule cannot be built as typed. The message is for the team member."""


def link_accepted_proposal(db: Session, deal: Deal, proposal: Proposal) -> Project | None:
    """The accepted proposal becomes the buyer's project, confirmed and ready for the payment schedule.

    A project of the old path that already has a payment is never touched: money may already have moved.
    """
    project = db.scalar(select(Project).where(Project.member_id == deal.member_id))
    if project is not None and db.scalar(select(Payment.id).where(Payment.project_id == project.id)) is not None:
        record_event(
            db, deal, "project_not_linked", actor="sistema",
            note="O comprador já tinha um projeto com pagamento criado; a equipe precisa decidir o que fazer.",
        )
        return None
    if project is None:
        project = Project(member_id=deal.member_id)
        db.add(project)
    project.proposal_id = proposal.id
    project.product_id = next((item.product_id for item in proposal.items if item.product_id), None)
    project.status = ProjectStatus.CONFIRMADO
    db.flush()
    record_event(db, deal, "project_confirmed", actor="sistema", note=f"Projeto confirmado pela proposta v{proposal.version}")
    return project


def build_schedule_from_proposal(db: Session, project: Project, amounts: dict) -> Payment:
    """Split the accepted total into the four payment phases, every phase paid to the proposal's store."""
    if project.proposal_id is None or project.status != ProjectStatus.CONFIRMADO:
        raise ScheduleError("Este projeto não veio de uma proposta aceita.")
    if db.scalar(select(Payment.id).where(Payment.project_id == project.id)) is not None:
        raise ScheduleError("Este projeto já tem um pagamento.")
    proposal = db.get(Proposal, project.proposal_id)

    values = {stage: Decimal(amounts.get(stage, Decimal("0"))) for stage in PaymentStage}
    if any(value < 0 for value in values.values()):
        raise ScheduleError("Nenhuma fase pode ter valor negativo.")
    if any(value.as_tuple().exponent < -2 for value in values.values()):
        raise ScheduleError("Use no máximo duas casas decimais.")
    total = sum(values.values(), Decimal("0"))
    if total != proposal.total:
        raise ScheduleError(
            f"A soma das fases precisa ser igual ao total aceito (R$ {proposal.total}); hoje soma R$ {total}."
        )
    if total > MAX_PAYMENT_AMOUNT:
        raise ScheduleError("O total ultrapassa o limite permitido para um pagamento.")

    payment = Payment(project_id=project.id, total_amount=total)
    db.add(payment)
    db.flush()
    for stage, value in values.items():
        if value > 0:
            db.add(PaymentAllocation(
                payment_id=payment.id, stage=stage, amount=value,
                recipient_member_id=proposal.partner_member_id, proposal_id=proposal.id,
            ))
    db.flush()
    return payment
