import io
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

import handler
from errors import OcrExtractionError


@pytest.fixture
def event():
    identifier = "3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b"
    return {"application_id": identifier, "bucket": "vericloud-raw-test",
            "id_card_key": f"raw/id-card/{identifier}.jpg",
            "selfie_key": f"raw/selfie/{identifier}.png", "created_at": "2026-11-06T00:00:00Z"}


def test_handler_reads_only_id_returns_exact_schema(monkeypatch, event):
    body = io.BytesIO(b"image bytes")
    client = Mock()
    client.get_object.return_value = {"Body": body, "ContentLength": 11}
    monkeypatch.setattr(handler, "_s3_client", lambda: client)
    recognize = Mock(return_value="Name: TEST USER\nID Number: 000000200001011234\nExpiry Date: 2099-01-01\nIssuing Authority: TEST BUREAU")
    monkeypatch.setattr(handler, "recognize", recognize)
    result = handler.lambda_handler(event, None)
    assert set(result) == {"name", "id_number_masked", "expiry_date", "issuing_authority", "id_valid"}
    assert result["id_number_masked"] == "**************1234"
    assert result["id_valid"] is True
    assert body.closed
    client.get_object.assert_called_once_with(Bucket=event["bucket"], Key=event["id_card_key"])
    recognize.assert_called_once_with(b"image bytes")


@pytest.mark.parametrize("field,value", [
    ("application_id", "bad-id"), ("bucket", "other-bucket"),
    ("id_card_key", "raw/id-card/other.jpg"), ("selfie_key", "elsewhere.png"),
    ("created_at", "2026-11-06"), ("created_at", "2026-11-06T08:00:00+08:00"),
])
def test_invalid_input_never_calls_s3(monkeypatch, event, field, value):
    client = Mock()
    monkeypatch.setattr(handler, "_s3_client", client)
    event[field] = value
    with pytest.raises(OcrExtractionError, match=field):
        handler.lambda_handler(event, None)
    client.assert_not_called()


def test_s3_failure_is_sanitized(monkeypatch, event):
    client = Mock()
    client.get_object.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": "secret details"}}, "GetObject")
    monkeypatch.setattr(handler, "_s3_client", lambda: client)
    with pytest.raises(OcrExtractionError, match="Cannot read") as error:
        handler.lambda_handler(event, None)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("data,size", [(b"", 0), (b"x", handler.MAX_IMAGE_BYTES + 1)])
def test_empty_or_oversize_stream_is_closed(monkeypatch, event, data, size):
    body = io.BytesIO(data)
    client = Mock()
    client.get_object.return_value = {"Body": body, "ContentLength": size}
    monkeypatch.setattr(handler, "_s3_client", lambda: client)
    with pytest.raises(OcrExtractionError):
        handler.lambda_handler(event, None)
    assert body.closed


def test_ocr_error_retains_contract_name(monkeypatch, event):
    monkeypatch.setattr(handler, "_read_document", lambda event: b"image")
    monkeypatch.setattr(handler, "recognize", Mock(side_effect=OcrExtractionError("Missing field: name")))
    with pytest.raises(OcrExtractionError, match="name"):
        handler.lambda_handler(event, None)
