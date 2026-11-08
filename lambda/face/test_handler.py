"""Unit tests for vericloud-face (C5). Runs anywhere, no AWS account needed:
Rekognition responses are faked with botocore Stubber, and the expected
params also assert the contract call direction (source=selfie, target=id card).

Run:  uv run --with boto3 --with pytest pytest test_handler.py -v
"""

import os

# Dummy credentials so boto3.client() succeeds on machines with no AWS setup.
# Stubber intercepts every API call; nothing leaves this machine.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import pytest
from botocore.stub import Stubber

import handler


EVENT = {
    "application_id": "c5-unit",
    "bucket": "vericloud-raw-1009",
    "id_card_key": "raw/id-card/c5-unit.jpg",
    "selfie_key": "raw/selfie/c5-unit.jpg",
    "created_at": "2026-11-08T00:00:00Z",
}

EXPECTED_CALL = {
    "SourceImage": {"S3Object": {"Bucket": EVENT["bucket"], "Name": EVENT["selfie_key"]}},
    "TargetImage": {"S3Object": {"Bucket": EVENT["bucket"], "Name": EVENT["id_card_key"]}},
    "SimilarityThreshold": 0,
}


def call(response=None, error_code=None, event=None):
    """Invoke lambda_handler with compare_faces stubbed to one canned outcome."""
    stub = Stubber(handler.rekognition)
    if error_code is not None:
        stub.add_client_error("compare_faces", error_code)
    elif response is not None:
        stub.add_response("compare_faces", response, expected_params=EXPECTED_CALL)
    with stub:  # activate, assert every expected call happened, deactivate
        return handler.lambda_handler(EVENT if event is None else event, None)


def matches(*similarities):
    return {
        "SourceImageFace": {"BoundingBox": {}, "Confidence": 99.9},
        "FaceMatches": [{"Similarity": s, "Face": {"BoundingBox": {}, "Confidence": 99.9}}
                        for s in similarities],
    }


# --- C5 category 1: normal (same person) ---

def test_normal_rounds_to_two_decimals_and_passes():
    out = call(matches(99.98372))
    assert out == {"similarity": 99.98, "face_matched": True}


def test_boundary_similarity_80_passes():
    out = call(matches(80.0))
    assert out["face_matched"] is True  # rule: similarity >= 80


def test_multiple_matches_takes_highest():
    out = call(matches(81.2, 95.5, 88.8))
    assert out["similarity"] == 95.5


# --- C5 category 2: different person (low similarity) ---

def test_different_person_below_threshold_fails():
    out = call(matches(42.156))
    assert out == {"similarity": 42.16, "face_matched": False}


def test_just_below_threshold_fails():
    out = call(matches(79.99))
    assert out["face_matched"] is False


# --- C5 category 3: no face ---

def test_no_face_empty_match_list_raises_contract_error():
    with pytest.raises(handler.FaceNotDetectedError):
        call({"SourceImageFace": {"BoundingBox": {}, "Confidence": 99.9},
              "FaceMatches": []})


def test_no_face_invalid_parameter_maps_to_not_detected():
    # Real Rekognition behavior observed 2026-11-06: an image with no face
    # at all makes CompareFaces throw InvalidParameterException, not an
    # empty match list. Both paths must end in FaceNotDetectedError.
    with pytest.raises(handler.FaceNotDetectedError):
        call(error_code="InvalidParameterException")


# --- contract robustness ---

def test_corrupt_image_maps_to_compare_error():
    with pytest.raises(handler.FaceCompareError):
        call(error_code="InvalidImageFormatException")


def test_other_service_errors_map_to_compare_error():
    with pytest.raises(handler.FaceCompareError):
        call(error_code="ThrottlingException")


def test_missing_field_in_event_maps_to_compare_error():
    with pytest.raises(handler.FaceCompareError):
        call(event={"bucket": EVENT["bucket"], "id_card_key": EVENT["id_card_key"]})
