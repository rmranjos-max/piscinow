from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStage, PaymentStatus
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus
from piscinow.payment.payment_provider import PaymentProviderError
from piscinow.payment.providers.fake_provider import FakePaymentProvider
from piscinow.web.deps import get_payment_provider
from tests.web.test_admin_pagamentos import _logged_in


class _FailAfterNReleases(FakePaymentProvider):
    """Succeeds on the first `fail_after` release() calls, then fails every call after that.

    Used to simulate a provider that dies mid-loop, after already moving money
    for earlier allocations in the same stage - the scenario Finding 2 is about.
    """

    def __init__(self, *, fail_after: int):
        super().__init__()
        self._fail_after = fail_after

    async def release(self, *, charge_id, amount, external_reference):
        if len(self.releases) >= self._fail_after:
            raise PaymentProviderError("simulated release failure")
        return await super().release(charge_id=charge_id, amount=amount, external_reference=external_reference)


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


def _paid_payment_with_two_allocations(db_session, *, stage=PaymentStage.ESTRUTURA):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add_all([comprador, loja, prestador])
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    payment = Payment(
        project_id=project.id, total_amount=21000, status=PaymentStatus.PAGO, external_charge_id="fake-charge-x"
    )
    db_session.add(payment)
    db_session.flush()
    allocation_1 = PaymentAllocation(
        payment_id=payment.id, stage=stage, recipient_member_id=loja.id, product_id=product.id, amount=18000
    )
    allocation_2 = PaymentAllocation(
        payment_id=payment.id, stage=stage, recipient_member_id=prestador.id, amount=3000
    )
    db_session.add_all([allocation_1, allocation_2])
    db_session.flush()
    return payment, allocation_1, allocation_2


def test_liberar_fase_always_failing_provider_keeps_all_allocations_retido(client, db_session):
    """With should_fail_release=True every release() call fails, including the
    first - so nothing should be committed as LIBERADO and no transfer should
    be recorded at the provider. This is the literal FakePaymentProvider(
    should_fail_release=True) configuration named in the fix-wave brief."""
    _logged_in(client, db_session)
    payment, allocation_1, allocation_2 = _paid_payment_with_two_allocations(db_session)
    provider = FakePaymentProvider(should_fail_release=True)
    client.app.dependency_overrides[get_payment_provider] = lambda: provider

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar")

    assert response.status_code == 400
    assert "Nao foi possivel liberar todos os itens desta fase" in response.text
    db_session.refresh(allocation_1)
    db_session.refresh(allocation_2)
    assert allocation_1.status == AllocationStatus.RETIDO
    assert allocation_2.status == AllocationStatus.RETIDO
    assert provider.releases == []


def test_liberar_fase_stops_after_mid_loop_failure_and_keeps_prior_release(client, db_session):
    """When the provider fails partway through the stage's allocations, the
    allocation(s) already released before the failure must stay LIBERADO
    (committed individually) and the provider's release log must reflect only
    the call(s) that actually succeeded - no double-release risk on retry."""
    _logged_in(client, db_session)
    payment, allocation_1, allocation_2 = _paid_payment_with_two_allocations(db_session)
    provider = _FailAfterNReleases(fail_after=1)
    client.app.dependency_overrides[get_payment_provider] = lambda: provider

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar")

    assert response.status_code == 400
    assert "Nao foi possivel liberar todos os itens desta fase" in response.text
    db_session.refresh(allocation_1)
    db_session.refresh(allocation_2)
    statuses = {allocation_1.status, allocation_2.status}
    assert statuses == {AllocationStatus.LIBERADO, AllocationStatus.RETIDO}
    assert len(provider.releases) == 1
