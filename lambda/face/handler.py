"""vericloud-face — compare the selfie against the ID-card photo.

Contract: docs/interface.md sections 5.4 and 7.
  input  (5.1, verbatim): {application_id, bucket, id_card_key, selfie_key, created_at}
  output (5.4):          {"similarity": 92.37, "face_matched": true}
  face_matched = similarity >= 80 (interface.md section 3)

Exception class names are load-bearing: the Step Functions Catch in
vericloud-kyc-workflow matches them by ErrorEquals, so they must stay
exactly FaceNotDetectedError and FaceCompareError.
"""

import boto3
from botocore.exceptions import ClientError

rekognition = boto3.client("rekognition")

SIMILARITY_PASS = 80  # interface.md section 3


class FaceNotDetectedError(Exception):
    """No usable face in either image (absent or too blurry)."""


class FaceCompareError(Exception):
    """Rekognition failed or the response was unusable."""


def compare(bucket: str, selfie_key: str, id_card_key: str) -> float:
    """Return the highest face similarity between selfie and ID card."""
    resp = rekognition.compare_faces(
        SourceImage={"S3Object": {"Bucket": bucket, "Name": selfie_key}},
        TargetImage={"S3Object": {"Bucket": bucket, "Name": id_card_key}},
        SimilarityThreshold=0,
    )
    matches = resp.get("FaceMatches") or []
    if not matches:
        raise FaceNotDetectedError(
            f"no face detected in {selfie_key!r} or {id_card_key!r}"
        )
    try:
        return round(max(m["Similarity"] for m in matches), 2)
    except (KeyError, TypeError) as e:
        raise FaceCompareError(f"unexpected CompareFaces response: {e}") from e


def lambda_handler(event, context):
    try:
        similarity = compare(
            event["bucket"], event["selfie_key"], event["id_card_key"]
        )
    except (FaceNotDetectedError, FaceCompareError):
        raise  # contract exceptions reach the state machine Catch untouched
    except KeyError as e:
        raise FaceCompareError(f"missing field in state input: {e}") from e
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "InvalidParameterException":
            # CompareFaces signals "no (usable) face in the image" this way
            raise FaceNotDetectedError(
                f"no usable face in {event['selfie_key']!r} or {event['id_card_key']!r}"
            ) from e
        raise FaceCompareError(f"rekognition call failed: {e}") from e
    return {"similarity": similarity, "face_matched": similarity >= SIMILARITY_PASS}
