import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from piscinow.installation.service import InstallationError, inbox_for_installer, respond_assignment
from piscinow.models.installation import AssignmentStatus, InstallerAssignment
from piscinow.models.member import Member
from piscinow.prestador_auth import require_prestador
from piscinow.web.deps import get_db

router = APIRouter(prefix="/prestador/instalacoes")

STATUS_LABELS = {"pendente": "Aguardando a sua resposta", "aceita": "Você aceitou", "recusada": "Você recusou", "cancelada": "Cancelada"}


def _render(request: Request, db: Session, installer: Member, *, error: str | None = None, status_code: int = 200):
    items = inbox_for_installer(db, installer.id)
    for item in items:
        item["label"] = STATUS_LABELS[item["assignment"].status.value]
    return request.app.state.templates.TemplateResponse(
        request, "prestador_instalacoes.html", {"items": items, "error": error}, status_code=status_code
    )


@router.get("", response_class=HTMLResponse)
async def caixa_de_entrada(
    request: Request, db: Session = Depends(get_db), prestador: Member = Depends(require_prestador)
):
    return _render(request, db, prestador)


@router.post("/{assignment_id}/resposta")
async def responder(
    request: Request,
    assignment_id: str,
    decisao: str = Form(...),
    motivo: str = Form(""),
    db: Session = Depends(get_db),
    prestador: Member = Depends(require_prestador),
):
    try:
        assignment = db.get(InstallerAssignment, uuid.UUID(assignment_id))
    except ValueError:
        assignment = None
    # Only a live-or-answered assignment of this very installer; anything else does not exist for them.
    if (
        assignment is None or assignment.installer_member_id != prestador.id
        or assignment.status == AssignmentStatus.CANCELADA
    ):
        raise HTTPException(status_code=404)
    try:
        respond_assignment(db, assignment, prestador, answer=decisao, reason=motivo)
    except InstallationError as exc:
        return _render(request, db, prestador, error=exc.errors[0], status_code=400)
    return RedirectResponse(url="/prestador/instalacoes", status_code=303)
