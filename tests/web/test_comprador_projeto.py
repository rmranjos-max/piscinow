from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus


def _comprador_logged_in(client, db_session, *, email="comprador@example.com", password="senha-forte-123"):
    comprador = Member(
        profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED, email=email
    )
    comprador.set_password(password)
    db_session.add(comprador)
    db_session.flush()
    client.post("/comprador/login", data={"email": email, "password": password})
    return comprador


def test_projeto_redirects_to_login_when_not_authenticated(client):
    response = client.get("/comprador/projeto", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"


def test_projeto_creates_draft_on_first_visit(client, db_session):
    comprador = _comprador_logged_in(client, db_session)

    response = client.get("/comprador/projeto")

    assert response.status_code == 200
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    assert project.status.value == "rascunho"


def test_escolher_produto_sets_product_on_project(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()

    response = client.post(
        "/comprador/projeto/produto", data={"product_id": str(product.id)}, follow_redirects=False
    )

    assert response.status_code == 303
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    assert project.product_id == product.id


def test_escolher_produto_inativo_retorna_404(client, db_session):
    _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(
        member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Inativo", price=1000, active=False
    )
    db_session.add(product)
    db_session.flush()

    response = client.post("/comprador/projeto/produto", data={"product_id": str(product.id)})

    assert response.status_code == 404


def test_escolher_produto_id_malformado_retorna_404(client, db_session):
    _comprador_logged_in(client, db_session)

    response = client.post("/comprador/projeto/produto", data={"product_id": "nao-e-um-uuid"})

    assert response.status_code == 404


def test_projeto_shows_payment_link_when_confirmed_with_payment(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    db_session.add(Payment(project_id=project.id, total_amount=18000))
    db_session.flush()

    response = client.get("/comprador/projeto")

    assert response.status_code == 200
    assert "/comprador/projeto/pagamento" in response.text


def test_projeto_hides_payment_link_when_confirmed_without_payment(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()

    response = client.get("/comprador/projeto")

    assert response.status_code == 200
    assert "/comprador/projeto/pagamento" not in response.text
