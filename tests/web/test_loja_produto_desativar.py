from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.product import Product, ProductKind
from tests.web.test_loja_produtos import _loja_logged_in


def test_desativar_produto_sets_active_false(client, db_session):
    loja = _loja_logged_in(client, db_session)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina X", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.post(f"/loja/produtos/{product.id}/desativar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(product)
    assert product.active is False


def test_desativar_produto_de_outra_loja_retorna_404(client, db_session):
    _loja_logged_in(client, db_session, email="loja1@example.com")

    outra_loja = Member(profile_type=ProfileType.LOJA, name="Outra Loja", status=MemberStatus.APPROVED)
    db_session.add(outra_loja)
    db_session.flush()
    product = Product(member_id=outra_loja.id, kind=ProductKind.PISCINA, category="fibra", name="Nao Meu", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.post(f"/loja/produtos/{product.id}/desativar")

    assert response.status_code == 404
