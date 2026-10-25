from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from piscinow.loja_auth import require_loja
from piscinow.matching.inbox import inbox_for_partner, respond, visible_decision
from piscinow.models.member import Member
from piscinow.web.deps import get_db

router = APIRouter(prefix="/loja/oportunidades")

RESPONSE_LABELS = {"pendente": "Aguardando a sua resposta", "em_analise": "Você vai analisar", "recusada": "Você recusou"}


def _render(request: Request, db: Session, loja: Member, error: str | None = None, status_code: int = 200):
    items = inbox_for_partner(db, loja.id)
    for item in items:
        item["response_label"] = RESPONSE_LABELS[item["response"]]
    return request.app.state.templates.TemplateResponse(
        request, "loja_oportunidades.html", {"items": items, "error": error}, status_code=status_code
    )


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
    decision = visible_decision(db, decision_id, loja.id)
    if decision is None:
        raise HTTPException(status_code=404)
    try:
        respond(db, decision, answer=decisao, reason=motivo)
    except ValueError as exc:
        return _render(request, db, loja, error=str(exc), status_code=400)
    return RedirectResponse(url="/loja/oportunidades", status_code=303)
