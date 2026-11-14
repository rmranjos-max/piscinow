import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from piscinow.media.photos import MAX_PHOTOS_PER_PRODUCT, photos_of
from piscinow.media.storage import MemoryMediaStorage, StorageError
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.product import Product, ProductKind
from piscinow.web.app import create_app


def _jpeg(size=(900, 600), color=(20, 110, 170)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "JPEG")
    return buffer.getvalue()


def _loja(client, db_session, *, email="loja@example.com", name="Studio Fibra Sul", login=True):
    loja = Member(profile_type=ProfileType.LOJA, name=name, status=MemberStatus.APPROVED, email=email, region="Valinhos")
    loja.set_password("senha-forte-123")
    db_session.add(loja)
    db_session.flush()
    if login:
        client.post("/loja/login", data={"email": email, "password": "senha-forte-123"})
    return loja


def _product(db_session, loja, name="Piscina Fibra 7x3"):
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name=name, price=18000)
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture()
def storage(client):
    client.app.state.media_storage = MemoryMediaStorage()
    return client.app.state.media_storage


def _upload(client, product, data=None, filename="foto.jpg", content_type="image/jpeg", **kwargs):
    return client.post(
        f"/loja/produtos/{product.id}/fotos",
        files={"foto": (filename, data if data is not None else _jpeg(), content_type)}, **kwargs,
    )


def test_uploading_requires_a_store_login(client, db_session, storage):
    loja = _loja(client, db_session, login=False)
    product = _product(db_session, loja)

    response = _upload(client, product, follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/loja/login"
    assert storage.files == {}


def test_a_store_uploads_a_photo_and_sees_it_with_a_confirmation(client, db_session, storage):
    loja = _loja(client, db_session)
    product = _product(db_session, loja)

    response = _upload(client, product, follow_redirects=True)

    assert response.status_code == 200
    [photo] = photos_of(db_session, product.id)
    assert set(storage.files) == {photo.key, photo.thumb_key}
    assert "Foto enviada." in response.text
    assert f'src="/midia/{photo.thumb_key}"' in response.text
    assert "Capa" in response.text


def test_the_stored_file_is_our_own_jpeg_and_never_the_uploaded_name(client, db_session, storage):
    loja = _loja(client, db_session)
    product = _product(db_session, loja)

    _upload(client, product, filename="../../segredo.php", content_type="application/x-php")

    [photo] = photos_of(db_session, product.id)
    assert "segredo" not in photo.key and photo.key.endswith(".jpg")
    assert Image.open(io.BytesIO(storage.files[photo.key])).format == "JPEG"


@pytest.mark.parametrize("data", [b"<?php echo 1; ?>", b"", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>"])
def test_a_file_that_is_not_a_photo_is_refused_with_the_error_next_to_the_field(client, db_session, storage, data):
    loja = _loja(client, db_session)
    product = _product(db_session, loja)

    response = _upload(client, product, data=data)

    assert response.status_code == 400
    assert 'id="foto-erro"' in response.text
    assert photos_of(db_session, product.id) == [] and storage.files == {}


def test_a_product_takes_at_most_five_photos(client, db_session, storage):
    loja = _loja(client, db_session)
    product = _product(db_session, loja)
    for _ in range(MAX_PHOTOS_PER_PRODUCT):
        assert _upload(client, product, follow_redirects=False).status_code == 303

    response = _upload(client, product)

    assert response.status_code == 400
    assert len(photos_of(db_session, product.id)) == MAX_PHOTOS_PER_PRODUCT
    assert "Limite de 5 fotos atingido" in client.get(f"/loja/produtos/{product.id}/editar").text


def test_a_store_cannot_touch_another_stores_product_photos(client, db_session, storage):
    other = _loja(client, db_session, email="outra@example.com", name="Outra", login=False)
    theirs = _product(db_session, other, "Produto alheio")
    mine = _loja(client, db_session)
    client.app.state.media_storage = storage
    from piscinow.media.photos import add_photo
    photo = add_photo(db_session, storage, theirs, _jpeg())

    assert _upload(client, theirs).status_code == 404
    assert client.post(f"/loja/produtos/{theirs.id}/fotos/{photo.id}/remover").status_code == 404
    assert client.post(f"/loja/produtos/{theirs.id}/fotos/{photo.id}/capa").status_code == 404
    # A photo id of another product does not work through my own product's address either.
    my_product = _product(db_session, mine, "Meu produto")
    assert client.post(f"/loja/produtos/{my_product.id}/fotos/{photo.id}/remover").status_code == 404
    assert len(photos_of(db_session, theirs.id)) == 1 and len(storage.files) == 2


def test_removing_a_photo_deletes_the_row_and_both_files(client, db_session, storage):
    loja = _loja(client, db_session)
    product = _product(db_session, loja)
    _upload(client, product)
    [photo] = photos_of(db_session, product.id)

    response = client.post(f"/loja/produtos/{product.id}/fotos/{photo.id}/remover", follow_redirects=True)

    assert "Foto removida." in response.text
    assert photos_of(db_session, product.id) == [] and storage.files == {}


def test_another_photo_can_become_the_cover(client, db_session, storage):
    loja = _loja(client, db_session)
    product = _product(db_session, loja)
    _upload(client, product)
    _upload(client, product, data=_jpeg(color=(200, 30, 30)))
    first, second = photos_of(db_session, product.id)

    client.post(f"/loja/produtos/{product.id}/fotos/{second.id}/capa")

    assert [p.id for p in photos_of(db_session, product.id)] == [second.id, first.id]


def test_malformed_ids_are_a_404_not_a_crash(client, db_session, storage):
    loja = _loja(client, db_session)
    product = _product(db_session, loja)

    assert _upload(client, type("P", (), {"id": "nao-uuid"})).status_code == 404
    assert client.post(f"/loja/produtos/{product.id}/fotos/nao-uuid/remover").status_code == 404


def test_a_storage_failure_is_reported_plainly_and_leaves_no_row(client, db_session):
    class Broken(MemoryMediaStorage):
        def save(self, key, data, content_type):
            raise StorageError("Não foi possível guardar a foto agora. Tente novamente.")

    client.app.state.media_storage = Broken()
    loja = _loja(client, db_session)
    product = _product(db_session, loja)

    response = _upload(client, product)

    assert response.status_code == 502
    assert "Não foi possível guardar a foto agora" in response.text
    assert photos_of(db_session, product.id) == []


def test_the_vitrine_shows_the_cover_photo_and_a_placeholder_for_products_without_one(client, db_session, storage):
    loja = _loja(client, db_session)
    with_photo, without = _product(db_session, loja, "Com Foto"), _product(db_session, loja, "Sem Foto Ainda")
    _upload(client, with_photo)
    [photo] = photos_of(db_session, with_photo.id)

    page = client.get("/vitrine/produtos").text

    assert f'src="/midia/{photo.thumb_key}"' in page
    assert 'alt="Foto de Com Foto"' in page
    assert "Produto ainda sem foto" in page


def test_uploads_are_off_in_production_while_photos_would_stay_on_the_server_disk(monkeypatch):
    monkeypatch.setenv("PISCINOW_ENVIRONMENT", "production")
    monkeypatch.setenv("PISCINOW_SESSION_SECRET", "s" * 40)
    app = create_app()

    assert app.state.media_enabled is False


def test_local_photos_are_served_as_jpeg_and_unknown_or_escaping_keys_are_404(monkeypatch, tmp_path):
    monkeypatch.setenv("PISCINOW_MEDIA_LOCAL_DIR", str(tmp_path))
    app = create_app()
    app.state.media_storage.save("produtos/abc.jpg", _jpeg(), "image/jpeg")
    local = TestClient(app)

    ok = local.get("/midia/produtos/abc.jpg")
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/jpeg"
    assert ok.headers["x-content-type-options"] == "nosniff"
    assert local.get("/midia/produtos/nao-existe.jpg").status_code == 404
    assert local.get("/midia/..%2F..%2Fpyproject.toml").status_code == 404
