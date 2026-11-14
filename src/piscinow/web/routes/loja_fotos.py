import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from piscinow.loja_auth import require_loja
from piscinow.media.images import MAX_UPLOAD_BYTES
from piscinow.media.photos import PhotoError, add_photo, make_cover, remove_photo
from piscinow.media.storage import StorageError
from piscinow.models.media import ProductPhoto
from piscinow.models.member import Member
from piscinow.models.product import Product
from piscinow.web.deps import get_db
from piscinow.web.photo_context import photo_context

router = APIRouter(prefix="/loja/produtos")
logger = logging.getLogger(__name__)


def _owned_product(db: Session, product_id: str, loja: Member) -> Product:
    try:
        product = db.get(Product, uuid.UUID(product_id))
    except ValueError:
        product = None
    if product is None or product.member_id != loja.id:
        raise HTTPException(status_code=404)
    return product


def _owned_photo(db: Session, photo_id: str, product: Product) -> ProductPhoto:
    try:
        photo = db.get(ProductPhoto, uuid.UUID(photo_id))
    except ValueError:
        photo = None
    # The photo must belong to this very product, which already belongs to this store.
    if photo is None or photo.product_id != product.id:
        raise HTTPException(status_code=404)
    return photo


def _require_media(request: Request) -> None:
    if not request.app.state.media_enabled:
        raise HTTPException(status_code=503, detail="Envio de fotos indisponível no momento.")


def _page_with_error(request: Request, db: Session, product: Product, message: str, status_code: int = 400):
    context = {"product": product, "error": None, **photo_context(request, db, product), "photo_error": message}
    return request.app.state.templates.TemplateResponse(
        request, "loja_produto_editar.html", context, status_code=status_code
    )


def _back(product: Product, notice: str) -> RedirectResponse:
    return RedirectResponse(url=f"/loja/produtos/{product.id}/editar?foto={notice}#fotos", status_code=303)


@router.post("/{product_id}/fotos")
async def enviar_foto(
    request: Request,
    product_id: str,
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    _require_media(request)
    product = _owned_product(db, product_id, loja)
    # One byte past the limit is enough to know it is too big, without holding a huge file in memory.
    raw = await foto.read(MAX_UPLOAD_BYTES + 1)
    try:
        add_photo(db, request.app.state.media_storage, product, raw)
    except PhotoError as exc:
        return _page_with_error(request, db, product, str(exc))
    except StorageError as exc:
        logger.exception("Photo upload failed for product %s", product.id)
        return _page_with_error(request, db, product, str(exc), status_code=502)
    return _back(product, "enviada")


@router.post("/{product_id}/fotos/{photo_id}/remover")
async def remover_foto(
    request: Request,
    product_id: str,
    photo_id: str,
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    _require_media(request)
    product = _owned_product(db, product_id, loja)
    photo = _owned_photo(db, photo_id, product)
    try:
        remove_photo(db, request.app.state.media_storage, photo)
    except StorageError:
        # The row is already gone, so the photo no longer shows; the orphan file is only wasted space.
        logger.exception("Photo file removal failed for product %s", product.id)
    return _back(product, "removida")


@router.post("/{product_id}/fotos/{photo_id}/capa")
async def definir_capa(
    request: Request,
    product_id: str,
    photo_id: str,
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    product = _owned_product(db, product_id, loja)
    make_cover(db, _owned_photo(db, photo_id, product))
    return _back(product, "capa")
