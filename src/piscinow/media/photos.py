from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.media.images import ImageError, process_image
from piscinow.media.storage import MediaStorage, new_key
from piscinow.models.media import ProductPhoto
from piscinow.models.product import Product

MAX_PHOTOS_PER_PRODUCT = 5


class PhotoError(ValueError):
    """Something the person can fix: wrong file, too many photos. The message is for them."""


def photos_of(db: Session, product_id) -> list[ProductPhoto]:
    return list(db.scalars(
        select(ProductPhoto).where(ProductPhoto.product_id == product_id)
        .order_by(ProductPhoto.position, ProductPhoto.created_at)
    ))


def add_photo(db: Session, storage: MediaStorage, product: Product, raw: bytes) -> ProductPhoto:
    existing = photos_of(db, product.id)
    if len(existing) >= MAX_PHOTOS_PER_PRODUCT:
        raise PhotoError(f"Cada produto pode ter até {MAX_PHOTOS_PER_PRODUCT} fotos. Remova uma para enviar outra.")
    try:
        processed = process_image(raw)
    except ImageError as exc:
        raise PhotoError(str(exc)) from exc

    key, thumb_key = new_key("produtos"), new_key("produtos/miniaturas")
    storage.save(key, processed.full, processed.content_type)
    try:
        storage.save(thumb_key, processed.thumb, processed.content_type)
    except Exception:
        storage.delete(key)  # do not leave half an upload behind
        raise
    photo = ProductPhoto(
        product_id=product.id, key=key, thumb_key=thumb_key,
        position=max((p.position for p in existing), default=-1) + 1,
    )
    db.add(photo)
    db.flush()
    return photo


def remove_photo(db: Session, storage: MediaStorage, photo: ProductPhoto) -> None:
    key, thumb_key = photo.key, photo.thumb_key
    db.delete(photo)
    db.flush()
    # The row goes first: a file without a row is harmless, a row without a file is a broken image.
    storage.delete(key)
    storage.delete(thumb_key)


def make_cover(db: Session, photo: ProductPhoto) -> None:
    lowest = min(p.position for p in photos_of(db, photo.product_id))
    photo.position = lowest - 1
    db.flush()


def cover_urls(db: Session, storage: MediaStorage, product_ids) -> dict:
    """Thumbnail of the cover photo of each product that has one."""
    ids = list(product_ids)
    if not ids:
        return {}
    covers: dict = {}
    for photo in db.scalars(
        select(ProductPhoto).where(ProductPhoto.product_id.in_(ids))
        .order_by(ProductPhoto.position, ProductPhoto.created_at)
    ):
        covers.setdefault(photo.product_id, storage.url(photo.thumb_key))
    return covers
