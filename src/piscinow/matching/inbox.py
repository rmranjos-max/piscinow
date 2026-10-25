import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.matching.rules import is_effective
from piscinow.models.matching import MatchingDecision, PartnerResponse
from piscinow.models.member import Member
from piscinow.models.qualification import ConsentState, Deal, DealStatus, LeadQualification
from piscinow.qualification.deals import CLOSED, record_event
from piscinow.qualification.projection import partner_briefing


def _visible(decision: MatchingDecision, deal: Deal, qualification: LeadQualification) -> bool:
    """A store sees an opportunity only while it was shared with it and the buyer still allows it."""
    return (
        decision.shared_at is not None
        and is_effective(decision.eligible, decision.override.value)
        and deal.status not in CLOSED
        and qualification.consent == ConsentState.CONCEDIDO
    )


def inbox_for_partner(db: Session, partner_id) -> list[dict]:
    rows = db.execute(
        select(MatchingDecision, Deal, LeadQualification)
        .join(Deal, MatchingDecision.deal_id == Deal.id)
        .join(LeadQualification, Deal.qualification_id == LeadQualification.id)
        .where(MatchingDecision.partner_member_id == partner_id, MatchingDecision.shared_at.is_not(None))
        .order_by(MatchingDecision.shared_at.desc())
    )
    items = []
    for decision, deal, qualification in rows:
        if not _visible(decision, deal, qualification):
            continue
        # Built from the field catalog only: no name, e-mail, phone or id can reach the store.
        items.append({
            "decision": decision,
            "briefing": partner_briefing(deal.member_id, qualification.values()),
            "response": decision.response.value,
        })
    return items


def visible_decision(db: Session, decision_id: str, partner_id) -> MatchingDecision | None:
    """The decision, only if it belongs to this store and is still visible to it."""
    try:
        decision = db.get(MatchingDecision, uuid.UUID(decision_id))
    except ValueError:
        return None
    if decision is None or decision.partner_member_id != partner_id:
        return None
    deal = db.get(Deal, decision.deal_id)
    qualification = db.get(LeadQualification, deal.qualification_id)
    return decision if _visible(decision, deal, qualification) else None


def respond(db: Session, decision: MatchingDecision, *, answer: str, reason: str) -> None:
    try:
        response = PartnerResponse(answer)
    except ValueError:
        raise ValueError("Resposta inválida.")
    if response == PartnerResponse.PENDENTE:
        raise ValueError("Resposta inválida.")
    if decision.response == PartnerResponse.RECUSADA:
        raise ValueError("Esta oportunidade já foi recusada.")
    reason = (reason or "").strip()
    if response == PartnerResponse.RECUSADA and not reason:
        raise ValueError("Informe o motivo para recusar.")
    decision.response = response
    decision.response_reason = reason[:500] if response == PartnerResponse.RECUSADA else None
    decision.responded_at = datetime.now(timezone.utc)
    deal = db.get(Deal, decision.deal_id)
    store = db.get(Member, decision.partner_member_id)
    label = "vai analisar" if response == PartnerResponse.EM_ANALISE else f"recusou ({decision.response_reason})"
    record_event(db, deal, "partner_response", actor=f"loja:{store.id}", note=f"{store.name} {label}")
