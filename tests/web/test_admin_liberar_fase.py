from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStage, PaymentStatus
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus
from piscinow.payment.providers.fake_provider import FakePaymentProvider
from piscinow.web.deps import get_payment_provider
from tests.web.test_admin_pagamentos import _logged_in


def _paid_payment_with_allocation(db_session, *, stage=PaymentStage.ESTRUTURA, status=PaymentStatus.PAGO):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add_all([comprador, loja])
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    payment = Payment(project_id=project.id, total_amount=18000, status=status, external_charge_id="fake-charge-x")
    db_session.add(payment)
    db_session.flush()
    allocation = PaymentAllocation(
        payment_id=payment.id, stage=stage, recipient_member_id=loja.id, product_id=product.id, amount=18000
    )
    db_session.add(allocation)
    db_session.flush()
    return payment, allocation


def test_liberar_fase_releases_allocation_and_calls_provider(client, db_session):
    admin_user = _logged_in(client, db_session)
    payment, allocation = _paid_payment_with_allocation(db_session)

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(allocation)
    assert allocation.status == AllocationStatus.LIBERADO
    assert allocation.external_transfer_id is not None
    assert allocation.released_by == admin_user.email


def test_liberar_fase_rejects_unpaid_payment(client, db_session):
    _logged_in(client, db_session)
    payment, allocation = _paid_payment_with_allocation(db_session, status=PaymentStatus.PENDENTE)

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar")

    assert response.status_code == 400
    db_session.refresh(allocation)
    assert allocation.status == AllocationStatus.RETIDO


def test_liberar_fase_is_idempotent(client, db_session):
    _logged_in(client, db_session)
    payment, allocation = _paid_payment_with_allocation(db_session)
    provider = FakePaymentProvider()
    client.app.dependency_overrides[get_payment_provider] = lambda: provider

    client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar")
    client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar")

    assert len(provider.releases) == 1


def test_liberar_fase_rejects_invalid_stage_name(client, db_session):
    _logged_in(client, db_session)
    payment, allocation = _paid_payment_with_allocation(db_session)

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/nao-existe/liberar")

    assert response.status_code == 404
