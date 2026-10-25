from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
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
from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStage, PaymentStatus
from piscinow.models.product import Product
from piscinow.models.project import Project, ProjectService, ProjectStatus
from piscinow.models.service import Service
from piscinow.payment.payment_provider import PaymentProvider, PaymentProviderError
from piscinow.rate_limit import admin_login_rate_limit_string, limiter
from piscinow.web.deps import get_db, get_payment_provider, require_payments_enabled

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

    payment_rows = db.execute(
        select(Payment, Project, Member, Product)
        .join(Project, Payment.project_id == Project.id)
        .join(Member, Project.member_id == Member.id)
        .join(Product, Project.product_id == Product.id)
        .order_by(Payment.created_at.desc())
    ).all()
    payments = [
        {"payment": row[0], "project": row[1], "comprador": row[2], "product": row[3]} for row in payment_rows
    ]
    return templates.TemplateResponse(request, "admin_pagamentos.html", {"items": items, "payments": payments})


MAX_PAYMENT_AMOUNT = Decimal("99999999.99")


def _parse_amount(raw) -> Decimal | None:
    """Parse a monetary value typed by an admin, pt-BR style.

    Accepts at most one separator (either "," or ".") used as the decimal
    separator - this covers plain integers ("18000"), comma-decimals
    ("18000,50", the pt-BR norm) and dot-decimals ("18000.50"). Anything
    with two separators (e.g. a pt-BR thousands-grouped "18.000,50") is
    rejected rather than guessed at, to avoid silently misreading one
    locale's convention as another's. The max-2-decimal-places check below
    also catches the dangerous case of an admin typing "18.000" meaning
    eighteen thousand: that parses to 18.000, which has 3 decimal places
    and gets rejected instead of silently saved as R$ 18,00.
    """
    text = str(raw).strip()
    if not text:
        return None
    if sum(text.count(c) for c in ".,") > 1:
        return None
    normalized = text.replace(",", ".")
    try:
        amount = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    if amount.as_tuple().exponent < -2:
        return None
    if amount > MAX_PAYMENT_AMOUNT:
        return None
    return amount.quantize(Decimal("0.01"))


def _project_services(db: Session, project_id) -> list[Service]:
    return list(
        db.scalars(
            select(Service)
            .join(ProjectService, ProjectService.service_id == Service.id)
            .where(ProjectService.project_id == project_id)
        )
    )


@router.get("/pagamentos/{project_id}/cronograma", response_class=HTMLResponse)
async def cronograma_form(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    templates = request.app.state.templates
    project = db.get(Project, project_id)
    if project is None or project.status != ProjectStatus.CONFIRMADO:
        raise HTTPException(status_code=404)
    existing = db.scalar(select(Payment).where(Payment.project_id == project.id))
    if existing is not None:
        raise HTTPException(status_code=400, detail="Este projeto ja tem um pagamento.")
    product = db.get(Product, project.product_id)
    services = _project_services(db, project.id)
    return templates.TemplateResponse(
        request,
        "admin_cronograma.html",
        {"project": project, "product": product, "services": services, "error": None},
    )


@router.post("/pagamentos/{project_id}/cronograma")
async def cronograma_submit(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    templates = request.app.state.templates
    project = db.get(Project, project_id)
    if project is None or project.status != ProjectStatus.CONFIRMADO:
        raise HTTPException(status_code=404)
    existing = db.scalar(select(Payment).where(Payment.project_id == project.id))
    if existing is not None:
        raise HTTPException(status_code=400, detail="Este projeto ja tem um pagamento.")

    product = db.get(Product, project.product_id)
    services = _project_services(db, project.id)
    form = await request.form()

    def _parse_item(prefix: str, item_id) -> tuple[str | None, PaymentStage | None, Decimal | None]:
        stage_raw = form.get(f"stage_{prefix}_{item_id}", "")
        amount_raw = form.get(f"amount_{prefix}_{item_id}", "")
        if stage_raw not in {s.value for s in PaymentStage}:
            return "Escolha uma fase valida para todos os itens.", None, None
        amount = _parse_amount(amount_raw)
        if amount is None:
            return "Informe um valor valido para todos os itens.", None, None
        return None, PaymentStage(stage_raw), amount

    allocations_data = []
    error = None

    error, stage, amount = _parse_item("product", product.id)
    if not error:
        allocations_data.append(
            {"stage": stage, "amount": amount, "recipient_member_id": product.member_id, "product_id": product.id}
        )

    if not error:
        for service in services:
            error, stage, amount = _parse_item("service", service.id)
            if error:
                break
            allocations_data.append(
                {"stage": stage, "amount": amount, "recipient_member_id": service.member_id, "service_id": service.id}
            )

    total = None
    if not error:
        total = sum((item["amount"] for item in allocations_data), Decimal("0")).quantize(Decimal("0.01"))
        if total > MAX_PAYMENT_AMOUNT:
            error = "A soma dos valores ultrapassa o limite permitido para um pagamento."

    if error:
        return templates.TemplateResponse(
            request,
            "admin_cronograma.html",
            {"project": project, "product": product, "services": services, "error": error},
            status_code=400,
        )

    payment = Payment(project_id=project.id, total_amount=total)
    db.add(payment)
    db.flush()
    for item in allocations_data:
        db.add(PaymentAllocation(payment_id=payment.id, **item))
    return RedirectResponse(url=f"/admin/pagamentos/{payment.id}", status_code=303)


def _stages_data_for_payment(db: Session, payment: Payment) -> list[dict]:
    allocations = list(
        db.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id))
    )
    stages_data = []
    for stage in PaymentStage:
        stage_allocations = [
            (allocation, db.get(Member, allocation.recipient_member_id))
            for allocation in allocations
            if allocation.stage == stage
        ]
        if not stage_allocations:
            continue
        all_released = all(a.status == AllocationStatus.LIBERADO for a, _ in stage_allocations)
        stages_data.append({"stage": stage, "allocations": stage_allocations, "all_released": all_released})
    return stages_data


@router.get("/pagamentos/{payment_id}", response_class=HTMLResponse)
async def pagamento_detalhe(
    payment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    templates = request.app.state.templates
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404)
    stages_data = _stages_data_for_payment(db, payment)
    return templates.TemplateResponse(
        request, "admin_pagamento_detalhe.html", {"payment": payment, "stages_data": stages_data, "error": None}
    )


@router.post(
    "/pagamentos/{payment_id}/fases/{stage}/liberar", dependencies=[Depends(require_payments_enabled)]
)
async def liberar_fase(
    payment_id: str,
    stage: str,
    request: Request,
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
    admin: AdminUser = Depends(require_admin),
):
    templates = request.app.state.templates
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404)
    if payment.status != PaymentStatus.PAGO:
        raise HTTPException(status_code=400, detail="Pagamento ainda nao foi pago pelo comprador.")
    if stage not in {s.value for s in PaymentStage}:
        raise HTTPException(status_code=404)
    allocations = list(
        db.scalars(
            select(PaymentAllocation).where(
                PaymentAllocation.payment_id == payment.id,
                PaymentAllocation.stage == PaymentStage(stage),
                PaymentAllocation.status == AllocationStatus.RETIDO,
            )
        )
    )
    release_error = None
    for allocation in allocations:
        try:
            transfer_id = await payment_provider.release(
                charge_id=payment.external_charge_id, amount=allocation.amount, external_reference=str(allocation.id)
            )
        except PaymentProviderError:
            release_error = (
                "Nao foi possivel liberar todos os itens desta fase. As alocacoes ja liberadas "
                "foram mantidas; tente novamente para as restantes."
            )
            break
        allocation.status = AllocationStatus.LIBERADO
        allocation.released_at = datetime.now(timezone.utc)
        allocation.released_by = admin.email
        allocation.external_transfer_id = transfer_id
        # Commit this single allocation now, not at end-of-request: if a later
        # allocation's release() call fails, we must not roll back releases
        # that already happened for real at the provider.
        db.commit()

    if release_error is not None:
        stages_data = _stages_data_for_payment(db, payment)
        return templates.TemplateResponse(
            request,
            "admin_pagamento_detalhe.html",
            {"payment": payment, "stages_data": stages_data, "error": release_error},
            status_code=400,
        )

    return RedirectResponse(url=f"/admin/pagamentos/{payment.id}", status_code=303)
