from piscinow.models.member import Member, ProfileType
from piscinow.models.product import Product, ProductKind


def test_product_persists_and_reloads(db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()

    product = Product(
        member_id=loja.id,
        kind=ProductKind.PISCINA,
        category="fibra",
        name="Piscina Fibra 6x3",
        price=18000.00,
        size_label="6x3m",
    )
    db_session.add(product)
    db_session.flush()
    db_session.expunge(product)

    reloaded = db_session.get(Product, product.id)

    assert reloaded.name == "Piscina Fibra 6x3"
    assert reloaded.category == "fibra"
    assert reloaded.active is True
    assert reloaded.member_id == loja.id
