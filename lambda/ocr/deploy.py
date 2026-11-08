"""Deploy an already-pushed image to the existing Learner Lab role.

Run explicitly after local image validation. Uses standard boto3 credentials,
never creates IAM roles or uploads documents, and never changes the interface.
"""

import argparse
import json
import re
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


NAME = "vericloud-ocr"
REGION = "us-east-1"


def deploy(image_uri: str, role_arn: str, output: Path):
    role = re.fullmatch(r"arn:aws:iam::(\d{12}):role/(?:[\w+=,.@-]+/)*LabRole", role_arn)
    image = re.fullmatch(r"(\d{12})\.dkr\.ecr\.us-east-1\.amazonaws\.com/[a-z0-9._/-]+(?::[\w.-]+|@sha256:[a-f0-9]{64})", image_uri)
    if not role or not image or role[1] != image[1]:
        raise ValueError("Use a us-east-1 private ECR image and a LabRole ARN in the same account")
    client = boto3.client("lambda", region_name=REGION)
    try:
        existing = client.get_function(FunctionName=NAME)
    except client.exceptions.ResourceNotFoundException:
        existing = None
    if existing:
        if existing["Configuration"]["PackageType"] != "Image":
            raise ValueError("Existing vericloud-ocr is not an image function; preserved without changes")
        # Existing architecture must match the documented linux/amd64 image.
        if existing["Configuration"].get("Architectures", ["x86_64"]) != ["x86_64"]:
            raise ValueError("Existing function is not x86_64; preserved without changes")
        client.update_function_code(FunctionName=NAME, ImageUri=image_uri)
        client.get_waiter("function_updated_v2").wait(FunctionName=NAME)
        client.update_function_configuration(FunctionName=NAME, Role=role_arn, MemorySize=1536, Timeout=60)
        client.get_waiter("function_updated_v2").wait(FunctionName=NAME)
    else:
        client.create_function(FunctionName=NAME, PackageType="Image", Role=role_arn,
                               Code={"ImageUri": image_uri}, Architectures=["x86_64"],
                               MemorySize=1536, Timeout=60)
        client.get_waiter("function_active_v2").wait(FunctionName=NAME)
    result = client.get_function(FunctionName=NAME)
    config = result["Configuration"]
    # Deliberately exclude environment values and the temporary ECR download URL.
    evidence = {key: config.get(key) for key in ("FunctionName", "FunctionArn", "Role", "MemorySize", "Timeout", "State", "LastUpdateStatus", "LastModified")}
    evidence["ImageUri"] = result["Code"].get("ResolvedImageUri", image_uri)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(config["FunctionArn"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create/update vericloud-ocr using an existing LabRole")
    parser.add_argument("--image-uri", required=True)
    parser.add_argument("--lab-role-arn", required=True)
    parser.add_argument("--output", type=Path, default=Path("build/ocr-deployment.json"))
    args = parser.parse_args()
    try:
        deploy(args.image_uri, args.lab_role_arn, args.output)
    except ClientError as exc:
        raise SystemExit(f"AWS deployment failed: {exc.response['Error']['Code']}") from None
