import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from piscinow.auth import require_admin
from piscinow.matching.service import BUDGET_BANDS, POOL_TYPES, ProfileError, get_profile, save_profile
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, ProfileType
from piscinow.web.deps import get_db

router = APIRouter(prefix="/admin/lojas")


def _store_or_404(db: Session, member_id: str) -> Member:
    try:
        member = db.get(Member, uuid.UUID(member_id))
    except ValueError:
        member = None
    if member is None or member.profile_type != ProfileType.LOJA:
        raise HTTPException(status_code=404)
    return member


def _render(request: Request, store: Member, form: dict, error: str | None = None, status_code: int = 200):
    return request.app.state.templates.TemplateResponse(
        request, "admin_atendimento.html",
        {"store": store, "form": form, "pool_types": POOL_TYPES, "budget_bands": BUDGET_BANDS, "error": error},
        status_code=status_code,
    )


@router.get("/{member_id}/atendimento", response_class=HTMLResponse)
async def formulario(
    request: Request, member_id: str, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    store = _store_or_404(db, member_id)
    profile = get_profile(db, store.id)
    form = {
        "areas": ", ".join(profile.service_areas) if profile else "",
        "pool_types": list(profile.pool_types) if profile else [],
        "budget_bands": list(profile.budget_bands) if profile else [],
        "capacity": profile.capacity if profile else 3,
        "active": profile.active if profile else True,
        "exists": profile is not None,
    }
    return _render(request, store, form)


@router.post("/{member_id}/atendimento")
async def salvar(
    request: Request,
    member_id: str,
    areas: str = Form(""),
    pool_types: list[str] = Form([]),
    budget_bands: list[str] = Form([]),
    capacity: str = Form("3"),
    active: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    store = _store_or_404(db, member_id)
    form = {
        "areas": areas, "pool_types": pool_types, "budget_bands": budget_bands,
        "capacity": capacity, "active": active is not None, "exists": get_profile(db, store.id) is not None,
    }
    try:
        try:
            parsed_capacity = int(capacity)
        except ValueError:
            raise ProfileError("A capacidade deve ser um número inteiro.")
        save_profile(
            db, store, areas=areas, pool_types=pool_types, budget_bands=budget_bands,
            capacity=parsed_capacity, active=active is not None, actor=f"admin:{admin.email}",
        )
    except ProfileError as exc:
        return _render(request, store, form, error=str(exc), status_code=400)
    return RedirectResponse(url="/admin/lojas", status_code=303)
