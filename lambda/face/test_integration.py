"""Integration tests for the deployed vericloud-face (C5): invoke the real
function against the three in-bucket fixture pairs (normal / no_face /
different_person).

Needs a valid [lab] profile in ~/.aws/credentials, so they are skipped
unless opted in:   VERICLOUD_INTEGRATION=1 uv run --with boto3 --with pytest \
                       pytest test_integration.py -v

Fixture images live in vericloud-raw-1009 (uploaded 2026-11-06, kept for C5);
the raw/ lifecycle deletes them after 7 days — if they are gone, re-upload
from tests/fixtures or any portrait pair before running.
"""

import json
import os

import boto3
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("VERICLOUD_INTEGRATION") != "1",
    reason="integration test; opt in with VERICLOUD_INTEGRATION=1 and a valid [lab] profile",
)

FUNCTION = "vericloud-face"
BUCKET = "vericloud-raw-1009"


def invoke_lambda(id_card_key, selfie_key, case):
    session = boto3.Session(profile_name="lab", region_name="us-east-1")
    client = session.client("lambda")
    event = {
        "application_id": f"c5-integration-{case}",
        "bucket": BUCKET,
        "id_card_key": id_card_key,
        "selfie_key": selfie_key,
        "created_at": "2026-11-08T00:00:00Z",
    }
    resp = client.invoke(FunctionName=FUNCTION, Payload=json.dumps(event))
    payload = json.loads(resp["Payload"].read())
    return payload, resp.get("FunctionError")


def test_normal_same_person_passes():
    payload, err = invoke_lambda(
        "raw/id-card/smoke-app.jpg", "raw/selfie/smoke-app.jpg", "same")
    assert err is None
    assert payload["face_matched"] is True
    assert payload["similarity"] >= 80


def test_no_face_raises_contract_error():
    payload, err = invoke_lambda(
        "raw/id-card/noface-test.jpg", "raw/selfie/noface-test.jpg", "noface")
    # "Handled" or "Unhandled" both occur for raised custom exceptions
    # depending on runtime; Step Functions matches errorType, not this header.
    assert err in ("Handled", "Unhandled")
    assert payload["errorType"] == "FaceNotDetectedError"


def test_different_person_fails_threshold():
    payload, err = invoke_lambda(
        "raw/id-card/diff-target.jpg", "raw/selfie/diff-source.jpg", "diff")
    assert err is None
    assert payload["face_matched"] is False
    assert payload["similarity"] < 80
