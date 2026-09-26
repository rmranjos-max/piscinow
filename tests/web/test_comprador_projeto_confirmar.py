from piscinow.models.member import Member, ProfileType
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project
from tests.web.test_comprador_projeto import _comprador_logged_in


def test_confirmar_sem_produto_mostra_erro(client, db_session):
    _comprador_logged_in(client, db_session)
    client.get("/comprador/projeto")

    response = client.post("/comprador/projeto/confirmar")

    assert response.status_code == 400
    assert "Escolha um produto" in response.text


def test_confirmar_com_produto_muda_status(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    client.post("/comprador/projeto/produto", data={"product_id": str(product.id)})

    response = client.post("/comprador/projeto/confirmar", follow_redirects=False)

    assert response.status_code == 303
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    assert project.status.value == "confirmado"


def test_alterar_produto_apos_confirmar_retorna_400(client, db_session):
    _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    outro_produto = Product(
        member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Outra Piscina", price=20000
    )
    db_session.add_all([product, outro_produto])
    db_session.flush()
    client.post("/comprador/projeto/produto", data={"product_id": str(product.id)})
    client.post("/comprador/projeto/confirmar")

    response = client.post("/comprador/projeto/produto", data={"product_id": str(outro_produto.id)})

    assert response.status_code == 400
