"""Unit tests for vericloud-notify (F4).

Run from the repository root:

    python -m pytest lambda/notify/test_handler.py -v
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handler  # noqa: E402

APP_ID = "3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b"
TOPIC = "arn:aws:sns:us-east-1:123456789012:vericloud-kyc-topic"


class FakeSns:
    def __init__(self):
        self.calls = []

    def publish(self, **kwargs):
        self.calls.append(kwargs)
        return {"MessageId": "fake-message-id"}


@pytest.fixture
def sns(monkeypatch):
    fake = FakeSns()
    monkeypatch.setattr(handler, "_sns_client", fake)
    monkeypatch.setenv("SNS_TOPIC_ARN", TOPIC)
    return fake


def _new_image(status="PASS"):
    return {
        "application_id": {"S": APP_ID},
        "review_status": {"S": status},
        "reason": {"S": "auto_approved"},
        "processed_at": {"S": "2026-11-20T08:30:41Z"},
        # personal fields that must NOT leak into the email
        "name": {"S": "ZHANG SAN"},
        "id_number_masked": {"S": "**************1234"},
    }


def _event(event_name="INSERT", status="PASS", old_status=None):
    stream = {"NewImage": _new_image(status), "SequenceNumber": "1"}
    if old_status is not None:
        stream["OldImage"] = {
            "application_id": {"S": APP_ID},
            "review_status": {"S": old_status},
        }
    return {
        "Records": [
            {
                "eventSource": "aws:dynamodb",
                "eventName": event_name,
                "eventID": "rec-1",
                "dynamodb": stream,
            }
        ]
    }


def test_insert_publishes_once(sns):
    handler.lambda_handler(_event("INSERT"), None)

    assert len(sns.calls) == 1
    call = sns.calls[0]
    assert call["TopicArn"] == TOPIC
    assert call["Subject"] == "[VeriCloud] Application 3f2b7c1e: PASS"


def test_payload_contains_no_personal_data(sns):
    handler.lambda_handler(_event("INSERT"), None)

    body = json.loads(sns.calls[0]["Message"])
    assert set(body) == {"application_id", "review_status", "reason", "processed_at"}
    assert "ZHANG SAN" not in sns.calls[0]["Message"]
    assert "1234" not in sns.calls[0]["Message"]


def test_modify_with_same_status_does_not_publish(sns):
    handler.lambda_handler(_event("MODIFY", status="PASS", old_status="PASS"), None)
    assert sns.calls == []


def test_modify_with_changed_status_publishes(sns):
    handler.lambda_handler(
        _event("MODIFY", status="NEEDS_HUMAN_REVIEW", old_status="PASS"), None
    )
    assert len(sns.calls) == 1
    assert sns.calls[0]["Subject"].endswith("NEEDS_HUMAN_REVIEW")


def test_remove_event_is_ignored(sns):
    handler.lambda_handler(_event("REMOVE"), None)
    assert sns.calls == []


def test_record_without_status_is_skipped(sns):
    event = _event("INSERT")
    event["Records"][0]["dynamodb"]["NewImage"].pop("review_status")
    handler.lambda_handler(event, None)
    assert sns.calls == []


def test_missing_topic_env_raises(sns, monkeypatch):
    monkeypatch.delenv("SNS_TOPIC_ARN", raising=False)
    with pytest.raises(RuntimeError):
        handler.lambda_handler(_event("INSERT"), None)
