import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.agent.llm_provider import LLMProvider
from piscinow.agent.product_extractor import extract_product_fields
from piscinow.loja_auth import login as do_login, logout as do_logout, require_loja
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.product import Product, ProductKind
from piscinow.rate_limit import chat_rate_limit_string, limiter, loja_login_rate_limit_string
from piscinow.web.deps import get_db, get_llm_provider

router = APIRouter(prefix="/loja")

_MAX_PRICE = Decimal("99999999.99")


def _validate_product_form(
    kind: str, category: str, name: str, price: str, size_label: str
) -> tuple[str | None, Decimal | None]:
    if kind not in {k.value for k in ProductKind}:
        return "Selecione um tipo de produto valido.", None
    if not category.strip() or not name.strip():
        return "Preencha categoria e nome do produto.", None
    if len(category.strip()) > 100 or len(name.strip()) > 200 or len(size_label.strip()) > 50:
        return "Categoria, nome ou tamanho do produto excede o limite permitido.", None
    try:
        parsed_price = Decimal(price.replace(",", "."))
    except (InvalidOperation, ValueError):
        return "Informe um preco valido.", None
    if not parsed_price.is_finite() or parsed_price <= 0 or parsed_price > _MAX_PRICE:
        return "Informe um preco valido.", None
    return None, parsed_price


def _get_owned_product(db: Session, product_id: str, loja_id) -> Product:
    try:
        parsed_id = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=404)
    product = db.get(Product, parsed_id)
    if product is None or product.member_id != loja_id:
        raise HTTPException(status_code=404)
    return product


@router.get("/definir-senha/{token}", response_class=HTMLResponse)
async def definir_senha_form(token: str, request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    member = db.scalar(
        select(Member).where(
            Member.set_password_token == token,
            Member.profile_type == ProfileType.LOJA,
            Member.status == MemberStatus.APPROVED,
        )
    )
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
    member = db.scalar(
        select(Member).where(
            Member.set_password_token == token,
            Member.profile_type == ProfileType.LOJA,
            Member.status == MemberStatus.APPROVED,
        )
    )
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
    normalized_email = email.strip().lower()
    existing = db.scalar(
        select(Member).where(
            Member.email == normalized_email,
            Member.id != member.id,
        )
    )
    if existing is not None:
        return templates.TemplateResponse(
            request,
            "loja_definir_senha.html",
            {"token": token, "invalid": False, "error": "Esse e-mail ja esta em uso."},
            status_code=400,
        )
    member.email = normalized_email
    member.set_password(password)
    return RedirectResponse(url="/loja/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "loja_login.html", {"error": None})


@router.post("/login")
@limiter.limit(loja_login_rate_limit_string)
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


@router.get("/produtos", response_class=HTMLResponse)
async def produtos(
    request: Request,
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    templates = request.app.state.templates
    items = list(
        db.scalars(select(Product).where(Product.member_id == loja.id).order_by(Product.created_at.desc()))
    )
    return templates.TemplateResponse(
        request, "loja_produtos.html", {"products": items, "error": None, "prefill": {}, "note": None}
    )


@router.post("/produtos")
async def criar_produto(
    request: Request,
    kind: str = Form(...),
    category: str = Form(...),
    name: str = Form(...),
    price: str = Form(...),
    description: str = Form(""),
    size_label: str = Form(""),
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    templates = request.app.state.templates
    error, parsed_price = _validate_product_form(kind, category, name, price, size_label)

    if error:
        items = list(
            db.scalars(select(Product).where(Product.member_id == loja.id).order_by(Product.created_at.desc()))
        )
        prefill = {
            "kind": kind,
            "category": category,
            "name": name,
            "price": price,
            "description": description,
            "size_label": size_label,
        }
        return templates.TemplateResponse(
            request,
            "loja_produtos.html",
            {"products": items, "error": error, "prefill": prefill, "note": None},
            status_code=400,
        )

    product = Product(
        member_id=loja.id,
        kind=ProductKind(kind),
        category=category.strip(),
        name=name.strip(),
        price=parsed_price,
        description=description.strip() or None,
        size_label=size_label.strip() or None,
    )
    db.add(product)
    return RedirectResponse(url="/loja/produtos", status_code=303)


@router.get("/produtos/{product_id}/editar", response_class=HTMLResponse)
async def editar_produto_form(
    product_id: str,
    request: Request,
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    product = _get_owned_product(db, product_id, loja.id)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "loja_produto_editar.html", {"product": product, "error": None})


@router.post("/produtos/{product_id}/editar")
async def editar_produto_submit(
    product_id: str,
    request: Request,
    kind: str = Form(...),
    category: str = Form(...),
    name: str = Form(...),
    price: str = Form(...),
    description: str = Form(""),
    size_label: str = Form(""),
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    product = _get_owned_product(db, product_id, loja.id)

    templates = request.app.state.templates
    error, parsed_price = _validate_product_form(kind, category, name, price, size_label)

    if error:
        return templates.TemplateResponse(
            request, "loja_produto_editar.html", {"product": product, "error": error}, status_code=400
        )

    product.kind = ProductKind(kind)
    product.category = category.strip()
    product.name = name.strip()
    product.price = parsed_price
    product.description = description.strip() or None
    product.size_label = size_label.strip() or None
    return RedirectResponse(url="/loja/produtos", status_code=303)


@router.post("/produtos/chat")
@limiter.limit(chat_rate_limit_string)
async def produtos_chat(
    request: Request,
    text: str = Form(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    loja: Member = Depends(require_loja),
):
    templates = request.app.state.templates
    prefill = await extract_product_fields(llm, text)
    items = list(
        db.scalars(select(Product).where(Product.member_id == loja.id).order_by(Product.created_at.desc()))
    )
    note = None
    if not any(prefill.values()):
        note = "Nao consegui entender, preencha manualmente."
    return templates.TemplateResponse(
        request, "loja_produtos.html", {"products": items, "error": None, "prefill": prefill, "note": note}
    )


@router.post("/produtos/{product_id}/desativar")
async def desativar_produto(
    product_id: str,
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    product = _get_owned_product(db, product_id, loja.id)
    product.active = False
    return RedirectResponse(url="/loja/produtos", status_code=303)
