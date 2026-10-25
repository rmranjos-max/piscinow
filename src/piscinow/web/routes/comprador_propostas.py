import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.comprador_auth import require_comprador
from piscinow.matching.inbox import decision_is_visible
from piscinow.models.matching import MatchingDecision, PartnerResponse
from piscinow.models.member import Member
from piscinow.models.proposal import DealMessage, FeasibilityCheck, MessageAuthor, Proposal
from piscinow.models.qualification import Deal, DealStatus
from piscinow.proposals.rules import acceptance_blocker, caveats, is_expired
from piscinow.proposals.service import (
    NEGOTIABLE, ProposalError, accept_proposal, brl, post_message, reject_proposal,
)
from piscinow.qualification.deals import active_deal
from piscinow.web.deps import get_db

router = APIRouter(prefix="/comprador/propostas")

STATUS_LABELS = {
    "enviada": "Em aberto", "substituida": "Substituída por versão mais nova", "recusada": "Recusada por você",
    "aceita": "Aceita", "encerrada": "Encerrada (você escolheu outra loja)",
}
FEASIBILITY_LABELS = {
    "pending": "Pendente", "conditionally_approved": "Aprovada com ressalvas", "approved": "Aprovada", "rejected": "Reprovada",
}


def _current_deal(db: Session, comprador: Member) -> Deal | None:
    return active_deal(db, comprador.id)


def _uuid_or_404(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise HTTPException(status_code=404)


def _own_proposal(db: Session, proposal_id: str, comprador: Member) -> Proposal:
    proposal = db.get(Proposal, _uuid_or_404(proposal_id))
    if proposal is None or db.get(Deal, proposal.deal_id).member_id != comprador.id:
        raise HTTPException(status_code=404)
    return proposal


def _own_decision(db: Session, decision_id: str, comprador: Member) -> MatchingDecision:
    decision = db.get(MatchingDecision, _uuid_or_404(decision_id))
    if decision is None or db.get(Deal, decision.deal_id).member_id != comprador.id:
        raise HTTPException(status_code=404)
    return decision


def _stores(db: Session, deal: Deal, today: date) -> list[dict]:
    """Stores the buyer can deal with: those that said they will analyze or already proposed."""
    entries = []
    for decision, store in db.execute(
        select(MatchingDecision, Member).join(Member, MatchingDecision.partner_member_id == Member.id)
        .where(MatchingDecision.deal_id == deal.id, MatchingDecision.shared_at.is_not(None)).order_by(Member.name)
    ):
        if not decision_is_visible(db, decision) or decision.response != PartnerResponse.EM_ANALISE:
            continue
        proposals = list(db.scalars(
            select(Proposal).where(Proposal.deal_id == deal.id, Proposal.partner_member_id == store.id)
            .order_by(Proposal.version.desc())
        ))
        messages = list(db.scalars(
            select(DealMessage).where(DealMessage.deal_id == deal.id, DealMessage.partner_member_id == store.id)
            .order_by(DealMessage.created_at)
        ))
        entries.append({
            "decision": decision, "store": store,
            "proposals": [
                {"p": p, "label": STATUS_LABELS[p.status.value],
                 "expired": p.status.value == "enviada" and is_expired(p.valid_until, today),
                 "total": brl(p.total), "items": [(i.description, brl(i.amount)) for i in p.items]}
                for p in proposals
            ],
            "messages": [{"mine": m.author == MessageAuthor.COMPRADOR, "text": m.text, "revision": m.is_revision_request} for m in messages],
        })
    return entries


def _render(request: Request, db: Session, comprador: Member, *, error: str | None = None, status_code: int = 200):
    deal = _current_deal(db, comprador) or db.scalar(
        select(Deal).where(Deal.member_id == comprador.id, Deal.status == DealStatus.ACCEPTED)
    )
    context = {"deal": None, "error": error}
    if deal is not None:
        today = date.today()
        check = db.scalar(select(FeasibilityCheck).where(FeasibilityCheck.deal_id == deal.id))
        status = check.status.value if check else None
        accepted = deal.status == DealStatus.ACCEPTED
        stores = _stores(db, deal, today)
        accepted_store = db.get(Member, deal.assigned_member_id) if accepted else None
        context.update({
            "deal": deal, "accepted": accepted, "accepted_store": accepted_store,
            "stores": [s for s in stores if not accepted or s["store"].id == deal.assigned_member_id],
            "feasibility_label": FEASIBILITY_LABELS.get(status, "Ainda não avaliada"),
            "feasibility_notes": check.notes if check and status == "rejected" else None,
            "caveats": caveats(check.items) if check else [],
            "blocker": acceptance_blocker(status),
            "can_negotiate": deal.status in NEGOTIABLE,
        })
    return request.app.state.templates.TemplateResponse(request, "comprador_propostas.html", context, status_code=status_code)


@router.get("", response_class=HTMLResponse)
async def propostas(request: Request, db: Session = Depends(get_db), comprador: Member = Depends(require_comprador)):
    return _render(request, db, comprador)


@router.post("/{proposal_id}/aceitar")
async def aceitar(
    request: Request,
    proposal_id: str,
    confirmo: str | None = Form(None),
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    proposal = _own_proposal(db, proposal_id, comprador)
    if confirmo is None:
        return _render(request, db, comprador, error="Confirme que leu os termos desta versão para aceitar.", status_code=400)
    try:
        accept_proposal(db, proposal, comprador)
    except ProposalError as exc:
        return _render(request, db, comprador, error=exc.errors[0], status_code=400)
    return RedirectResponse(url="/comprador/propostas", status_code=303)


@router.post("/{proposal_id}/recusar")
async def recusar(
    request: Request,
    proposal_id: str,
    motivo: str = Form(""),
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    proposal = _own_proposal(db, proposal_id, comprador)
    try:
        reject_proposal(db, proposal, comprador, reason=motivo)
    except ProposalError as exc:
        return _render(request, db, comprador, error=exc.errors[0], status_code=400)
    return RedirectResponse(url="/comprador/propostas", status_code=303)


def _message(request: Request, db: Session, comprador: Member, decision_id: str, texto: str, revision: bool):
    decision = _own_decision(db, decision_id, comprador)
    try:
        post_message(db, decision, author=MessageAuthor.COMPRADOR, member=comprador, text=texto, revision=revision)
    except ProposalError as exc:
        return _render(request, db, comprador, error=exc.errors[0], status_code=400)
    return RedirectResponse(url="/comprador/propostas", status_code=303)


@router.post("/loja/{decision_id}/revisao")
async def pedir_revisao(
    request: Request, decision_id: str, texto: str = Form(""),
    db: Session = Depends(get_db), comprador: Member = Depends(require_comprador),
):
    return _message(request, db, comprador, decision_id, texto, True)


@router.post("/loja/{decision_id}/mensagem")
async def mensagem(
    request: Request, decision_id: str, texto: str = Form(""),
    db: Session = Depends(get_db), comprador: Member = Depends(require_comprador),
):
    return _message(request, db, comprador, decision_id, texto, False)
