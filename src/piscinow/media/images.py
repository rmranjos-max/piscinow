import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SIDE_PIXELS = 12000
# About a 40-megapixel photo. Decoding costs several bytes per pixel, so this bounds memory per upload.
MAX_PIXELS = 40_000_000
FULL_SIDE = 1600
THUMB_SIDE = 480
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Second line of defence only: Pillow raises at twice this value. MAX_PIXELS is the real limit.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


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
        # Checked from the header, before any pixel is decoded. Pillow's own guard only raises at
        # twice its limit, so the count is enforced here.
        if max(image.size) > MAX_SIDE_PIXELS or image.width * image.height > MAX_PIXELS:
            raise ImageError("A foto é grande demais. Envie uma versão menor.")
        if image.format == "JPEG":
            # Lets the decoder shrink a large JPEG while reading it, instead of holding it all in memory.
            image.draft("RGB", (FULL_SIDE * 2, FULL_SIDE * 2))
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
