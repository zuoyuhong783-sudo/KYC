"""Bounded in-memory image loading and lazily cached CPU OCR engines."""

import io
import os
import warnings
from functools import lru_cache

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from errors import OcrExtractionError


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_SIDE = 2400


def prepare_image(data: bytes) -> Image.Image:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise OcrExtractionError("Image is empty or exceeds the 10 MiB OCR limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG"}:
                    raise OcrExtractionError("Image format must be JPEG or PNG")
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise OcrExtractionError("Image exceeds the 20 megapixel OCR limit")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                if "A" in oriented.getbands() or "transparency" in oriented.info:
                    rgba = oriented.convert("RGBA")
                    image = Image.new("RGB", rgba.size, "white")
                    image.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    image = oriented.convert("RGB")
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
        return image
    except OcrExtractionError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise OcrExtractionError("Image cannot be decoded as a complete JPEG or PNG") from None


@lru_cache(maxsize=1)
def _rapid_engine():
    from rapidocr_onnxruntime import RapidOCR

    # Avoid oversubscribing Lambda CPU. Models are bundled in the installed wheel.
    return RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)


@lru_cache(maxsize=1)
def _tesseract_engine():
    from tesserocr import PSM, PyTessBaseAPI

    return PyTessBaseAPI(path=os.environ["TESSDATA_PREFIX"], lang="chi_sim+eng", psm=PSM.SINGLE_BLOCK)


def recognize(data: bytes, *, engine: str = "rapidocr") -> str:
    image = prepare_image(data)
    try:
        if engine == "rapidocr":
            # RapidOCR ndarray input uses OpenCV's BGR channel order.
            result, _ = _rapid_engine()(np.asarray(image)[:, :, ::-1].copy())
            lines = [str(item[1]).strip() for item in result or [] if float(item[2]) >= 0.5]
            text = "\n".join(lines)
        elif engine == "tesseract":
            api = _tesseract_engine()
            api.SetImage(image)
            text = api.GetUTF8Text()
            api.Clear()
        else:
            raise ValueError("Unknown local OCR engine")
    except Exception:
        # OCR libraries may include recognized text in exceptions: never expose it
        # through Lambda errors/CloudWatch. Detailed engine diagnostics stay local.
        raise OcrExtractionError(f"OCR engine unavailable or inference failed: {engine}") from None
    if not text.strip():
        raise OcrExtractionError("No readable text; missing required OCR fields")
    return text
