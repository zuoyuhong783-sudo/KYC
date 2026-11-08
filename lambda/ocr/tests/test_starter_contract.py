"""Regression: starter's emitted payload must be accepted by OCR unchanged."""
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

import boto3
from PIL import Image

from handler import _validate_event


def test_starter_uses_contract_id_card_prefix(monkeypatch):
    source = Path(__file__).resolve().parents[2] / "starter" / "handler.py"
    image = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(image, format="JPEG")
    data = image.getvalue()
    s3, sfn = Mock(), Mock()
    s3.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(data), "ContentLength": len(data)}
    sfn.start_execution.return_value = {"executionArn": "mock-execution"}
    monkeypatch.setenv("STATE_MACHINE_ARN", "mock-state-machine")
    monkeypatch.setattr(boto3, "client", lambda service: s3 if service == "s3" else sfn)
    spec = importlib.util.spec_from_file_location("starter_for_ocr_contract", source)
    starter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(starter)
    identifier = "3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b"
    event = {"Records": [{"body": json.dumps({"Records": [{"s3": {
        "bucket": {"name": "vericloud-raw-1009"},
        "object": {"key": f"raw/selfie/{identifier}.jpg"},
    }}]})}]}
    starter.lambda_handler(event, None)
    payload = json.loads(sfn.start_execution.call_args.kwargs["input"])
    assert payload["id_card_key"] == f"raw/id-card/{identifier}.jpg"
    _validate_event(payload)
    assert s3.get_object.call_args_list[-1].kwargs["Key"] == payload["id_card_key"]
