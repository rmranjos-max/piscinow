import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SIDE_PIXELS = 12000
FULL_SIDE = 1600
THUMB_SIDE = 480
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# A decoded image this large is refused by Pillow itself (decompression-bomb guard).
Image.MAX_IMAGE_PIXELS = 40_000_000


class ImageError(ValueError):
    """The upload is not a photo we accept. The message is written for the person uploading."""


@dataclass(frozen=True)
class ProcessedImage:
    full: bytes
    thumb: bytes
    content_type: str = "image/jpeg"


def _encode(image: Image.Image, side: int) -> bytes:
    copy = image.copy()
    copy.thumbnail((side, side), Image.LANCZOS)  # never enlarges
    buffer = io.BytesIO()
    copy.save(buffer, "JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def process_image(raw: bytes) -> ProcessedImage:
    """Validate an uploaded photo by its content and re-encode it.

    The stored files are always new JPEGs written by us: nothing of the original file (its
    metadata, GPS position, or anything hidden in it) is kept, and the name or declared type of
    the upload is never trusted.
    """
    if not raw:
        raise ImageError("Escolha um arquivo de foto.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageError("A foto deve ter no máximo 8 MB.")
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in ALLOWED_FORMATS:
            raise ImageError("Envie uma foto em JPG, PNG ou WebP.")
        if max(image.size) > MAX_SIDE_PIXELS:
            raise ImageError("A foto é grande demais. Envie uma versão menor.")
        image.load()
    except ImageError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError):
        raise ImageError("Não foi possível ler este arquivo como foto. Envie em JPG, PNG ou WebP.")

    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    else:
        image = image.convert("RGB")
    return ProcessedImage(full=_encode(image, FULL_SIDE), thumb=_encode(image, THUMB_SIDE))
