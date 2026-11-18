import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from piscinow.agent.llm_provider import LLMProvider
from piscinow.agent.project_search import extract_search_filters
from piscinow.comprador_auth import require_comprador
from piscinow.models.member import Member
from piscinow.models.payment import Payment, PaymentAllocation, PaymentStatus
from piscinow.models.product import Product, ProductKind
from piscinow.models.proposal import Proposal, ProposalStatus
from piscinow.models.project import Project, ProjectService, ProjectStatus
from piscinow.models.service import Service, ServiceKind
from piscinow.payment.payment_provider import PaymentProvider, PaymentProviderError
from piscinow.rate_limit import limiter, chat_rate_limit_string
from piscinow.web.deps import get_db, get_llm_provider, get_payment_provider, require_payments_enabled
from piscinow.installation.service import responsible_installer
from piscinow.models.proposal import FeasibilityCheck
from piscinow.models.qualification import Deal
from piscinow.proposals.rules import caveats
from piscinow.proposals.service import item_rows
from piscinow.qualification.deals import active_deal
from piscinow.qualification.fields import REQUIRED, label_for
from piscinow.qualification.service import find_qualification
from piscinow.web.journey import buyer_journey, stage_overview

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


def _read_only_overview(db: Session, comprador: Member):
    """Project, product, services, payment and stage rows of a comprador, without creating anything."""
    project = db.scalar(select(Project).where(Project.member_id == comprador.id))
    if project is None:
        return None, None, [], None, []
    product = db.get(Product, project.product_id) if project.product_id else None
    services = _project_services(db, project.id)
    payment = db.scalar(select(Payment).where(Payment.project_id == project.id))
    rows = []
    if payment is not None:
        for allocation, recipient in db.execute(
            select(PaymentAllocation, Member)
            .join(Member, PaymentAllocation.recipient_member_id == Member.id)
            .where(PaymentAllocation.payment_id == payment.id)
        ):
            rows.append((allocation.stage.value, allocation.status.value, allocation.amount, recipient.name))
    return project, product, services, payment, rows


FEASIBILITY_BADGES = {
    "pending": ("Em avaliação", "amber", "A equipe está avaliando o terreno."),
    "conditionally_approved": ("Aprovada com ressalvas", "green", "Aprovada pela equipe."),
    "approved": ("Aprovada", "green", "O terreno foi aprovado pela equipe."),
    "rejected": ("Reprovada", "amber", "A equipe encontrou um impeditivo. Ela vai conversar com você."),
}
BRIEFING_BADGES = {
    "none": ("Não iniciado", ""), "in_progress": ("Em construção", "amber"),
    "declined": ("Aguardando sua autorização", "amber"), "done": ("Compartilhado", "green"),
}


def _journey_context(db: Session, comprador: Member) -> dict:
    """Everything the buyer's home and project pages read. Never creates anything."""
    project, _, _, payment, rows = _read_only_overview(db, comprador)
    qualification = find_qualification(db, comprador)
    values = qualification.values() if qualification else {}
    missing = [key for key in REQUIRED if key not in values]
    consent = qualification.consent.value if qualification else None
    if qualification is None:
        briefing = "none"
    elif not missing and consent == "concedido":
        briefing = "done"
    elif not missing and consent == "recusado":
        briefing = "declined"
    else:
        briefing = "in_progress"

    deal = active_deal(db, comprador.id) or db.scalar(
        select(Deal).where(Deal.member_id == comprador.id).order_by(Deal.number.desc()).limit(1)
    )
    open_proposals = 0
    feasibility = None
    if deal is not None:
        open_proposals = db.scalar(
            select(func.count()).select_from(Proposal).where(
                Proposal.deal_id == deal.id, Proposal.status == ProposalStatus.ENVIADA
            )
        )
        check = db.scalar(select(FeasibilityCheck).where(FeasibilityCheck.deal_id == deal.id))
        if check is not None:
            label, tone, text = FEASIBILITY_BADGES[check.status.value]
            feasibility = {"label": label, "tone": tone, "text": text, "caveats": caveats(check.items)}

    proposal = db.get(Proposal, project.proposal_id) if project is not None and project.proposal_id else None
    journey = buyer_journey(
        briefing=briefing, deal_status=deal.status.value if deal else None, open_proposals=open_proposals,
        payment_status=payment.status.value if payment else None,
        all_released=bool(rows) and all(status == "liberado" for _, status, _, _ in rows),
        project_linked=proposal is not None or payment is not None,
    )
    summary = " · ".join(
        label_for(key, values[key]) for key in ("tipo_piscina", "localizacao", "dimensoes", "prazo") if key in values
    )
    label, tone = BRIEFING_BADGES[briefing]
    return {
        "journey": journey, "deal": deal, "payment": payment, "project": project, "proposal": proposal,
        "feasibility": feasibility, "briefing_summary": summary, "briefing_badge": {"label": label, "tone": tone},
    }


def _accepted_summary(request: Request, db: Session, proposal: Proposal) -> dict:
    store = db.get(Member, proposal.partner_member_id)
    first = proposal.items[0] if proposal.items else None
    storage = request.app.state.media_storage
    photo_key = next((item.photo_thumb_key for item in proposal.items if item.photo_thumb_key), None)
    return {
        "store": store.name, "version": proposal.version, "total": proposal.total,
        "item": first.description if first else "", "photo": storage.url(photo_key) if photo_key else None,
    }


@router.get("", response_class=HTMLResponse)
async def inicio(
    request: Request,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    context = _journey_context(db, comprador)
    first_name = (comprador.name or "").split()[0] if (comprador.name or "").strip() else ""
    proposal = context["proposal"]
    return request.app.state.templates.TemplateResponse(
        request,
        "comprador_inicio.html",
        {**context, "first_name": first_name, "accepted": _accepted_summary(request, db, proposal) if proposal else None},
    )


@router.get("/obra", response_class=HTMLResponse)
async def obra(
    request: Request,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    _, _, _, payment, rows = _read_only_overview(db, comprador)
    request.scope["shell_path"] = "/comprador/projeto"  # the work belongs to "Meu projeto" in the menu
    return request.app.state.templates.TemplateResponse(
        request, "comprador_obra.html", {"payment": payment, "stages": stage_overview(rows)}
    )


@router.get("/projeto", response_class=HTMLResponse)
async def projeto(
    request: Request,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    templates = request.app.state.templates
    context = _journey_context(db, comprador)
    project, proposal = context["project"], context["proposal"]
    if proposal is not None:
        deal = db.get(Deal, proposal.deal_id)
        installer = responsible_installer(db, deal) if deal else None
        view = {
            "store": db.get(Member, proposal.partner_member_id).name, "version": proposal.version,
            "accepted_at": proposal.decided_at, "lead_time_days": proposal.lead_time_days, "total": proposal.total,
            "scope": proposal.scope, "exclusions": proposal.exclusions,
            "items": item_rows(request.app.state.media_storage, proposal),
            "installer": installer.name if installer else None,
        }
        return templates.TemplateResponse(
            request, "comprador_meu_projeto.html", {**context, "project": view}
        )
    if project is None or project.status != ProjectStatus.CONFIRMADO:
        # The project is born from an accepted proposal; nothing is created by opening this page.
        return templates.TemplateResponse(request, "comprador_meu_projeto.html", {**context, "project": None})

    # A project of the old path (product chosen in the vitrine), kept readable for existing data.
    product = db.get(Product, project.product_id) if project.product_id else None
    services = _project_services(db, project.id)
    payment = db.scalar(select(Payment).where(Payment.project_id == project.id))
    return templates.TemplateResponse(
        request,
        "comprador_projeto.html",
        {
            "project": project,
            "product": product,
            "services": services,
            "payment": payment,
            "error": None,
            "note": None,
            "sugestoes": None,
        },
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


@router.post("/projeto/confirmar")
async def confirmar_projeto(
    request: Request,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    project = _get_or_create_project(db, comprador.id)
    if project.status != ProjectStatus.RASCUNHO:
        raise HTTPException(status_code=400, detail="Projeto ja confirmado.")
    if project.product_id is None:
        templates = request.app.state.templates
        services = _project_services(db, project.id)
        return templates.TemplateResponse(
            request,
            "comprador_projeto.html",
            {
                "project": project,
                "product": None,
                "services": services,
                "error": "Escolha um produto antes de confirmar o projeto.",
                "note": None,
                "sugestoes": None,
            },
            status_code=400,
        )
    project.status = ProjectStatus.CONFIRMADO
    return RedirectResponse(url="/comprador/projeto", status_code=303)


@router.post("/projeto/buscar")
@limiter.limit(chat_rate_limit_string)
async def buscar_sugestoes(
    request: Request,
    text: str = Form(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    comprador: Member = Depends(require_comprador),
):
    templates = request.app.state.templates
    project = _get_or_create_project(db, comprador.id)
    product = db.get(Product, project.product_id) if project.product_id else None
    services = _project_services(db, project.id)
    filters = await extract_search_filters(llm, text)

    produtos_query = select(Product).join(Member, Product.member_id == Member.id).where(Product.active.is_(True))
    if filters["kind"] in {k.value for k in ProductKind}:
        produtos_query = produtos_query.where(Product.kind == ProductKind(filters["kind"]))
    if filters["category"]:
        produtos_query = produtos_query.where(Product.category.ilike(f"%{filters['category']}%"))
    if filters["region"]:
        produtos_query = produtos_query.where(Member.region.ilike(f"%{filters['region']}%"))
    produtos_sugeridos = list(db.scalars(produtos_query.limit(10)))

    servicos_query = select(Service).join(Member, Service.member_id == Member.id).where(Service.active.is_(True))
    if filters["kind"] in {k.value for k in ServiceKind}:
        servicos_query = servicos_query.where(Service.kind == ServiceKind(filters["kind"]))
    if filters["category"]:
        servicos_query = servicos_query.where(Service.category.ilike(f"%{filters['category']}%"))
    if filters["region"]:
        servicos_query = servicos_query.where(Member.region.ilike(f"%{filters['region']}%"))
    servicos_sugeridos = list(db.scalars(servicos_query.limit(10)))

    note = None
    if not produtos_sugeridos and not servicos_sugeridos:
        note = "Nao encontrei nada com esses filtros, tente ajustar."

    return templates.TemplateResponse(
        request,
        "comprador_projeto.html",
        {
            "project": project,
            "product": product,
            "services": services,
            "error": None,
            "note": note,
            "sugestoes": {"produtos": produtos_sugeridos, "servicos": servicos_sugeridos},
        },
    )


@router.get("/projeto/pagamento", response_class=HTMLResponse)
async def ver_pagamento(
    request: Request,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    templates = request.app.state.templates
    project = _get_or_create_project(db, comprador.id)
    payment = db.scalar(select(Payment).where(Payment.project_id == project.id))
    if payment is None:
        raise HTTPException(status_code=404)
    allocations = [
        (allocation, db.get(Member, allocation.recipient_member_id))
        for allocation in db.scalars(
            select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id)
        )
    ]
    return templates.TemplateResponse(
        request, "comprador_pagamento.html", {"payment": payment, "allocations": allocations, "error": None}
    )


@router.post("/projeto/pagamento/pagar", dependencies=[Depends(require_payments_enabled)])
async def pagar(
    request: Request,
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
    comprador: Member = Depends(require_comprador),
):
    templates = request.app.state.templates
    project = _get_or_create_project(db, comprador.id)
    payment = db.scalar(select(Payment).where(Payment.project_id == project.id))
    if payment is None:
        raise HTTPException(status_code=404)
    if payment.status != PaymentStatus.PENDENTE:
        raise HTTPException(status_code=400, detail="Este pagamento ja foi processado.")

    allocations = [
        (allocation, db.get(Member, allocation.recipient_member_id))
        for allocation in db.scalars(
            select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id)
        )
    ]

    try:
        charge_id = await payment_provider.charge(amount=payment.total_amount, external_reference=str(payment.id))
    except PaymentProviderError:
        return templates.TemplateResponse(
            request,
            "comprador_pagamento.html",
            {
                "payment": payment,
                "allocations": allocations,
                "error": "Nao foi possivel processar o pagamento. Tente novamente.",
            },
            status_code=400,
        )

    payment.external_charge_id = charge_id
    payment.status = PaymentStatus.PAGO
    payment.paid_at = datetime.now(timezone.utc)
    return RedirectResponse(url="/comprador/projeto/pagamento", status_code=303)
