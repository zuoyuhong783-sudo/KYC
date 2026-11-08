"""Generate unmistakably synthetic OCR-only cards; these are NOT E's face fixtures."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def generate(output: Path, font_path: Path):
    output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(font_path), 42)
    small = ImageFont.truetype(str(font_path), 24)
    cases = []
    records = [
        ("normal_cn", "测试甲", "000000200001011234", "2035-05-01", "测试市公安局", "zh"),
        ("normal_en", "TEST USER", "000000200001015678", "2034-06-02", "TEST SECURITY BUREAU", "en"),
        ("normal_range", "测试乙", "000000200001012345", "2033-07-03", "样例市公安局", "zh"),
        ("normal_jpeg", "测试丙", "000000200001013456", "2032-08-04", "示例市公安局", "zh"),
        ("normal_split", "测试丁", "000000200001014567", "2031-09-05", "演示市公安局", "zh"),
        ("expired", "测试戊", "000000200001015679", "2020-05-01", "测试市公安局", "zh"),
    ]
    for case_id, name, identifier, expiry, authority, language in records:
        image = Image.new("RGB", (1600, 950), "white")
        draw = ImageDraw.Draw(image)
        draw.text((60, 35), "SYNTHETIC OCR TEST - NOT AN ID DOCUMENT", font=small, fill=(100, 100, 100))
        if language == "en":
            lines = [f"Name: {name}", f"ID Number: {identifier}", f"Expiry Date: {expiry}", f"Issuing Authority: {authority}"]
        elif case_id == "normal_split":
            lines = ["姓名", name, "公民身份号码", identifier, "签发机关", authority, "有效期限", expiry]
        else:
            value = f"2023.07.03-{expiry.replace('-', '.')}" if case_id == "normal_range" else expiry
            lines = [f"姓名: {name}", f"公民身份号码: {identifier}", f"签发机关: {authority}", f"有效期限: {value}"]
        for index, line in enumerate(lines):
            draw.text((60, 140 + index * 90), line, font=font, fill="black")
        image_file = f"{case_id}.jpg" if case_id == "normal_jpeg" else f"{case_id}.png"
        image.save(output / image_file)
        cases.append({"case_id": case_id, "image": image_file, "expected": {
            "name": name, "id_number_masked": "*" * 14 + identifier[-4:],
            "expiry_date": expiry, "issuing_authority": authority, "id_valid": expiry >= "2026-11-06",
        }})
    for case_id, data in [("zero_byte", b""), ("wrong_format", b"plain text renamed as jpg"), ("truncated", b"\xff\xd8\xff\xe0broken")]:
        image_file = f"{case_id}.jpg"
        (output / image_file).write_bytes(data)
        cases.append({"case_id": case_id, "image": image_file, "expected_error": "OcrExtractionError"})
    for case in cases:
        case["sha256"] = hashlib.sha256((output / case["image"]).read_bytes()).hexdigest()
    manifest = {"dataset": "synthetic-smoke-only", "today": "2026-11-06",
                "font_sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(), "cases": cases}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True, help="Local font with Chinese glyphs")
    args = parser.parse_args()
    generate(args.output, args.font)
