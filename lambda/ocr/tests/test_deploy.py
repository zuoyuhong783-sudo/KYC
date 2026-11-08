from unittest.mock import Mock

import pytest

import deploy


def test_rejects_wrong_region_or_role_before_any_network(monkeypatch, tmp_path):
    factory = Mock()
    monkeypatch.setattr(deploy.boto3, "client", factory)
    with pytest.raises(ValueError):
        deploy.deploy("123456789012.dkr.ecr.us-west-2.amazonaws.com/vericloud-ocr:v1",
                      "arn:aws:iam::123456789012:role/LabRole", tmp_path / "evidence.json")
    factory.assert_not_called()


def test_preserves_existing_zip_function(monkeypatch, tmp_path):
    client = Mock()
    client.get_function.return_value = {"Configuration": {"PackageType": "Zip"}}
    monkeypatch.setattr(deploy.boto3, "client", lambda *a, **kw: client)
    with pytest.raises(ValueError, match="preserved"):
        deploy.deploy("123456789012.dkr.ecr.us-east-1.amazonaws.com/vericloud-ocr:v1",
                      "arn:aws:iam::123456789012:role/LabRole", tmp_path / "evidence.json")
    client.update_function_code.assert_not_called()


def test_updates_only_ocr_and_writes_redacted_deployment_evidence(monkeypatch, tmp_path):
    client = Mock()
    config = {"PackageType": "Image", "FunctionName": "vericloud-ocr", "FunctionArn": "arn:example",
              "Environment": {"Variables": {"SECRET": "do-not-store"}}}
    client.get_function.return_value = {"Configuration": config, "Code": {"ResolvedImageUri": "image@sha256:example", "Location": "temporary-secret"}}
    monkeypatch.setattr(deploy.boto3, "client", lambda *a, **kw: client)
    output = tmp_path / "evidence.json"
    deploy.deploy("123456789012.dkr.ecr.us-east-1.amazonaws.com/vericloud-ocr:v1",
                  "arn:aws:iam::123456789012:role/LabRole", output)
    client.update_function_configuration.assert_called_once_with(FunctionName="vericloud-ocr", Role="arn:aws:iam::123456789012:role/LabRole", MemorySize=1536, Timeout=60)
    assert "do-not-store" not in output.read_text()
    assert "temporary-secret" not in output.read_text()
