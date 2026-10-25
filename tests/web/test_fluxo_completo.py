from decimal import Decimal

from sqlalchemy import select

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStage, PaymentStatus
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus
from piscinow.models.service import Service, ServiceKind
from tests.web.test_admin_pagamentos import _logged_in
from tests.web.test_comprador_projeto import _comprador_logged_in


def test_full_journey_choose_confirm_schedule_pay_and_release_every_stage(client, db_session):
    # Catalogue the partners would have registered (set up directly: this test is about the money flow).
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.APPROVED)
    db_session.add_all([loja, prestador])
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao completa", price_min=2500
    )
    db_session.add_all([product, service])
    db_session.flush()

    # From here on, only HTTP routes. One client holds both sessions (admin and comprador).
    _logged_in(client, db_session)
    comprador = _comprador_logged_in(client, db_session)

    # 1. The comprador builds and confirms the project.
    assert client.post("/comprador/projeto/produto", data={"product_id": str(product.id)}).status_code == 200
    assert client.post(f"/comprador/projeto/servicos/{service.id}/adicionar").status_code == 200
    assert client.post("/comprador/projeto/confirmar").status_code == 200
    project = db_session.scalar(select(Project).where(Project.member_id == comprador.id))
    db_session.refresh(project)
    assert project.status == ProjectStatus.CONFIRMADO

    # 2. The admin sees it waiting and builds the schedule.
    assert f"/admin/pagamentos/{project.id}/cronograma" in client.get("/admin/pagamentos").text
    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "18000",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    payment = db_session.scalar(select(Payment).where(Payment.project_id == project.id))
    assert payment.status == PaymentStatus.PENDENTE
    assert payment.total_amount == Decimal("21000.00")

    # 3. The comprador sees the schedule and pays once, for the full amount.
    page = client.get("/comprador/projeto/pagamento")
    assert page.status_code == 200
    assert "21.000,00" in page.text
    assert client.post("/comprador/projeto/pagamento/pagar", follow_redirects=False).status_code == 303
    db_session.refresh(payment)
    assert payment.status == PaymentStatus.PAGO
    provider = client.app.state.payment_provider
    assert [c["amount"] for c in provider.charges] == [Decimal("21000.00")]

    # 4. Paying twice is refused and does not charge again.
    assert client.post("/comprador/projeto/pagamento/pagar").status_code == 400
    assert len(provider.charges) == 1

    allocations = {
        a.stage: a for a in db_session.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id))
    }
    assert all(a.status == AllocationStatus.RETIDO for a in allocations.values())

    # 5. Releasing one stage moves only that stage's money.
    assert client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar", follow_redirects=False).status_code == 303
    db_session.refresh(allocations[PaymentStage.ESTRUTURA])
    db_session.refresh(allocations[PaymentStage.ACABAMENTO])
    assert allocations[PaymentStage.ESTRUTURA].status == AllocationStatus.LIBERADO
    assert allocations[PaymentStage.ACABAMENTO].status == AllocationStatus.RETIDO
    assert [r["amount"] for r in provider.releases] == [Decimal("18000.00")]

    # 6. Releasing the same stage again changes nothing; releasing the last stage finishes the payment.
    client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar")
    assert len(provider.releases) == 1
    assert client.post(f"/admin/pagamentos/{payment.id}/fases/acabamento/liberar", follow_redirects=False).status_code == 303
    db_session.refresh(allocations[PaymentStage.ACABAMENTO])
    assert allocations[PaymentStage.ACABAMENTO].status == AllocationStatus.LIBERADO
    assert sum(r["amount"] for r in provider.releases) == payment.total_amount
    assert len(provider.charges) == 1

    # 7. Both sides see the final state.
    assert "Pagamento realizado" in client.get("/comprador/projeto/pagamento").text
    detail = client.get(f"/admin/pagamentos/{payment.id}").text
    assert detail.count("(liberado)") == 2
