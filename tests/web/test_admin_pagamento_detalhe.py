import uuid

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment, PaymentAllocation, PaymentStage
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus
from tests.web.test_admin_pagamentos import _logged_in


def test_pagamento_detalhe_shows_allocations_grouped_by_stage(client, db_session):
    _logged_in(client, db_session)
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
    payment = Payment(project_id=project.id, total_amount=18000)
    db_session.add(payment)
    db_session.flush()
    db_session.add(
        PaymentAllocation(
            payment_id=payment.id,
            stage=PaymentStage.ESTRUTURA,
            recipient_member_id=loja.id,
            product_id=product.id,
            amount=18000,
        )
    )
    db_session.flush()

    response = client.get(f"/admin/pagamentos/{payment.id}")

    assert response.status_code == 200
    assert "Studio Fibra Sul" in response.text
    assert "Estrutura" in response.text


def test_pagamento_detalhe_returns_404_for_unknown_payment(client, db_session):
    _logged_in(client, db_session)

    response = client.get(f"/admin/pagamentos/{uuid.uuid4()}")

    assert response.status_code == 404


def test_pagamento_detalhe_redirects_to_login_when_not_authenticated(client):
    response = client.get(f"/admin/pagamentos/{uuid.uuid4()}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
