from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.service import Service, ServiceKind
from piscinow.prestador_auth import login as do_login, logout as do_logout, require_prestador
from piscinow.rate_limit import limiter, prestador_login_rate_limit_string
from piscinow.web.deps import get_db

router = APIRouter(prefix="/prestador")


@router.get("/definir-senha/{token}", response_class=HTMLResponse)
async def definir_senha_form(token: str, request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    member = db.scalar(
        select(Member).where(
            Member.set_password_token == token,
            Member.profile_type == ProfileType.PRESTADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "prestador_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    return templates.TemplateResponse(
        request, "prestador_definir_senha.html", {"token": token, "invalid": False, "error": None}
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
    member = db.scalar(
        select(Member).where(
            Member.set_password_token == token,
            Member.profile_type == ProfileType.PRESTADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "prestador_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "prestador_definir_senha.html",
            {"token": token, "invalid": False, "error": "As senhas nao coincidem."},
            status_code=400,
        )
    normalized_email = email.strip().lower()
    existing = db.scalar(
        select(Member).where(
            Member.email == normalized_email,
            Member.profile_type == ProfileType.PRESTADOR,
            Member.id != member.id,
        )
    )
    if existing is not None:
        return templates.TemplateResponse(
            request,
            "prestador_definir_senha.html",
            {"token": token, "invalid": False, "error": "Esse e-mail ja esta em uso por outro prestador."},
            status_code=400,
        )
    member.email = normalized_email
    member.set_password(password)
    return RedirectResponse(url="/prestador/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "prestador_login.html", {"error": None})


@router.post("/login")
@limiter.limit(prestador_login_rate_limit_string)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if do_login(request, db, email, password):
        return RedirectResponse(url="/prestador/servicos", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "prestador_login.html", {"error": "E-mail ou senha invalidos"}, status_code=401
    )


@router.post("/logout")
async def logout_submit(request: Request):
    do_logout(request)
    return RedirectResponse(url="/prestador/login", status_code=303)


_MAX_PRICE = Decimal("99999999.99")


def _validate_service_form(
    kind: str, category: str, name: str, price_min: str, price_max: str
) -> tuple[str | None, Decimal | None, Decimal | None]:
    if kind not in {k.value for k in ServiceKind}:
        return "Selecione um tipo de servico valido.", None, None
    if not category.strip() or not name.strip():
        return "Preencha categoria e nome do servico.", None, None
    if len(category.strip()) > 100 or len(name.strip()) > 200:
        return "Categoria ou nome do servico excede o limite permitido.", None, None

    def _parse_price(raw: str, label: str) -> tuple[str | None, Decimal | None]:
        if not raw.strip():
            return None, None
        try:
            parsed = Decimal(raw.strip().replace(",", "."))
        except (InvalidOperation, ValueError):
            return f"Informe um preco {label} valido.", None
        if not parsed.is_finite() or parsed <= 0 or parsed > _MAX_PRICE:
            return f"Informe um preco {label} valido.", None
        return None, parsed

    error, parsed_min = _parse_price(price_min, "minimo")
    if error:
        return error, None, None
    error, parsed_max = _parse_price(price_max, "maximo")
    if error:
        return error, None, None

    if parsed_min is not None and parsed_max is not None and parsed_min > parsed_max:
        return "O preco minimo nao pode ser maior que o preco maximo.", None, None

    return None, parsed_min, parsed_max


@router.get("/servicos", response_class=HTMLResponse)
async def servicos(
    request: Request,
    db: Session = Depends(get_db),
    prestador: Member = Depends(require_prestador),
):
    templates = request.app.state.templates
    items = list(
        db.scalars(select(Service).where(Service.member_id == prestador.id).order_by(Service.created_at.desc()))
    )
    return templates.TemplateResponse(
        request, "prestador_servicos.html", {"services": items, "error": None, "prefill": {}, "note": None}
    )


@router.post("/servicos")
async def criar_servico(
    request: Request,
    kind: str = Form(...),
    category: str = Form(...),
    name: str = Form(...),
    price_min: str = Form(""),
    price_max: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    prestador: Member = Depends(require_prestador),
):
    templates = request.app.state.templates
    error, parsed_min, parsed_max = _validate_service_form(kind, category, name, price_min, price_max)

    if error:
        items = list(
            db.scalars(select(Service).where(Service.member_id == prestador.id).order_by(Service.created_at.desc()))
        )
        prefill = {
            "kind": kind,
            "category": category,
            "name": name,
            "price_min": price_min,
            "price_max": price_max,
            "description": description,
        }
        return templates.TemplateResponse(
            request,
            "prestador_servicos.html",
            {"services": items, "error": error, "prefill": prefill, "note": None},
            status_code=400,
        )

    service = Service(
        member_id=prestador.id,
        kind=ServiceKind(kind),
        category=category.strip(),
        name=name.strip(),
        price_min=parsed_min,
        price_max=parsed_max,
        description=description.strip() or None,
    )
    db.add(service)
    return RedirectResponse(url="/prestador/servicos", status_code=303)
