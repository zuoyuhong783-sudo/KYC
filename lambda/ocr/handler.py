"""vericloud-ocr Lambda entrypoint. No database writes or final KYC decisions."""

import re
from datetime import datetime
from functools import lru_cache
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from errors import OcrExtractionError
from extraction import extract_fields
from ocr_engine import MAX_IMAGE_BYTES, recognize


def _validate_event(event):
    if not isinstance(event, dict):
        raise OcrExtractionError("Input must be the workflow JSON object")
    required = ("application_id", "bucket", "id_card_key", "selfie_key", "created_at")
    for field in required:
        if not isinstance(event.get(field), str) or not event[field]:
            raise OcrExtractionError(f"Missing or invalid input field: {field}")
    try:
        identifier = UUID(event["application_id"])
        if identifier.version != 4 or str(identifier) != event["application_id"]:
            raise ValueError
    except ValueError:
        raise OcrExtractionError("Invalid input field: application_id (expected UUID v4)") from None
    if not re.fullmatch(r"vericloud-raw-[a-z0-9][a-z0-9.-]*[a-z0-9]", event["bucket"]):
        raise OcrExtractionError("Invalid input field: bucket")
    for key, prefix in (("id_card_key", "raw/id-card"), ("selfie_key", "raw/selfie")):
        allowed = {f"{prefix}/{identifier}.{ext}" for ext in ("jpg", "jpeg", "png")}
        if event[key] not in allowed:
            raise OcrExtractionError(f"Invalid input field: {key}")
    try:
        timestamp = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
            raise ValueError
    except ValueError:
        raise OcrExtractionError("Invalid input field: created_at (expected UTC)") from None


@lru_cache(maxsize=1)
def _s3_client():
    return boto3.client("s3", region_name="us-east-1", config=Config(
        connect_timeout=5, read_timeout=10, retries={"mode": "standard", "total_max_attempts": 2},
    ))


def _read_document(event):
    try:
        response = _s3_client().get_object(Bucket=event["bucket"], Key=event["id_card_key"])
        body = response["Body"]
        try:
            if response.get("ContentLength", 0) > MAX_IMAGE_BYTES:
                raise OcrExtractionError("Image exceeds the 10 MiB OCR limit")
            data = body.read(MAX_IMAGE_BYTES + 1)
        finally:
            body.close()
    except (BotoCoreError, ClientError, OSError):
        raise OcrExtractionError("Cannot read id_card_key from S3") from None
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise OcrExtractionError("Image is empty or exceeds the 10 MiB OCR limit")
    return data


def lambda_handler(event, context):
    _validate_event(event)
    return extract_fields(recognize(_read_document(event)))
