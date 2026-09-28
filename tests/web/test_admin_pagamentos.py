from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus


def _logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def _confirmed_project(db_session, *, comprador_name="Marina Duarte"):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name=comprador_name, status=MemberStatus.APPROVED)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add_all([comprador, loja])
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    return project, product


def test_pagamentos_lists_confirmed_projects_without_payment(client, db_session):
    _logged_in(client, db_session)
    project, product = _confirmed_project(db_session)

    response = client.get("/admin/pagamentos")

    assert "Marina Duarte" in response.text
    assert "Piscina Fibra" in response.text


def test_pagamentos_hides_projects_that_already_have_payment(client, db_session):
    _logged_in(client, db_session)
    project, product = _confirmed_project(db_session, comprador_name="Ja Tem Pagamento")
    db_session.add(Payment(project_id=project.id, total_amount=18000))
    db_session.flush()

    response = client.get("/admin/pagamentos")

    assert "Ja Tem Pagamento" not in response.text


def test_pagamentos_hides_unconfirmed_projects(client, db_session):
    _logged_in(client, db_session)
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Rascunho Ainda", status=MemberStatus.APPROVED)
    db_session.add(comprador)
    db_session.flush()
    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()

    response = client.get("/admin/pagamentos")

    assert "Rascunho Ainda" not in response.text


def test_pagamentos_redirects_to_login_when_not_authenticated(client):
    response = client.get("/admin/pagamentos", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
