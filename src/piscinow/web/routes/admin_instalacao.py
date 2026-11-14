import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from piscinow.auth import require_admin
from piscinow.installation.service import (
    SERVICE_KINDS, InstallationError, get_installer_profile, save_installer_profile,
)
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, ProfileType
from piscinow.web.deps import get_db

router = APIRouter(prefix="/admin/prestadores")


def _installer_or_404(db: Session, member_id: str) -> Member:
    try:
        member = db.get(Member, uuid.UUID(member_id))
    except ValueError:
        member = None
    if member is None or member.profile_type != ProfileType.PRESTADOR:
        raise HTTPException(status_code=404)
    return member


def _render(request: Request, installer: Member, form: dict, error: str | None = None, status_code: int = 200):
    return request.app.state.templates.TemplateResponse(
        request, "admin_instalador_atendimento.html",
        {"installer": installer, "form": form, "service_kinds": SERVICE_KINDS, "error": error}, status_code=status_code,
    )


@router.get("/{member_id}/atendimento", response_class=HTMLResponse)
async def formulario(
    request: Request, member_id: str, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    installer = _installer_or_404(db, member_id)
    profile = get_installer_profile(db, installer.id)
    form = {
        "areas": ", ".join(profile.service_areas) if profile else "",
        "service_kinds": list(profile.service_kinds) if profile else [],
        "active": profile.active if profile else True,
    }
    return _render(request, installer, form)


@router.post("/{member_id}/atendimento")
async def salvar(
    request: Request,
    member_id: str,
    areas: str = Form(""),
    service_kinds: list[str] = Form([]),
    active: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    installer = _installer_or_404(db, member_id)
    form = {"areas": areas, "service_kinds": service_kinds, "active": active is not None}
    try:
        save_installer_profile(
            db, installer, areas=areas, service_kinds=service_kinds, active=active is not None, actor=f"admin:{admin.email}"
        )
    except InstallationError as exc:
        return _render(request, installer, form, error=" ".join(exc.errors), status_code=400)
    return RedirectResponse(url="/admin/prestadores", status_code=303)
