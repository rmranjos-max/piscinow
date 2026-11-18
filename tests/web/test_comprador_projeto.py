from sqlalchemy import select

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus


def _confirm_project(db_session, comprador, product):
    # Projeto do caminho antigo (produto escolhido na vitrine), ainda legivel para dados existentes.
    project = db_session.scalar(select(Project).where(Project.member_id == comprador.id))
    if project is None:
        project = Project(member_id=comprador.id)
        db_session.add(project)
    project.product_id = product.id
    project.status = ProjectStatus.CONFIRMADO
    db_session.flush()
    return project


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


def test_projeto_never_creates_a_draft_and_explains_how_the_project_is_born(client, db_session):
    comprador = _comprador_logged_in(client, db_session)

    response = client.get("/comprador/projeto")

    assert response.status_code == 200
    assert db_session.query(Project).filter(Project.member_id == comprador.id).count() == 0
    assert "nasce quando você aceita a proposta" in response.text


def test_projeto_shows_the_accepted_proposal_with_its_items_and_the_payment_state(client, db_session):
    from piscinow.proposals.service import accept_proposal
    from tests.proposals.test_service import _approve_feasibility, _loja, _send, _setup

    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    accept_proposal(db_session, _send(db_session, decisions[loja.id]), buyer)
    buyer.email = "meu.projeto@example.com"
    buyer.set_password("senha-forte-123")
    db_session.flush()
    client.post("/comprador/login", data={"email": "meu.projeto@example.com", "password": "senha-forte-123"})

    page = client.get("/comprador/projeto").text

    assert "Studio Fibra Sul" in page and "Versão 1 aceita" in page
    assert "Piscina de fibra 7x3" in page and "R$ 21.000,00" in page
    assert "Em preparação" in page
    assert "ainda vai indicar o instalador" in page


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
    project = _confirm_project(db_session, comprador, product)
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
    _confirm_project(db_session, comprador, product)

    response = client.get("/comprador/projeto")

    assert response.status_code == 200
    assert "/comprador/projeto/pagamento" not in response.text
