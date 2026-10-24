from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment, PaymentAllocation, PaymentStage
from piscinow.models.product import Product, ProductKind
from tests.web.test_comprador_projeto import _comprador_logged_in, _confirm_project


def _confirmed_project_with_payment(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = _confirm_project(db_session, comprador, product)
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
    return comprador, payment


def test_ver_pagamento_shows_cronograma(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)

    response = client.get("/comprador/projeto/pagamento")

    assert response.status_code == 200
    assert "18.000,00" in response.text


def test_ver_pagamento_returns_404_when_no_payment_yet(client, db_session):
    _comprador_logged_in(client, db_session)

    response = client.get("/comprador/projeto/pagamento")

    assert response.status_code == 404


def test_ver_pagamento_redirects_to_login_when_not_authenticated(client):
    response = client.get("/comprador/projeto/pagamento", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"
