from fastapi import Request
from sqlalchemy.orm import Session

from piscinow.media.photos import MAX_PHOTOS_PER_PRODUCT, photos_of
from piscinow.models.product import Product


def photo_context(request: Request, db: Session, product: Product) -> dict:
    """What the product edit page needs to show and manage the product's photos."""
    storage = request.app.state.media_storage
    photos = photos_of(db, product.id)
    return {
        "photos": [
            {"id": photo.id, "thumb": storage.url(photo.thumb_key), "cover": index == 0}
            for index, photo in enumerate(photos)
        ],
        "photo_limit": MAX_PHOTOS_PER_PRODUCT,
        "can_add_photo": len(photos) < MAX_PHOTOS_PER_PRODUCT,
        "media_enabled": request.app.state.media_enabled,
        "photo_error": None,
        "photo_notice": request.query_params.get("foto"),
    }
