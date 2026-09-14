from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.loja_auth import login as do_login, logout as do_logout, require_loja
from piscinow.models.member import Member, ProfileType
from piscinow.models.product import Product, ProductKind
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
    error = None
    parsed_price = None

    if kind not in {k.value for k in ProductKind}:
        error = "Selecione um tipo de produto valido."
    elif not category.strip() or not name.strip():
        error = "Preencha categoria e nome do produto."
    else:
        try:
            parsed_price = Decimal(price.replace(",", "."))
            if parsed_price <= 0:
                error = "Informe um preco valido."
        except (InvalidOperation, ValueError):
            error = "Informe um preco valido."

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
    product = db.get(Product, product_id)
    if product is None or product.member_id != loja.id:
        raise HTTPException(status_code=404)
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
    product = db.get(Product, product_id)
    if product is None or product.member_id != loja.id:
        raise HTTPException(status_code=404)

    templates = request.app.state.templates
    error = None
    parsed_price = None

    if kind not in {k.value for k in ProductKind}:
        error = "Selecione um tipo de produto valido."
    elif not category.strip() or not name.strip():
        error = "Preencha categoria e nome do produto."
    else:
        try:
            parsed_price = Decimal(price.replace(",", "."))
            if parsed_price <= 0:
                error = "Informe um preco valido."
        except (InvalidOperation, ValueError):
            error = "Informe um preco valido."

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
