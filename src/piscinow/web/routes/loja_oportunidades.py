from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.loja_auth import require_loja
from piscinow.matching.inbox import inbox_for_partner, respond, visible_decision
from piscinow.models.matching import PartnerResponse
from piscinow.models.member import Member
from piscinow.models.proposal import DealMessage, MessageAuthor, Proposal
from piscinow.models.qualification import Deal
from piscinow.proposals.forms import parse_proposal_form
from piscinow.proposals.rules import is_expired
from piscinow.proposals.service import NEGOTIABLE, ProposalError, brl, post_message, submit_proposal
from piscinow.web.deps import get_db

router = APIRouter(prefix="/loja/oportunidades")

RESPONSE_LABELS = {"pendente": "Aguardando a sua resposta", "em_analise": "Você vai analisar", "recusada": "Você recusou"}
PROPOSAL_LABELS = {
    "enviada": "Em aberto", "substituida": "Substituída", "recusada": "Recusada pelo comprador",
    "aceita": "Aceita", "encerrada": "Encerrada (outra loja foi escolhida)",
}
FORM_ROWS = 6


def _enrich(db: Session, item: dict, today: date) -> dict:
    decision = item["decision"]
    deal = db.get(Deal, item["deal_id"])
    proposals = list(db.scalars(
        select(Proposal).where(Proposal.deal_id == deal.id, Proposal.partner_member_id == decision.partner_member_id)
        .order_by(Proposal.version.desc())
    ))
    messages = list(db.scalars(
        select(DealMessage).where(DealMessage.deal_id == deal.id, DealMessage.partner_member_id == decision.partner_member_id)
        .order_by(DealMessage.created_at)
    ))
    return {
        **item,
        "response_label": RESPONSE_LABELS[item["response"]],
        "can_propose": decision.response == PartnerResponse.EM_ANALISE and deal.status in NEGOTIABLE,
        "proposals": [
            {"p": p, "label": PROPOSAL_LABELS[p.status.value], "expired": p.status.value == "enviada" and is_expired(p.valid_until, today),
             "total": brl(p.total), "items": [(i.description, brl(i.amount)) for i in p.items]}
            for p in proposals
        ],
        "messages": [{"mine": m.author == MessageAuthor.LOJA, "text": m.text, "revision": m.is_revision_request, "at": m.created_at} for m in messages],
        "rows": range(FORM_ROWS),
        "errors": [],
        "form": {},
    }


def _render(
    request: Request, db: Session, loja: Member, *, error: str | None = None, status_code: int = 200,
    failed_id: str | None = None, errors: list[str] | None = None, form: dict | None = None,
):
    today = date.today()
    items = [_enrich(db, item, today) for item in inbox_for_partner(db, loja.id)]
    for item in items:
        if failed_id and str(item["decision"].id) == failed_id:
            item["errors"], item["form"] = errors or [], form or {}
    return request.app.state.templates.TemplateResponse(
        request, "loja_oportunidades.html", {"items": items, "error": error}, status_code=status_code
    )


def _decision_or_404(db: Session, decision_id: str, loja: Member):
    decision = visible_decision(db, decision_id, loja.id)
    if decision is None:
        raise HTTPException(status_code=404)
    return decision


@router.get("", response_class=HTMLResponse)
async def caixa_de_entrada(
    request: Request, db: Session = Depends(get_db), loja: Member = Depends(require_loja)
):
    return _render(request, db, loja)


@router.post("/{decision_id}/resposta")
async def responder(
    request: Request,
    decision_id: str,
    decisao: str = Form(...),
    motivo: str = Form(""),
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    decision = _decision_or_404(db, decision_id, loja)
    try:
        respond(db, decision, answer=decisao, reason=motivo)
    except ValueError as exc:
        return _render(request, db, loja, error=str(exc), status_code=400)
    return RedirectResponse(url="/loja/oportunidades", status_code=303)


@router.post("/{decision_id}/proposta")
async def enviar_proposta(
    request: Request,
    decision_id: str,
    item_desc: list[str] = Form([]),
    item_amount: list[str] = Form([]),
    scope: str = Form(""),
    lead_time_days: str = Form(""),
    valid_until: str = Form(""),
    exclusions: str = Form(""),
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    decision = _decision_or_404(db, decision_id, loja)
    values, errors = parse_proposal_form(item_desc, item_amount, scope, lead_time_days, valid_until, exclusions)
    if values is not None:
        try:
            submit_proposal(db, decision, **values)
        except ProposalError as exc:
            errors = exc.errors
    if errors:
        form = {
            "rows": list(zip(item_desc + [""] * FORM_ROWS, item_amount + [""] * FORM_ROWS))[:FORM_ROWS],
            "scope": scope, "lead_time_days": lead_time_days, "valid_until": valid_until, "exclusions": exclusions,
        }
        return _render(request, db, loja, status_code=400, failed_id=decision_id, errors=errors, form=form)
    return RedirectResponse(url="/loja/oportunidades", status_code=303)


@router.post("/{decision_id}/mensagem")
async def enviar_mensagem(
    request: Request,
    decision_id: str,
    texto: str = Form(""),
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    decision = _decision_or_404(db, decision_id, loja)
    try:
        post_message(db, decision, author=MessageAuthor.LOJA, member=loja, text=texto)
    except ProposalError as exc:
        return _render(request, db, loja, error=exc.errors[0], status_code=400)
    return RedirectResponse(url="/loja/oportunidades", status_code=303)
