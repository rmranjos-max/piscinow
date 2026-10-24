import pytest
from sqlalchemy.exc import IntegrityError

from piscinow.models.member import Member, ProfileType
from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStage, PaymentStatus
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project


def test_payment_persists_with_default_status(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    db_session.add(comprador)
    db_session.flush()
    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()

    payment = Payment(project_id=project.id, total_amount=21000)
    db_session.add(payment)
    db_session.flush()
    db_session.expunge(payment)

    reloaded = db_session.get(Payment, payment.id)
    assert reloaded.status == PaymentStatus.PENDENTE
    assert reloaded.external_charge_id is None
    assert reloaded.paid_at is None


def test_payment_project_id_is_unique(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    db_session.add(comprador)
    db_session.flush()
    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()

    payment_a = Payment(project_id=project.id, total_amount=21000)
    db_session.add(payment_a)
    db_session.flush()

    payment_b = Payment(project_id=project.id, total_amount=5000)
    db_session.add(payment_b)
    with pytest.raises(IntegrityError):
        db_session.flush()


def _payment_with_loja(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add_all([comprador, loja])
    db_session.flush()
    project = Project(member_id=comprador.id)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add_all([project, product])
    db_session.flush()
    payment = Payment(project_id=project.id, total_amount=18000)
    db_session.add(payment)
    db_session.flush()
    return payment, loja, product


def test_payment_allocation_requires_exactly_one_of_product_or_service(db_session):
    payment, loja, product = _payment_with_loja(db_session)

    db_session.add(
        PaymentAllocation(payment_id=payment.id, stage=PaymentStage.ESTRUTURA, recipient_member_id=loja.id, amount=100)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_payment_allocation_links_payment_to_recipient_and_product(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add_all([comprador, loja])
    db_session.flush()
    project = Project(member_id=comprador.id)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add_all([project, product])
    db_session.flush()
    payment = Payment(project_id=project.id, total_amount=18000)
    db_session.add(payment)
    db_session.flush()

    allocation = PaymentAllocation(
        payment_id=payment.id,
        stage=PaymentStage.ESTRUTURA,
        recipient_member_id=loja.id,
        product_id=product.id,
        amount=18000,
    )
    db_session.add(allocation)
    db_session.flush()
    db_session.expunge(allocation)

    reloaded = db_session.get(PaymentAllocation, allocation.id)
    assert reloaded.status == AllocationStatus.RETIDO
    assert reloaded.service_id is None
    assert reloaded.released_at is None
