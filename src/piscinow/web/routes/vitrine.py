from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member
from piscinow.models.product import Product, ProductKind
from piscinow.models.service import Service, ServiceKind
from piscinow.web.deps import get_db

router = APIRouter(prefix="/vitrine")


@router.get("/produtos", response_class=HTMLResponse)
async def vitrine_produtos(
    request: Request,
    kind: str = "",
    category: str = "",
    regiao: str = "",
    db: Session = Depends(get_db),
):
    templates = request.app.state.templates
    query = select(Product, Member).join(Member, Product.member_id == Member.id).where(Product.active.is_(True))
    if kind in {k.value for k in ProductKind}:
        query = query.where(Product.kind == ProductKind(kind))
    if category:
        query = query.where(Product.category.ilike(f"%{category}%"))
    if regiao:
        query = query.where(Member.region.ilike(f"%{regiao}%"))
    rows = db.execute(query.order_by(Product.created_at.desc())).all()
    items = [{"product": row[0], "loja": row[1]} for row in rows]
    return templates.TemplateResponse(
        request,
        "vitrine_produtos.html",
        {"items": items, "kind": kind, "category": category, "regiao": regiao},
    )


@router.get("/servicos", response_class=HTMLResponse)
async def vitrine_servicos(
    request: Request,
    kind: str = "",
    category: str = "",
    regiao: str = "",
    db: Session = Depends(get_db),
):
    templates = request.app.state.templates
    query = select(Service, Member).join(Member, Service.member_id == Member.id).where(Service.active.is_(True))
    if kind in {k.value for k in ServiceKind}:
        query = query.where(Service.kind == ServiceKind(kind))
    if category:
        query = query.where(Service.category.ilike(f"%{category}%"))
    if regiao:
        query = query.where(Member.region.ilike(f"%{regiao}%"))
    rows = db.execute(query.order_by(Service.created_at.desc())).all()
    items = [{"service": row[0], "prestador": row[1]} for row in rows]
    return templates.TemplateResponse(
        request,
        "vitrine_servicos.html",
        {"items": items, "kind": kind, "category": category, "regiao": regiao},
    )
