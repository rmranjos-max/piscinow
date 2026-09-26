import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.comprador_auth import require_comprador
from piscinow.models.member import Member
from piscinow.models.product import Product
from piscinow.models.project import Project, ProjectService, ProjectStatus
from piscinow.models.service import Service
from piscinow.web.deps import get_db

router = APIRouter(prefix="/comprador")


def _get_or_create_project(db: Session, member_id) -> Project:
    project = db.scalar(select(Project).where(Project.member_id == member_id))
    if project is None:
        project = Project(member_id=member_id)
        db.add(project)
        db.flush()
    return project


def _project_services(db: Session, project_id) -> list[Service]:
    return list(
        db.scalars(
            select(Service)
            .join(ProjectService, ProjectService.service_id == Service.id)
            .where(ProjectService.project_id == project_id)
        )
    )


@router.get("/projeto", response_class=HTMLResponse)
async def projeto(
    request: Request,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    templates = request.app.state.templates
    project = _get_or_create_project(db, comprador.id)
    product = db.get(Product, project.product_id) if project.product_id else None
    services = _project_services(db, project.id)
    return templates.TemplateResponse(
        request,
        "comprador_projeto.html",
        {"project": project, "product": product, "services": services, "error": None, "note": None, "sugestoes": None},
    )


@router.post("/projeto/produto")
async def escolher_produto(
    product_id: str = Form(...),
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    project = _get_or_create_project(db, comprador.id)
    if project.status != ProjectStatus.RASCUNHO:
        raise HTTPException(status_code=400, detail="Projeto ja confirmado, nao pode ser alterado.")
    try:
        parsed_id = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=404)
    product = db.get(Product, parsed_id)
    if product is None or not product.active:
        raise HTTPException(status_code=404)
    project.product_id = product.id
    return RedirectResponse(url="/comprador/projeto", status_code=303)


@router.post("/projeto/servicos/{service_id}/adicionar")
async def adicionar_servico(
    service_id: str,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    project = _get_or_create_project(db, comprador.id)
    if project.status != ProjectStatus.RASCUNHO:
        raise HTTPException(status_code=400, detail="Projeto ja confirmado, nao pode ser alterado.")
    try:
        parsed_id = uuid.UUID(service_id)
    except ValueError:
        raise HTTPException(status_code=404)
    service = db.get(Service, parsed_id)
    if service is None or not service.active:
        raise HTTPException(status_code=404)
    existing = db.scalar(
        select(ProjectService).where(
            ProjectService.project_id == project.id, ProjectService.service_id == service.id
        )
    )
    if existing is None:
        db.add(ProjectService(project_id=project.id, service_id=service.id))
    return RedirectResponse(url="/comprador/projeto", status_code=303)


@router.post("/projeto/servicos/{service_id}/remover")
async def remover_servico(
    service_id: str,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    project = _get_or_create_project(db, comprador.id)
    if project.status != ProjectStatus.RASCUNHO:
        raise HTTPException(status_code=400, detail="Projeto ja confirmado, nao pode ser alterado.")
    try:
        parsed_id = uuid.UUID(service_id)
    except ValueError:
        raise HTTPException(status_code=404)
    link = db.scalar(
        select(ProjectService).where(
            ProjectService.project_id == project.id, ProjectService.service_id == parsed_id
        )
    )
    if link is not None:
        db.delete(link)
    return RedirectResponse(url="/comprador/projeto", status_code=303)
