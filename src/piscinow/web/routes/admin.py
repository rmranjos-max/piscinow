from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.auth import login as do_login
from piscinow.auth import logout as do_logout
from piscinow.auth import require_admin
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus
from piscinow.web.deps import get_db

router = APIRouter(prefix="/admin")


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "admin_login.html", {"error": None})


@router.post("/login")
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
