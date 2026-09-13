from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.loja_auth import login as do_login, logout as do_logout
from piscinow.models.member import Member, ProfileType
from piscinow.web.deps import get_db

router = APIRouter(prefix="/loja")


@router.get("/definir-senha/{token}", response_class=HTMLResponse)
async def definir_senha_form(token: str, request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    member = db.scalar(select(Member).where(Member.set_password_token == token))
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "loja_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    return templates.TemplateResponse(
        request, "loja_definir_senha.html", {"token": token, "invalid": False, "error": None}
    )


@router.post("/definir-senha/{token}")
async def definir_senha_submit(
    token: str,
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    templates = request.app.state.templates
    member = db.scalar(select(Member).where(Member.set_password_token == token))
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "loja_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "loja_definir_senha.html",
            {"token": token, "invalid": False, "error": "As senhas nao coincidem."},
            status_code=400,
        )
    existing = db.scalar(
        select(Member).where(
            Member.email == email,
            Member.profile_type == ProfileType.LOJA,
            Member.id != member.id,
        )
    )
    if existing is not None:
        return templates.TemplateResponse(
            request,
            "loja_definir_senha.html",
            {"token": token, "invalid": False, "error": "Esse e-mail ja esta em uso por outra loja."},
            status_code=400,
        )
    member.email = email
    member.set_password(password)
    return RedirectResponse(url="/loja/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "loja_login.html", {"error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if do_login(request, db, email, password):
        return RedirectResponse(url="/loja/produtos", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "loja_login.html", {"error": "E-mail ou senha invalidos"}, status_code=401
    )


@router.post("/logout")
async def logout_submit(request: Request):
    do_logout(request)
    return RedirectResponse(url="/loja/login", status_code=303)
