import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.auth import require_admin
from piscinow.matching.rules import is_effective
from piscinow.matching.service import EDITABLE, run_matching, set_override, share_with_partners
from piscinow.models.admin import AdminUser
from piscinow.models.conversation import MessageRole
from piscinow.models.matching import MatchingDecision, MatchOverride
from piscinow.models.member import Member
from piscinow.models.qualification import (
    Deal,
    DealEvent,
    DealStatus,
    FieldSource,
    LeadQualification,
)
from piscinow.qualification.deals import CLOSED, STATUS_LABELS, mark_lost, record_event
from piscinow.qualification.fields import FIELDS, label_for
from piscinow.qualification.service import conversation_of, known_fields, refresh_status, set_field
from piscinow.web.deps import get_db

router = APIRouter(prefix="/admin/oportunidades")

# "ativas" is the default view; the others filter by one state.
FILTERS = {"ativas": "Ativas", "todas": "Todas", **{status.value: STATUS_LABELS[status] for status in DealStatus}}
STATUS_TONE = {
    DealStatus.LOST: "amber", DealStatus.CANCELLED: "amber", DealStatus.ACCEPTED: "green",
}


def _summary(values: dict) -> str:
    parts = [label_for(key, values[key]) for key in ("tipo_piscina", "localizacao", "prazo") if key in values]
    return " · ".join(parts) if parts else "Briefing ainda vazio"


def _qualification_or_404(db: Session, qualification_id: str) -> LeadQualification:
    try:
        parsed = uuid.UUID(qualification_id)
    except ValueError:
        raise HTTPException(status_code=404)
    qualification = db.get(LeadQualification, parsed)
    if qualification is None:
        raise HTTPException(status_code=404)
    return qualification


@router.get("", response_class=HTMLResponse)
async def lista(
    request: Request,
    estado: str = "ativas",
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    if estado not in FILTERS:
        estado = "ativas"
    query = select(Deal, LeadQualification, Member).join(
        LeadQualification, Deal.qualification_id == LeadQualification.id
    ).join(Member, Deal.member_id == Member.id)
    if estado == "ativas":
        query = query.where(Deal.status.notin_(CLOSED))
    elif estado != "todas":
        query = query.where(Deal.status == DealStatus(estado))
    rows = [
        {
            "deal": deal, "buyer": member, "qualification": qualification,
            "status": STATUS_LABELS[deal.status], "tone": STATUS_TONE.get(deal.status, ""),
            "summary": _summary(qualification.values()),
        }
        for deal, qualification, member in db.execute(query.order_by(Deal.number.desc()))
    ]

    # Buyers the assistant could not finish with, and who have no opportunity yet.
    with_deal = select(Deal.qualification_id)
    waiting = [
        {"qualification": q, "buyer": member, "summary": _summary(q.values())}
        for q, member in db.execute(
            select(LeadQualification, Member)
            .join(Member, LeadQualification.member_id == Member.id)
            .where(LeadQualification.attention_at.is_not(None), LeadQualification.id.notin_(with_deal))
            .order_by(LeadQualification.attention_at)
        )
    ]
    return request.app.state.templates.TemplateResponse(
        request,
        "admin_oportunidades.html",
        {"rows": rows, "waiting": waiting, "filters": FILTERS, "estado": estado},
    )


def _event_title(event: DealEvent) -> str:
    if event.kind == "created":
        return "Oportunidade criada"
    if event.from_status and event.to_status:
        return f"{_status_label(event.from_status)} → {_status_label(event.to_status)}"
    return event.kind


def _status_label(value: str) -> str:
    try:
        return STATUS_LABELS[DealStatus(value)]
    except ValueError:
        return value


def _detail_context(db: Session, qualification: LeadQualification, error: str | None = None) -> dict:
    buyer = db.get(Member, qualification.member_id)
    deal = db.scalar(
        select(Deal).where(Deal.qualification_id == qualification.id).order_by(Deal.number.desc()).limit(1)
    )
    events = []
    if deal is not None:
        events = [
            {"title": _event_title(e),
             "detail": f"{e.created_at:%d/%m/%Y %H:%M} · {e.actor}" + (f" · {e.note}" if e.note else "")}
            for e in db.scalars(select(DealEvent).where(DealEvent.deal_id == deal.id).order_by(DealEvent.created_at))
        ]
    conversation = conversation_of(db, qualification)
    return {
        "qualification": qualification,
        "buyer": buyer,
        "deal": deal,
        "deal_status": STATUS_LABELS[deal.status] if deal else None,
        "closed": deal is not None and deal.status in CLOSED,
        "briefing": known_fields(qualification),
        "events": events,
        "transcript": [
            {"from_agent": m.role == MessageRole.AGENT, "text": m.content} for m in conversation.messages
        ],
        "field_keys": {key: definition.label for key, definition in FIELDS.items()},
        "matching": _matching_rows(db, deal) if deal is not None and not closed_deal(deal) else None,
        "can_edit_matching": deal is not None and deal.status in EDITABLE,
        "can_share": deal is not None and deal.status == DealStatus.MATCHED,
        "error": error,
    }


def closed_deal(deal: Deal) -> bool:
    return deal.status in CLOSED


RESPONSE_LABELS = {"pendente": "Aguardando resposta", "em_analise": "Vai analisar", "recusada": "Não tem interesse"}
OVERRIDE_LABELS = {"nenhum": "", "incluida": "Incluída pela equipe", "excluida": "Excluída pela equipe"}


def _matching_rows(db: Session, deal: Deal) -> list[dict]:
    rows = []
    for decision, store in db.execute(
        select(MatchingDecision, Member)
        .join(Member, MatchingDecision.partner_member_id == Member.id)
        .where(MatchingDecision.deal_id == deal.id)
        .order_by(Member.name)
    ):
        rows.append({
            "decision": decision, "store": store,
            "effective": is_effective(decision.eligible, decision.override.value),
            "override_label": OVERRIDE_LABELS[decision.override.value],
            "response_label": RESPONSE_LABELS[decision.response.value] if decision.shared_at else None,
        })
    rows.sort(key=lambda r: (not r["effective"], r["store"].name))
    return rows


@router.get("/{qualification_id}", response_class=HTMLResponse)
async def detalhe(
    request: Request,
    qualification_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    qualification = _qualification_or_404(db, qualification_id)
    return request.app.state.templates.TemplateResponse(
        request, "admin_oportunidade_detalhe.html", _detail_context(db, qualification)
    )


@router.post("/{qualification_id}/campo")
async def preencher_campo(
    qualification_id: str,
    key: str = Form(...),
    value: str = Form(...),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    qualification = _qualification_or_404(db, qualification_id)
    if key not in FIELDS:
        raise HTTPException(status_code=404)
    if not set_field(db, qualification, key, value, source=FieldSource.ADMIN, actor=f"admin:{admin.email}"):
        raise HTTPException(status_code=400, detail="Valor inválido para este campo.")
    refresh_status(db, qualification)
    return RedirectResponse(url=f"/admin/oportunidades/{qualification.id}", status_code=303)


@router.post("/{qualification_id}/atencao/resolver")
async def resolver_atencao(
    qualification_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    qualification = _qualification_or_404(db, qualification_id)
    qualification.attention_note = None
    qualification.attention_at = None
    return RedirectResponse(url=f"/admin/oportunidades/{qualification.id}", status_code=303)


@router.post("/{qualification_id}/perdida")
async def marcar_perdida(
    request: Request,
    qualification_id: str,
    motivo: str = Form(""),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    qualification = _qualification_or_404(db, qualification_id)
    deal = db.scalar(
        select(Deal).where(Deal.qualification_id == qualification.id, Deal.status.notin_(CLOSED))
    )
    if deal is None:
        raise HTTPException(status_code=404, detail="Não há oportunidade ativa para encerrar.")
    try:
        mark_lost(db, deal, reason=motivo, actor=f"admin:{admin.email}")
    except ValueError as exc:
        return request.app.state.templates.TemplateResponse(
            request, "admin_oportunidade_detalhe.html",
            _detail_context(db, qualification, error=str(exc)), status_code=400,
        )
    return RedirectResponse(url=f"/admin/oportunidades/{qualification.id}", status_code=303)



def _active_deal_or_404(db: Session, qualification: LeadQualification) -> Deal:
    deal = db.scalar(select(Deal).where(Deal.qualification_id == qualification.id, Deal.status.notin_(CLOSED)))
    if deal is None:
        raise HTTPException(status_code=404, detail="Não há oportunidade ativa.")
    return deal


def _detail_error(request: Request, db: Session, qualification: LeadQualification, error: str):
    return request.app.state.templates.TemplateResponse(
        request, "admin_oportunidade_detalhe.html", _detail_context(db, qualification, error=error), status_code=400
    )


@router.post("/{qualification_id}/matching/executar")
async def executar_matching(
    request: Request,
    qualification_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    qualification = _qualification_or_404(db, qualification_id)
    deal = _active_deal_or_404(db, qualification)
    try:
        run_matching(db, deal, actor=f"admin:{admin.email}")
    except ValueError as exc:
        return _detail_error(request, db, qualification, str(exc))
    return RedirectResponse(url=f"/admin/oportunidades/{qualification.id}#matching", status_code=303)


@router.post("/{qualification_id}/matching/encaminhar")
async def encaminhar(
    request: Request,
    qualification_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    qualification = _qualification_or_404(db, qualification_id)
    deal = _active_deal_or_404(db, qualification)
    try:
        share_with_partners(db, deal, actor=f"admin:{admin.email}")
    except ValueError as exc:
        return _detail_error(request, db, qualification, str(exc))
    return RedirectResponse(url=f"/admin/oportunidades/{qualification.id}#matching", status_code=303)


@router.post("/{qualification_id}/matching/{decision_id}/revisao")
async def revisar_loja(
    request: Request,
    qualification_id: str,
    decision_id: str,
    decisao: str = Form(...),
    motivo: str = Form(""),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    qualification = _qualification_or_404(db, qualification_id)
    deal = _active_deal_or_404(db, qualification)
    try:
        decision = db.get(MatchingDecision, uuid.UUID(decision_id))
    except ValueError:
        decision = None
    # The decision must belong to this very opportunity: the URL never widens what an id can reach.
    if decision is None or decision.deal_id != deal.id:
        raise HTTPException(status_code=404)
    try:
        override = MatchOverride(decisao)
        set_override(db, decision, override, reason=motivo, actor=f"admin:{admin.email}")
    except ValueError as exc:
        message = "Decisão inválida." if decisao not in {o.value for o in MatchOverride} else str(exc)
        return _detail_error(request, db, qualification, message)
    return RedirectResponse(url=f"/admin/oportunidades/{qualification.id}#matching", status_code=303)
