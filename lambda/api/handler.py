"""vericloud-api — the two browser-facing endpoints the frontend needs.

Served through an API Gateway HTTP API, payload format 2.0 (CORS is configured on the API, not here).

  POST /applications
       body {"application_id", "id_card_extension", "selfie_extension"}
       -> 200 {"application_id", "id_card_url", "selfie_url", "expires_in"}
       Two presigned PUT URLs (interface sections 1 and 3: raw/id-card/<id><ext>,
       raw/selfie/<id><ext>, 300 s). The browser uploads the ID card first, then
       the selfie; the selfie upload starts the pipeline (A5).

  GET  /applications/<application_id>
       -> 200 {"review_status", "reason", "processed_at"} once the row exists
       -> 404 while the workflow is still running (frontend keeps polling)
       Only these three fields leave the table: no name, no ID number.

Environment: BUCKET (vericloud-raw-1009-a), TABLE (vericloud-kyc-table), URL_TTL (300).
No authentication: acceptable for the class demo only. Anyone with the URL can
request upload links, so the API URL is not shared outside the team.
"""

import base64
import json
import os
import re

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

BUCKET = os.environ.get("BUCKET", "vericloud-raw-1009-a")
TABLE = os.environ.get("TABLE", "vericloud-kyc-table")
URL_TTL = int(os.environ.get("URL_TTL", "300"))
ALLOWED_EXT = (".jpg", ".jpeg", ".png")
UUID_V4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
GET_PATH = re.compile(r"^/applications/([^/]+)/?$")

_s3 = None
_ddb = None


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version="s3v4"))
    return _s3


def _ddb_client():
    global _ddb
    if _ddb is None:
        _ddb = boto3.client("dynamodb", region_name="us-east-1")
    return _ddb


def _resp(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, ensure_ascii=False)}


def _body(event):
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _ext(value):
    value = (value or "").lower()
    if not value.startswith("."):
        value = "." + value
    return value if value in ALLOWED_EXT else None


def _exists(key):
    try:
        _s3_client().head_object(Bucket=BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def create_application(event):
    data = _body(event)
    if data is None:
        return _resp(400, {"error": "body must be a JSON object"})
    app_id = data.get("application_id")
    if not isinstance(app_id, str) or not UUID_V4.match(app_id):
        return _resp(400, {"error": "application_id must be a lowercase UUID v4"})
    id_ext, selfie_ext = _ext(data.get("id_card_extension")), _ext(data.get("selfie_extension"))
    if not id_ext or not selfie_ext:
        return _resp(400, {"error": "extensions must be .jpg, .jpeg or .png"})

    id_key = f"raw/id-card/{app_id}{id_ext}"
    selfie_key = f"raw/selfie/{app_id}{selfie_ext}"
    # Never hand out a URL that would overwrite an earlier application's photos.
    if _exists(selfie_key) or _exists(id_key):
        return _resp(409, {"error": "application_id already used"})

    sign = lambda key: _s3_client().generate_presigned_url(
        "put_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=URL_TTL)
    return _resp(200, {"application_id": app_id, "id_card_url": sign(id_key),
                       "selfie_url": sign(selfie_key), "expires_in": URL_TTL})


def get_result(app_id):
    if not UUID_V4.match(app_id):
        return _resp(400, {"error": "application_id must be a lowercase UUID v4"})
    item = _ddb_client().get_item(
        TableName=TABLE, Key={"application_id": {"S": app_id}},
        ProjectionExpression="review_status, reason, processed_at",
    ).get("Item")
    if not item or "review_status" not in item:
        return _resp(404, {"status": "PENDING"})
    return _resp(200, {k: item[k]["S"] for k in ("review_status", "reason", "processed_at") if k in item})


def lambda_handler(event, context):
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method", "")
    path = event.get("rawPath") or http.get("path") or ""
    try:
        if method == "POST" and path.rstrip("/") == "/applications":
            return create_application(event)
        match = GET_PATH.match(path)
        if method == "GET" and match:
            return get_result(match.group(1))
        return _resp(404, {"error": "not found"})
    except ClientError as e:
        print(f"AWS error: {e}")
        return _resp(502, {"error": "backend error"})
