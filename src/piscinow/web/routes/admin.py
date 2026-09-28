from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.agent.memory_store import MemoryStore
from piscinow.auth import login as do_login
from piscinow.auth import logout as do_logout
from piscinow.auth import require_admin
from piscinow.config import get_settings
from piscinow.models.admin import AdminUser
from piscinow.models.conversation import Conversation
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.memory import MemoryKind, MemorySource
from piscinow.models.payment import Payment
from piscinow.models.product import Product
from piscinow.models.project import Project, ProjectStatus
from piscinow.rate_limit import admin_login_rate_limit_string, limiter
from piscinow.web.deps import get_db

router = APIRouter(prefix="/admin")


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "admin_login.html", {"error": None})


@router.post("/login")
@limiter.limit(admin_login_rate_limit_string)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if do_login(request, db, email, password):
        return RedirectResponse(url="/admin/fila", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "admin_login.html", {"error": "E-mail ou senha invalidos"}, status_code=401
    )


@router.post("/logout")
async def logout_submit(request: Request):
    do_logout(request)
    return RedirectResponse(url="/admin/login", status_code=303)


@router.get("/fila", response_class=HTMLResponse)
async def fila(request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)):
    templates = request.app.state.templates
    pending = list(db.scalars(select(Member).where(Member.status == MemberStatus.WAITLISTED)))
    return templates.TemplateResponse(request, "admin_queue.html", {"members": pending})


@router.post("/fila/{member_id}/aprovar")
async def aprovar(
    member_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    member = db.get(Member, member_id)
    if member is not None:
        member.approve(approved_by=admin.email)
        if member.profile_type in (ProfileType.LOJA, ProfileType.PRESTADOR, ProfileType.COMPRADOR):
            member.generate_set_password_token()
    return RedirectResponse(url="/admin/fila", status_code=303)


@router.post("/fila/{member_id}/recusar")
async def recusar(
    member_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    member = db.get(Member, member_id)
    if member is not None:
        member.reject(approved_by=admin.email)
    return RedirectResponse(url="/admin/fila", status_code=303)


@router.get("/correcoes", response_class=HTMLResponse)
async def correcoes(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    conversations = list(
        db.scalars(select(Conversation).order_by(Conversation.started_at.desc()).limit(20))
    )
    return templates.TemplateResponse(request, "admin_corrections.html", {"conversations": conversations})


@router.post("/correcoes/ensinar")
async def ensinar(
    content: str = Form(...),
    profile_type: str = Form(...),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    memory = MemoryStore(db)
    memory.write(
        content=content,
        kind=MemoryKind.CORRECTION,
        source=MemorySource.HUMAN,
        profile_type=ProfileType(profile_type) if profile_type != "geral" else None,
        confidence=0.9,
        created_by=admin.email,
    )
    return RedirectResponse(url="/admin/correcoes", status_code=303)


@router.get("/lojas", response_class=HTMLResponse)
async def lojas(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    items = list(
        db.scalars(
            select(Member)
            .where(Member.profile_type == ProfileType.LOJA, Member.status == MemberStatus.APPROVED)
            .order_by(Member.approved_at.desc())
        )
    )
    base_url = get_settings().public_base_url
    return templates.TemplateResponse(request, "admin_lojas.html", {"members": items, "base_url": base_url})


@router.get("/prestadores", response_class=HTMLResponse)
async def prestadores(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    items = list(
        db.scalars(
            select(Member)
            .where(Member.profile_type == ProfileType.PRESTADOR, Member.status == MemberStatus.APPROVED)
            .order_by(Member.approved_at.desc())
        )
    )
    base_url = get_settings().public_base_url
    return templates.TemplateResponse(
        request, "admin_prestadores.html", {"members": items, "base_url": base_url}
    )


@router.get("/compradores", response_class=HTMLResponse)
async def compradores(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    items = list(
        db.scalars(
            select(Member)
            .where(Member.profile_type == ProfileType.COMPRADOR, Member.status == MemberStatus.APPROVED)
            .order_by(Member.approved_at.desc())
        )
    )
    base_url = get_settings().public_base_url
    return templates.TemplateResponse(
        request, "admin_compradores.html", {"members": items, "base_url": base_url}
    )


@router.get("/pagamentos", response_class=HTMLResponse)
async def pagamentos(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    paid_project_ids = select(Payment.project_id)
    rows = db.execute(
        select(Project, Member, Product)
        .join(Member, Project.member_id == Member.id)
        .join(Product, Project.product_id == Product.id)
        .where(Project.status == ProjectStatus.CONFIRMADO, Project.id.not_in(paid_project_ids))
        .order_by(Project.updated_at.desc())
    ).all()
    items = [{"project": row[0], "comprador": row[1], "product": row[2]} for row in rows]
    return templates.TemplateResponse(request, "admin_pagamentos.html", {"items": items})
