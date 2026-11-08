"""Offline CLI using the same image and extraction path as Lambda."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from errors import OcrExtractionError
from extraction import extract_fields
from ocr_engine import MAX_IMAGE_BYTES, recognize


def main():
    parser = argparse.ArgumentParser(description="VeriCloud B: local OCR (no AWS required)")
    parser.add_argument("image", type=Path)
    parser.add_argument("--engine", choices=("rapidocr", "tesseract"), default="rapidocr")
    parser.add_argument("--today", type=date.fromisoformat, help="Fixed evaluation date for reproducible tests")
    parser.add_argument("--raw", action="store_true", help="LOCAL ONLY: print raw text; use synthetic samples only")
    args = parser.parse_args()
    try:
        with args.image.open("rb") as stream:
            text = recognize(stream.read(MAX_IMAGE_BYTES + 1), engine=args.engine)
        if args.raw:
            print(text)
        else:
            print(json.dumps(extract_fields(text, today=args.today), ensure_ascii=False, indent=2))
        return 0
    except (OcrExtractionError, OSError) as exc:
        message = str(exc) if isinstance(exc, OcrExtractionError) else "Cannot open local input file"
        print(f"OcrExtractionError: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
