"""Exercise the real Lambda entrypoint and real OCR; replace only S3 transport."""

import argparse
import io
import json
from pathlib import Path
from unittest.mock import Mock, patch

import handler
from errors import OcrExtractionError


def run(fixtures: Path):
    samples = Path(__file__).parent / "samples"
    for name, image in (("valid", "normal_cn.png"), ("expired", "expired.png")):
        event = json.loads((samples / f"{name}.input.json").read_text(encoding="utf-8"))
        expected = json.loads((samples / f"{name}.output.json").read_text(encoding="utf-8"))
        data = (fixtures / image).read_bytes()
        client = Mock()
        body = io.BytesIO(data)
        client.get_object.return_value = {"Body": body, "ContentLength": len(data)}
        with patch.object(handler, "_s3_client", return_value=client):
            actual = handler.lambda_handler(event, None)
        assert actual == expected, f"{name} contract output mismatch"
        assert body.closed
        client.get_object.assert_called_once_with(Bucket=event["bucket"], Key=event["id_card_key"])
        print(f"{name}: real handler + real OCR passed (S3 mocked)")
    for name in ("zero_byte", "wrong_format", "truncated"):
        data = (fixtures / f"{name}.jpg").read_bytes()
        client = Mock()
        client.get_object.return_value = {"Body": io.BytesIO(data), "ContentLength": len(data)}
        with patch.object(handler, "_s3_client", return_value=client):
            try:
                handler.lambda_handler(event, None)
            except OcrExtractionError:
                print(f"{name}: agreed exception raised")
            else:
                raise AssertionError(f"{name}: invalid image was accepted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("fixtures", type=Path)
    run(parser.parse_args().fixtures)
