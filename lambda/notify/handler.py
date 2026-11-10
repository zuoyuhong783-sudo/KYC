"""
vericloud-notify — DynamoDB Streams -> Amazon SNS email notification.

Contract: ``docs/interface.md`` v1.2, section 5.6.

Behaviour
---------
* Trigger: ``vericloud-kyc-table`` DynamoDB Stream (``NEW_AND_OLD_IMAGES``).
* Publish only when ``review_status`` is **created** (INSERT) or **changed**
  (MODIFY with a different status). A MODIFY that leaves the status untouched
  is ignored, so a DynamoDB Streams at-least-once redelivery cannot duplicate
  an email.
* The SNS payload contains exactly four fields and never the applicant's name
  or ID number — see ``_build_payload``.

Environment
-----------
``SNS_TOPIC_ARN``  ARN of ``vericloud-kyc-topic`` (required).

IAM
---
``sns:Publish`` on the topic above; ``dynamodb:DescribeStream``,
``dynamodb:GetRecords``, ``dynamodb:GetShardIterator``, ``dynamodb:ListStreams``
for the stream. In Learner Lab this is satisfied by ``LabRole``.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_sns_client = None


def _sns() -> Any:
    """Lazily create the SNS client (keeps cold start cheap and tests simple)."""
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns")
    return _sns_client


def _attr_str(image: Dict[str, Any], name: str) -> Optional[str]:
    """Return the string value of a DynamoDB attribute, or ``None``."""
    attribute = image.get(name)
    if not attribute:
        return None
    return attribute.get("S")


def _build_payload(new_image: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build the SNS message body from a DynamoDB ``NewImage``.

    Returns ``None`` when the record is not a KYC result we can act on.

    Deliberately excludes ``name``, ``id_number_masked`` and every other
    personal field: the email must not contain applicant identifiers.
    """
    application_id = _attr_str(new_image, "application_id")
    review_status = _attr_str(new_image, "review_status")
    if not application_id or not review_status:
        return None
    return {
        "application_id": application_id,
        "review_status": review_status,
        "reason": _attr_str(new_image, "reason"),
        "processed_at": _attr_str(new_image, "processed_at"),
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Entry point: publish one SNS notification per status change."""
    topic_arn = os.environ.get("SNS_TOPIC_ARN")

    published = 0
    for record in event.get("Records", []):
        if record.get("eventSource") != "aws:dynamodb":
            continue

        event_name = record.get("eventName")
        if event_name not in ("INSERT", "MODIFY"):
            continue

        stream = record.get("dynamodb") or {}
        new_image = stream.get("NewImage") or {}
        old_image = stream.get("OldImage") or {}

        payload = _build_payload(new_image)
        if payload is None:
            logger.warning(
                "Skipping record %s: missing application_id or review_status",
                record.get("eventID"),
            )
            continue

        if event_name == "MODIFY" and _attr_str(old_image, "review_status") == payload["review_status"]:
            logger.info(
                "review_status unchanged for %s; no notification",
                payload["application_id"],
            )
            continue

        if not topic_arn:
            raise RuntimeError("SNS_TOPIC_ARN environment variable is not set")

        subject = "[VeriCloud] Application {}: {}".format(
            payload["application_id"][:8], payload["review_status"]
        )
        _sns().publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=json.dumps(payload, ensure_ascii=False),
        )
        published += 1

    logger.info("Published %d notification(s)", published)
    return {"statusCode": 200, "body": json.dumps({"published": published})}
