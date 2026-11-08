import io

import pytest
from PIL import Image

from errors import OcrExtractionError
from ocr_engine import MAX_IMAGE_BYTES, prepare_image


@pytest.mark.parametrize("format", ["JPEG", "PNG"])
def test_valid_images_converted_to_rgb(format):
    stream = io.BytesIO()
    Image.new("L", (200, 100), 255).save(stream, format=format)
    image = prepare_image(stream.getvalue())
    assert image.mode == "RGB"
    assert image.size == (200, 100)


@pytest.mark.parametrize("data", [b"", b"this is not a jpg", b"\xff\xd8\xff\xe0broken", b"x" * (MAX_IMAGE_BYTES + 1)])
def test_invalid_image_bytes(data):
    with pytest.raises(OcrExtractionError):
        prepare_image(data)


def test_gif_is_not_accepted_even_if_decodable():
    stream = io.BytesIO()
    Image.new("RGB", (20, 20)).save(stream, format="GIF")
    with pytest.raises(OcrExtractionError, match="format"):
        prepare_image(stream.getvalue())


def test_oversized_pixel_dimensions():
    stream = io.BytesIO()
    Image.new("1", (5000, 5000)).save(stream, format="PNG")
    with pytest.raises(OcrExtractionError, match="megapixel"):
        prepare_image(stream.getvalue())


def test_resize_preserves_aspect_ratio():
    stream = io.BytesIO()
    Image.new("RGB", (3000, 1500)).save(stream, format="JPEG")
    assert prepare_image(stream.getvalue()).size == (2400, 1200)


def test_transparent_background_is_composited_on_white():
    source = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    source.putpixel((5, 5), (0, 0, 0, 255))
    stream = io.BytesIO()
    source.save(stream, format="PNG")
    image = prepare_image(stream.getvalue())
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getpixel((5, 5)) == (0, 0, 0)
