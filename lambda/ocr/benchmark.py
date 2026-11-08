"""Repeatable B1/B5 measurements. Stores metrics, never raw OCR or full IDs."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter

from errors import OcrExtractionError
from extraction import extract_fields
from ocr_engine import MAX_IMAGE_BYTES, recognize


FIELDS = ("name", "id_number_masked", "expiry_date", "issuing_authority", "id_valid")


def run(manifest_path: Path, engines: list[str], output: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("cases"):
        raise ValueError("Benchmark manifest must contain cases")
    for case in manifest["cases"]:
        if "sha256" in case:
            digest = hashlib.sha256((manifest_path.parent / case["image"]).read_bytes()).hexdigest()
            if digest != case["sha256"]:
                raise ValueError(f"Fixture checksum mismatch: {case['case_id']}")
    today = date.fromisoformat(manifest["today"])
    rows = []
    for engine in engines:
        for index, case in enumerate(manifest["cases"]):
            started = perf_counter()
            actual, error = {}, ""
            try:
                with (manifest_path.parent / case["image"]).open("rb") as stream:
                    text = recognize(stream.read(MAX_IMAGE_BYTES + 1), engine=engine)
                actual = extract_fields(text, today=today)
            except (OcrExtractionError, OSError) as exc:
                error = str(exc) if isinstance(exc, OcrExtractionError) else "Cannot open fixture"
            elapsed = perf_counter() - started
            expected_error = case.get("expected_error") == "OcrExtractionError"
            # A missing runtime/model must never count as successful bad-file handling.
            infrastructure_error = error.startswith("OCR engine unavailable") or error == "Cannot open fixture"
            passed = (bool(error) and not infrastructure_error) if expected_error else (not error and actual == case["expected"])
            row = {"engine": engine, "case_id": case["case_id"], "seconds": round(elapsed, 6),
                   "first_call": index == 0, "expected_error": expected_error,
                   "passed": passed, "error": error}
            for field in FIELDS:
                row[field + "_correct"] = "" if expected_error else int(not error and actual.get(field) == case["expected"][field])
            rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metadata = {"dataset": manifest.get("dataset", "unspecified"), "today": str(today),
                "recorded_at": datetime.now(timezone.utc).isoformat(), "python": sys.version,
                "platform": platform.platform(), "timing": "local image read + OCR + extraction; first call includes model load",
                "packages": {name: importlib.metadata.version(name) for name in ("rapidocr-onnxruntime", "onnxruntime", "pillow")}}
    metadata["fixtures_sha256"] = {case["case_id"]: case.get("sha256", "not recorded") for case in manifest["cases"]}
    metadata["font_sha256"] = manifest.get("font_sha256", "not recorded")
    if "tesseract" in engines:
        import os
        import tesserocr

        metadata["packages"]["tesserocr"] = importlib.metadata.version("tesserocr")
        metadata["tesseract_version"] = tesserocr.tesseract_version()
        model_dir = Path(os.environ["TESSDATA_PREFIX"])
        metadata["tessdata_sha256"] = {lang: hashlib.sha256((model_dir / f"{lang}.traineddata").read_bytes()).hexdigest() for lang in ("chi_sim", "eng")}
    output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for engine in engines:
        subset = [row for row in rows if row["engine"] == engine]
        print(f"{engine}: {sum(row['passed'] for row in subset)}/{len(subset)} cases matched expectations")
    return int(any(not row["passed"] for row in rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--engines", nargs="+", choices=("rapidocr", "tesseract"), default=["rapidocr"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.manifest, args.engines, args.output))
