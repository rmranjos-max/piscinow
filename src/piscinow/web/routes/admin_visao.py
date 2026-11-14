from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from piscinow.auth import require_admin
from piscinow.models.admin import AdminUser
from piscinow.overview.service import EVENT_GROUPS, gather_overview, governance_page
from piscinow.web.deps import get_db

router = APIRouter(prefix="/admin")


@router.get("", response_class=HTMLResponse)
async def visao_geral(request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)):
    return request.app.state.templates.TemplateResponse(request, "admin_visao_geral.html", gather_overview(db))


@router.get("/governanca", response_class=HTMLResponse)
async def governanca(
    request: Request,
    tipo: str = "todas",
    pagina: str = "1",
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    try:
        page = int(pagina)
    except ValueError:
        page = 1
    context = governance_page(db, tipo, page)
    context["groups"] = {key: label for key, (label, _) in EVENT_GROUPS.items()}
    return request.app.state.templates.TemplateResponse(request, "admin_governanca.html", context)
