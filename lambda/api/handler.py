"""vericloud-api — the two browser-facing endpoints the frontend needs.

Served through an API Gateway HTTP API, payload format 2.0 (CORS is configured on the API, not here).

  POST /applications
       body {"application_id", "id_card_extension", "selfie_extension"[, "id_card_back_extension"]}
       -> 200 {"application_id", "id_card_url", "selfie_url", "expires_in"[, "id_card_back_url"]}
       With id_card_back_extension (v1.5) the ID front goes to raw/id-card-front/, the
       back to raw/id-card-back/, and the starter stitches them into raw/id-card/.
       Two presigned PUT URLs (interface sections 1 and 3: raw/id-card/<id><ext>,
       raw/selfie/<id><ext>, 300 s). The browser uploads the ID card first, then
       the selfie; the selfie upload starts the pipeline (A5).

  GET  /applications/<application_id>
       -> 200 {"review_status", "reason", "processed_at"} once the row exists
       -> 404 while the workflow is still running (frontend keeps polling)
       Only these three fields leave the table: no name, no ID number.

  GET  /applications/<application_id>/trace    (live view in frontend/live)
       -> 200 {"uploads", "execution", "steps", "result"}: which photos are in S3,
       the Step Functions execution and every state it has passed so far, and the
       DynamoDB row with the name masked to its first character.

  GET  /dashboard
       -> 200 {"counts", "recent", "queues", "executions"}: PASS / review / FAIL
       counts, the latest rows (no personal fields), queue and DLQ depth.

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
TRACE_PATH = re.compile(r"^/applications/([^/]+)/trace/?$")
STATE_MACHINE = os.environ.get("STATE_MACHINE", "vericloud-kyc-workflow")
QUEUE = os.environ.get("QUEUE", "vericloud-ingest-queue")
DLQ = os.environ.get("DLQ", "vericloud-ingest-dlq")

_s3 = None
_ddb = None
_sfn = None
_sqs = None


def _sfn_client():
    global _sfn
    if _sfn is None:
        _sfn = boto3.client("stepfunctions", region_name="us-east-1")
    return _sfn


def _sqs_client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs", region_name="us-east-1")
    return _sqs


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


# CORS is answered here as well: the HTTP API's own CORS setting did not take effect
# in the Learner Lab account. If it does, API Gateway uses its own headers instead.
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


def _resp(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json", **CORS_HEADERS},
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

    back_ext = None
    if data.get("id_card_back_extension") is not None:
        back_ext = _ext(data.get("id_card_back_extension"))
        if not back_ext:
            return _resp(400, {"error": "extensions must be .jpg, .jpeg or .png"})

    # v1.5: with a back side, front and back go to their own prefixes and the starter
    # stitches them into raw/id-card/<id>.jpg. Without one, the single image goes
    # straight to raw/id-card/ as before.
    selfie_key = f"raw/selfie/{app_id}{selfie_ext}"
    if back_ext:
        id_key = f"raw/id-card-front/{app_id}{id_ext}"
        back_key = f"raw/id-card-back/{app_id}{back_ext}"
    else:
        id_key, back_key = f"raw/id-card/{app_id}{id_ext}", None
    # Never hand out a URL that would overwrite an earlier application's photos.
    if any(_exists(k) for k in (selfie_key, id_key, back_key) if k):
        return _resp(409, {"error": "application_id already used"})

    sign = lambda key: _s3_client().generate_presigned_url(
        "put_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=URL_TTL)
    out = {"application_id": app_id, "id_card_url": sign(id_key),
           "selfie_url": sign(selfie_key), "expires_in": URL_TTL}
    if back_key:
        out["id_card_back_url"] = sign(back_key)
    return _resp(200, out)


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


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _plain(attr):
    """DynamoDB attribute -> plain JSON value."""
    if "S" in attr:
        return attr["S"]
    if "N" in attr:
        return float(attr["N"])
    if "BOOL" in attr:
        return attr["BOOL"]
    return None


def _mask_name(name):
    name = (name or "").strip()
    return name[:1] + "*" * (len(name) - 1) if name else None


def _account(context):
    return context.invoked_function_arn.split(":")[4]


def _find_upload(prefix, app_id):
    for ext in ALLOWED_EXT:
        try:
            head = _s3_client().head_object(Bucket=BUCKET, Key=f"{prefix}{app_id}{ext}")
            return {"key": f"{prefix}{app_id}{ext}", "size": head["ContentLength"],
                    "uploaded_at": _iso(head["LastModified"])}
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound", "403"):
                raise
    return None


_STEP_EVENTS = ("TaskStateEntered", "TaskStateExited", "PassStateEntered", "PassStateExited",
                "ChoiceStateEntered", "ChoiceStateExited", "ParallelStateEntered", "ParallelStateExited")


def trace(app_id, context):
    """Everything the live view needs for one application, in one call."""
    if not UUID_V4.match(app_id):
        return _resp(400, {"error": "application_id must be a lowercase UUID v4"})
    out = {"application_id": app_id,
           "uploads": {"id_card_front": _find_upload("raw/id-card-front/", app_id),
                       "id_card_back": _find_upload("raw/id-card-back/", app_id),
                       "id_card": _find_upload("raw/id-card/", app_id),   # single image, or the stitched one
                       "selfie": _find_upload("raw/selfie/", app_id)},
           "execution": None, "steps": [], "result": None}

    arn = f"arn:aws:states:us-east-1:{_account(context)}:execution:{STATE_MACHINE}:{app_id}"
    try:
        ex = _sfn_client().describe_execution(executionArn=arn)
        out["execution"] = {"status": ex["status"], "started_at": _iso(ex.get("startDate")),
                            "stopped_at": _iso(ex.get("stopDate"))}
        steps = {}
        for ev in _sfn_client().get_execution_history(executionArn=arn, maxResults=200)["events"]:
            if ev["type"] not in _STEP_EVENTS:
                continue
            details = ev.get("stateEnteredEventDetails") or ev.get("stateExitedEventDetails") or {}
            step = steps.setdefault(details.get("name"), {"name": details.get("name"), "entered_at": None, "exited_at": None})
            step["entered_at" if ev["type"].endswith("Entered") else "exited_at"] = _iso(ev["timestamp"])
        out["steps"] = list(steps.values())
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") != "ExecutionDoesNotExist":
            raise

    item = _ddb_client().get_item(TableName=TABLE, Key={"application_id": {"S": app_id}}).get("Item")
    if item:
        row = {k: _plain(v) for k, v in item.items()}
        out["result"] = {
            "review_status": row.get("review_status"), "reason": row.get("reason"),
            "created_at": row.get("created_at"), "received_at": row.get("received_at"),
            "processed_at": row.get("processed_at"),
            "ocr": None if "id_number_masked" not in row else {
                "name": _mask_name(row.get("name")), "id_number_masked": row.get("id_number_masked"),
                "expiry_date": row.get("expiry_date"), "issuing_authority": row.get("issuing_authority"),
                "id_valid": row.get("id_valid")},
            "similarity": row.get("similarity"), "face_error": row.get("face_error"),
        }
    return _resp(200, out)


def dashboard(context):
    """Counters and recent rows for the operations view (no personal fields)."""
    out = {"counts": {"PASS": 0, "NEEDS_HUMAN_REVIEW": 0, "FAIL": 0}, "recent": [],
           "queues": {}, "executions": {}}
    items = _ddb_client().scan(
        TableName=TABLE, Limit=500,
        ProjectionExpression="application_id, review_status, reason, created_at, received_at, processed_at, similarity",
    ).get("Items", [])
    rows = [{k: _plain(v) for k, v in it.items()} for it in items]
    for r in rows:
        if r.get("review_status") in out["counts"]:
            out["counts"][r["review_status"]] += 1
    rows.sort(key=lambda r: r.get("processed_at") or "", reverse=True)
    out["recent"] = rows[:15]

    for label, name in (("ingest", QUEUE), ("dlq", DLQ)):
        try:
            url = _sqs_client().get_queue_url(QueueName=name)["QueueUrl"]
            a = _sqs_client().get_queue_attributes(
                QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
            out["queues"][label] = {"waiting": int(a["ApproximateNumberOfMessages"]),
                                    "in_flight": int(a["ApproximateNumberOfMessagesNotVisible"])}
        except ClientError:
            out["queues"][label] = None

    sm_arn = f"arn:aws:states:us-east-1:{_account(context)}:stateMachine:{STATE_MACHINE}"
    try:
        for status in ("RUNNING", "SUCCEEDED", "FAILED"):
            out["executions"][status] = len(_sfn_client().list_executions(
                stateMachineArn=sm_arn, statusFilter=status, maxResults=100)["executions"])
    except ClientError:
        out["executions"] = None
    return _resp(200, out)


def lambda_handler(event, context):
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method", "")
    path = event.get("rawPath") or http.get("path") or ""
    if method == "OPTIONS":  # CORS preflight from the browser
        return {"statusCode": 204, "headers": {**CORS_HEADERS,
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "content-type", "Access-Control-Max-Age": "300"}}
    try:
        if method == "POST" and path.rstrip("/") == "/applications":
            return create_application(event)
        if method == "GET" and path.rstrip("/") == "/dashboard":
            return dashboard(context)
        match = TRACE_PATH.match(path)
        if method == "GET" and match:
            return trace(match.group(1), context)
        match = GET_PATH.match(path)
        if method == "GET" and match:
            return get_result(match.group(1))
        return _resp(404, {"error": "not found"})
    except ClientError as e:
        print(f"AWS error: {e}")
        return _resp(502, {"error": "backend error"})
