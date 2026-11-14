import io

import pytest
from PIL import Image

from piscinow.media.images import MAX_UPLOAD_BYTES, ImageError, process_image


def _image_bytes(size=(2400, 1200), fmt="JPEG", color=(20, 110, 170), exif=None, mode="RGB"):
    buffer = io.BytesIO()
    image = Image.new(mode, size, color if mode == "RGB" else (20, 110, 170, 128))
    params = {"exif": exif} if exif else {}
    image.save(buffer, fmt, **params)
    return buffer.getvalue()


def _open(data):
    return Image.open(io.BytesIO(data))


def test_a_large_photo_is_resized_and_a_thumbnail_is_made_both_as_jpeg():
    result = process_image(_image_bytes((2400, 1200)))

    full, thumb = _open(result.full), _open(result.thumb)
    assert full.format == "JPEG" and thumb.format == "JPEG"
    assert full.size == (1600, 800)
    assert thumb.size == (480, 240)
    assert result.content_type == "image/jpeg"


def test_a_small_photo_is_never_enlarged():
    result = process_image(_image_bytes((300, 200)))

    assert _open(result.full).size == (300, 200)
    assert _open(result.thumb).size == (300, 200)


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_png_and_webp_are_accepted_and_converted(fmt):
    result = process_image(_image_bytes((800, 600), fmt=fmt))

    assert _open(result.full).format == "JPEG"


def test_transparency_is_flattened_on_white_instead_of_turning_black():
    result = process_image(_image_bytes((100, 100), fmt="PNG", mode="RGBA"))

    red, green, blue = _open(result.full).getpixel((50, 50))
    assert red > 100 and green > 150 and blue > 180  # blended with white, not with black


def test_location_and_camera_metadata_are_removed():
    exif = Image.Exif()
    exif[0x010F] = "Fabricante"   # Make
    exif[0x8825] = {1: "S", 2: (22, 54, 0)}  # GPS IFD
    result = process_image(_image_bytes((800, 600), exif=exif.tobytes()))

    assert len(_open(result.full).getexif()) == 0
    assert len(_open(result.thumb).getexif()) == 0


def test_a_sideways_phone_photo_is_stored_upright():
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise to display
    result = process_image(_image_bytes((800, 400), exif=exif.tobytes()))

    assert _open(result.full).size == (400, 800)


@pytest.mark.parametrize("data", [b"", b"isto nao e uma imagem", b"%PDF-1.7 documento", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"])
def test_files_that_are_not_photos_are_refused_whatever_their_name(data):
    with pytest.raises(ImageError):
        process_image(data)


def test_a_gif_is_refused():
    with pytest.raises(ImageError) as raised:
        process_image(_image_bytes((50, 50), fmt="GIF"))

    assert "JPG, PNG ou WebP" in str(raised.value)


def test_a_file_over_the_size_limit_is_refused_before_being_decoded():
    with pytest.raises(ImageError) as raised:
        process_image(b"\xff\xd8" + b"0" * MAX_UPLOAD_BYTES)

    assert "8 MB" in str(raised.value)


def test_an_absurdly_large_canvas_is_refused():
    with pytest.raises(ImageError):
        process_image(_image_bytes((13000, 100), fmt="PNG"))


def test_a_truncated_file_is_refused_cleanly():
    with pytest.raises(ImageError):
        process_image(_image_bytes((800, 600))[:200])


def test_a_photo_over_the_pixel_limit_is_refused_from_its_header_before_decoding():
    # 42 megapixels in a 1-bit PNG: a tiny file that would be large once decoded.
    buffer = io.BytesIO()
    Image.new("1", (7000, 6000)).save(buffer, "PNG")

    with pytest.raises(ImageError) as raised:
        process_image(buffer.getvalue())

    assert "grande demais" in str(raised.value)


def test_a_large_phone_photo_under_the_limit_still_works():
    result = process_image(_image_bytes((6000, 4000)))  # 24 megapixels

    assert _open(result.full).size == (1600, 1067)
