from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.qualification import (
    ConsentState,
    Deal,
    DealEvent,
    DealStatus,
    LeadQualification,
)
from piscinow.qualification.flow import is_qualified

CLOSED = (DealStatus.LOST, DealStatus.CANCELLED)

STATUS_LABELS = {
    DealStatus.NEW: "Nova",
    DealStatus.QUALIFIED: "Qualificada",
    DealStatus.MATCHED: "Lojas indicadas",
    DealStatus.PARTNER_REVIEW: "Em análise pela loja",
    DealStatus.PROPOSAL_SENT: "Proposta enviada",
    DealStatus.NEGOTIATING: "Em negociação",
    DealStatus.ACCEPTED: "Aceita",
    DealStatus.LOST: "Perdida",
    DealStatus.CANCELLED: "Cancelada",
}


def active_deal(db: Session, member_id) -> Deal | None:
    return db.scalar(select(Deal).where(Deal.member_id == member_id, Deal.status.notin_(CLOSED)))


def record_event(
    db: Session, deal: Deal, kind: str, *, actor: str,
    from_status: str | None = None, to_status: str | None = None, note: str | None = None,
) -> DealEvent:
    event = DealEvent(
        deal_id=deal.id, kind=kind, from_status=from_status, to_status=to_status,
        note=note, actor=actor, created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.flush()
    return event


def open_deal_if_qualified(db: Session, qualification: LeadQualification) -> Deal | None:
    """Create the buyer's deal once, when the essentials and the consent are in.

    A deal the team has lost is never silently reopened because the buyer edited the briefing
    afterwards. One cancelled because the buyer withdrew the authorization reopens when they authorize again.
    """
    consent = qualification.consent
    if not is_qualified(qualification.values(), consent.value if isinstance(consent, ConsentState) else consent):
        return None
    # Only a deal the team lost blocks a new one; a cancelled one (authorization withdrawn) may reopen.
    blocked = db.scalar(
        select(Deal.id).where(
            Deal.qualification_id == qualification.id,
            Deal.status.notin_((DealStatus.CANCELLED,)),
        ).limit(1)
    )
    if blocked is not None:
        return None
    deal = Deal(member_id=qualification.member_id, qualification_id=qualification.id, status=DealStatus.QUALIFIED)
    db.add(deal)
    db.flush()
    record_event(db, deal, "created", actor="sistema", to_status=DealStatus.QUALIFIED.value)
    return deal


def mark_lost(db: Session, deal: Deal, *, reason: str, actor: str) -> None:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("O motivo da perda é obrigatório.")
    if deal.status in CLOSED:
        raise ValueError("Esta oportunidade já está encerrada.")
    previous = deal.status
    deal.status = DealStatus.LOST
    deal.lost_reason = reason[:500]
    record_event(
        db, deal, "status_changed", actor=actor,
        from_status=previous.value, to_status=DealStatus.LOST.value, note=reason[:500],
    )


def cancel_for_withdrawn_consent(db: Session, qualification: LeadQualification) -> None:
    """The buyer took the authorization back: stores must stop seeing the briefing right away."""
    deal = active_deal(db, qualification.member_id)
    if deal is None or deal.status == DealStatus.ACCEPTED:
        # An accepted proposal already released the contact; it is no longer a briefing-sharing matter.
        return
    previous = deal.status
    deal.status = DealStatus.CANCELLED
    record_event(
        db, deal, "status_changed", actor=f"comprador:{qualification.member_id}",
        from_status=previous.value, to_status=DealStatus.CANCELLED.value,
        note="O comprador retirou a autorização de compartilhamento.",
    )
