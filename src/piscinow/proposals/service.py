from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.matching.inbox import decision_is_visible
from piscinow.models.matching import MatchingDecision, PartnerResponse
from piscinow.models.member import Member
from piscinow.models.proposal import (
    DealMessage, FeasibilityCheck, FeasibilityStatus, MessageAuthor, Proposal, ProposalItem, ProposalStatus,
)
from piscinow.models.qualification import Deal, DealStatus
from piscinow.proposals.rules import acceptance_blocker, is_expired, total_of, validate_feasibility, validate_proposal
from piscinow.qualification.deals import record_event

NEGOTIABLE = (DealStatus.PARTNER_REVIEW, DealStatus.PROPOSAL_SENT, DealStatus.NEGOTIATING)
MAX_MESSAGE_CHARS = 1000
MAX_ITEM_DESCRIPTION = 300


class ProposalError(Exception):
    def __init__(self, *errors: str):
        super().__init__(errors[0] if errors else "")
        self.errors = list(errors)


def brl(amount: Decimal) -> str:
    return "R$ " + f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _deal(db: Session, decision: MatchingDecision) -> Deal:
    return db.get(Deal, decision.deal_id)


def _store(db: Session, decision: MatchingDecision) -> Member:
    return db.get(Member, decision.partner_member_id)


def submit_proposal(
    db: Session, decision: MatchingDecision, *, items: list[tuple[str, Decimal]], scope: str,
    lead_time_days: int, valid_until: date, exclusions: str = "", today: date | None = None,
) -> Proposal:
    today = today or date.today()
    deal = _deal(db, decision)
    if not decision_is_visible(db, decision) or decision.response != PartnerResponse.EM_ANALISE:
        raise ProposalError("Esta oportunidade não está disponível para enviar proposta.")
    if deal.status not in NEGOTIABLE:
        raise ProposalError("Esta oportunidade não aceita mais propostas.")
    errors = validate_proposal(
        items=items, scope=scope, lead_time_days=lead_time_days, valid_until=valid_until, today=today
    )
    if any(len((description or "").strip()) > MAX_ITEM_DESCRIPTION for description, _ in items):
        errors.append(f"Cada descrição deve ter no máximo {MAX_ITEM_DESCRIPTION} caracteres.")
    if errors:
        raise ProposalError(*errors)

    previous = list(db.scalars(
        select(Proposal).where(Proposal.deal_id == deal.id, Proposal.partner_member_id == decision.partner_member_id)
    ))
    for old in previous:
        if old.status == ProposalStatus.ENVIADA:
            old.status = ProposalStatus.SUBSTITUIDA
    db.flush()

    store = _store(db, decision)
    proposal = Proposal(
        deal_id=deal.id, partner_member_id=store.id, version=max((p.version for p in previous), default=0) + 1,
        total=total_of(amount for _, amount in items), scope=scope.strip(), lead_time_days=lead_time_days,
        valid_until=valid_until, exclusions=(exclusions or "").strip() or None, created_by=f"loja:{store.id}",
    )
    proposal.items = [
        ProposalItem(position=position, description=description.strip(), amount=amount)
        for position, (description, amount) in enumerate(items, start=1)
    ]
    db.add(proposal)
    db.flush()

    if deal.status == DealStatus.PARTNER_REVIEW:
        previous_status, deal.status = deal.status, DealStatus.PROPOSAL_SENT
        record_event(
            db, deal, "proposal_sent", actor=proposal.created_by, from_status=previous_status.value,
            to_status=deal.status.value, note=f"{store.name} enviou a v{proposal.version} ({brl(proposal.total)})",
        )
    else:
        record_event(
            db, deal, "proposal_sent", actor=proposal.created_by,
            note=f"{store.name} enviou a v{proposal.version} ({brl(proposal.total)})",
        )
    return proposal


def post_message(
    db: Session, decision: MatchingDecision, *, author: MessageAuthor, member: Member, text: str, revision: bool = False
) -> DealMessage:
    deal = _deal(db, decision)
    if not decision_is_visible(db, decision):
        raise ProposalError("Esta conversa não está disponível.")
    if author == MessageAuthor.COMPRADOR and member.id != deal.member_id:
        raise ProposalError("Esta conversa não está disponível.")
    if author == MessageAuthor.LOJA and member.id != decision.partner_member_id:
        raise ProposalError("Esta conversa não está disponível.")
    if revision and author != MessageAuthor.COMPRADOR:
        raise ProposalError("Somente o comprador pode pedir revisão.")
    if revision and deal.status not in NEGOTIABLE:
        raise ProposalError("Esta oportunidade não aceita mais pedidos de revisão.")
    text = (text or "").strip()
    if not text:
        raise ProposalError("Escreva uma mensagem.")
    if len(text) > MAX_MESSAGE_CHARS:
        raise ProposalError(f"A mensagem deve ter no máximo {MAX_MESSAGE_CHARS} caracteres.")

    message = DealMessage(
        deal_id=deal.id, partner_member_id=decision.partner_member_id, author=author, author_member_id=member.id,
        is_revision_request=revision, text=text,
    )
    db.add(message)
    db.flush()
    if revision:
        store = _store(db, decision)
        if deal.status != DealStatus.NEGOTIATING:
            previous, deal.status = deal.status, DealStatus.NEGOTIATING
            record_event(
                db, deal, "revision_requested", actor=f"comprador:{member.id}", from_status=previous.value,
                to_status=deal.status.value, note=f"Revisão pedida a {store.name}",
            )
        else:
            record_event(db, deal, "revision_requested", actor=f"comprador:{member.id}", note=f"Revisão pedida a {store.name}")
    return message


def reject_proposal(db: Session, proposal: Proposal, *, reason: str) -> None:
    if proposal.status != ProposalStatus.ENVIADA:
        raise ProposalError("Esta proposta não está mais em aberto.")
    reason = (reason or "").strip()
    if not reason:
        raise ProposalError("Informe o motivo para recusar.")
    proposal.status = ProposalStatus.RECUSADA
    proposal.decision_reason = reason[:500]
    proposal.decided_at = datetime.now(timezone.utc)
    deal = db.get(Deal, proposal.deal_id)
    store = db.get(Member, proposal.partner_member_id)
    record_event(
        db, deal, "proposal_rejected", actor=f"comprador:{deal.member_id}",
        note=f"Proposta v{proposal.version} de {store.name} recusada: {reason[:200]}",
    )


def feasibility_status_of(db: Session, deal: Deal) -> str | None:
    check = db.scalar(select(FeasibilityCheck).where(FeasibilityCheck.deal_id == deal.id))
    return check.status.value if check else None


def accept_proposal(db: Session, proposal: Proposal, buyer: Member, *, today: date | None = None) -> None:
    today = today or date.today()
    deal = db.get(Deal, proposal.deal_id)
    if buyer.id != deal.member_id:
        raise ProposalError("Esta proposta não está disponível.")
    if deal.status not in NEGOTIABLE or proposal.status != ProposalStatus.ENVIADA:
        raise ProposalError("Esta proposta não está mais em aberto.")
    decision = db.scalar(select(MatchingDecision).where(
        MatchingDecision.deal_id == deal.id, MatchingDecision.partner_member_id == proposal.partner_member_id
    ))
    if decision is None or not decision_is_visible(db, decision):
        raise ProposalError("Esta proposta não está mais disponível.")
    if is_expired(proposal.valid_until, today):
        raise ProposalError("Esta proposta está vencida; peça uma nova versão à loja.")
    blocker = acceptance_blocker(feasibility_status_of(db, deal))
    if blocker:
        raise ProposalError(blocker)

    now = datetime.now(timezone.utc)
    store = db.get(Member, proposal.partner_member_id)
    proposal.status = ProposalStatus.ACEITA
    proposal.decided_at = now
    for other in db.scalars(select(Proposal).where(
        Proposal.deal_id == deal.id, Proposal.id != proposal.id, Proposal.status == ProposalStatus.ENVIADA
    )):
        other.status = ProposalStatus.ENCERRADA
        other.decided_at = now
    db.flush()

    previous, deal.status = deal.status, DealStatus.ACCEPTED
    deal.assigned_member_id = store.id
    record_event(
        db, deal, "proposal_accepted", actor=f"comprador:{buyer.id}", from_status=previous.value,
        to_status=deal.status.value, note=f"{store.name} v{proposal.version} ({brl(proposal.total)})",
    )
    record_event(db, deal, "contact_released", actor="sistema", note=f"Contato liberado para {store.name}")


def save_feasibility(
    db: Session, deal: Deal, *, status: str, items: list[dict], notes: str, actor: str
) -> FeasibilityCheck:
    errors = validate_feasibility(status, items, notes)
    if errors:
        raise ProposalError(*errors)
    check = db.scalar(select(FeasibilityCheck).where(FeasibilityCheck.deal_id == deal.id))
    if check is None:
        check = FeasibilityCheck(deal_id=deal.id)
        db.add(check)
    check.status = FeasibilityStatus(status)
    check.items = [{"key": i["key"], "state": i["state"], "note": (i.get("note") or "").strip()[:300]} for i in items]
    check.notes = (notes or "").strip()[:1000] or None
    check.decided_by = actor
    check.decided_at = datetime.now(timezone.utc)
    db.flush()
    record_event(db, deal, "feasibility", actor=actor, note=f"Viabilidade: {status}")
    return check
