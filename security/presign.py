"""C2 — Issue two short-lived presigned PUT URLs for one KYC application.

Contract: docs/interface.md sections 1 and 3.
  - bucket:  vericloud-raw-1009 (us-east-1, Learner Lab region lock)
  - paths:   raw/id-card/<application_id><ext> and raw/selfie/<application_id><ext>
  - expiry:  300 seconds (5 minutes)
  - formats: .jpg / .jpeg / .png

The URLs are signed with SigV4 and carry the signer's session token, so they
stop working both when they expire and when the signing credentials do.

Usage:
    python presign.py <application_id> [--profile lab] [--ext .jpg] [--expires 300]

Output is JSON on stdout:
    {"application_id": ..., "bucket": ..., "expires_in": 300,
     "id_card_url": "https://...", "selfie_url": "https://..."}

A client uploads with:  curl -X PUT --data-binary @photo.jpg "<url>"
No Content-Type header is signed, so any HTTP client works unchanged.
"""

import argparse
import json
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ProfileNotFound

BUCKET = "vericloud-raw-1009"
REGION = "us-east-1"
EXPIRES_IN = 300  # seconds, per interface.md section 3
ALLOWED_EXT = (".jpg", ".jpeg", ".png")


def generate_upload_urls(application_id, ext=".jpg", *, bucket=BUCKET,
                         profile="lab", expires_in=EXPIRES_IN):
    """Return a dict with the two presigned PUT URLs for this application_id.

    Raises ValueError on bad input, so callers (and tests) can validate
    without touching AWS.
    """
    if not application_id or not application_id.strip():
        raise ValueError("application_id must not be empty")
    if not ext.startswith("."):
        ext = "." + ext
    if ext.lower() not in ALLOWED_EXT:
        raise ValueError(f"extension {ext!r} not allowed, use one of {ALLOWED_EXT}")

    session = boto3.Session(profile_name=profile, region_name=REGION)
    s3 = session.client("s3", config=Config(signature_version="s3v4"))

    urls = {}
    for doc_type in ("id-card", "selfie"):
        key = f"raw/{doc_type}/{application_id}{ext}"
        urls[f"{doc_type.replace('-', '_')}_url"] = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    return {
        "application_id": application_id,
        "bucket": bucket,
        "expires_in": expires_in,
        **urls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("application_id", help="e.g. 3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b")
    parser.add_argument("--profile", default="lab", help="AWS CLI profile (default: lab)")
    parser.add_argument("--ext", default=".jpg", help="image extension (default: .jpg)")
    parser.add_argument("--expires", type=int, default=EXPIRES_IN,
                        help="URL lifetime in seconds (default 300 per interface.md; "
                             "smaller values only for the expiry demo)")
    args = parser.parse_args()

    try:
        result = generate_upload_urls(
            args.application_id, args.ext,
            profile=args.profile, expires_in=args.expires,
        )
    except ValueError as e:
        print(f"Invalid input: {e}", file=sys.stderr)
        return 2
    except ProfileNotFound:
        print(f"AWS profile {args.profile!r} not found in ~/.aws/credentials", file=sys.stderr)
        return 2
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
