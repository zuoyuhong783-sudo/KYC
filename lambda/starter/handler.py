import os
import json
import boto3
import io
from PIL import Image

s3_client = boto3.client('s3')
sfn_client = boto3.client('stepfunctions')

# 从环境变量读取状态机 ARN
STATE_MACHINE_ARN = os.environ.get('STATE_MACHINE_ARN')

ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png')

class PrecheckFailedError(Exception):
    """文件预检失败异常"""
    pass

def validate_s3_image(bucket: str, key: str):
    """
    预检 S3 图片：
    1. 校验扩展名
    2. 校验文件存在且大于 0 字节
    3. PIL 完整性校验
    """
    if not key.lower().endswith(ALLOWED_EXTENSIONS):
        raise PrecheckFailedError(f"Invalid extension for file: {key}")

    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
    except Exception as e:
        raise PrecheckFailedError(f"File not found in S3 ({bucket}/{key}): {str(e)}")

    content_length = response.get('ContentLength', 0)
    if content_length <= 0:
        raise PrecheckFailedError(f"File is empty (0 bytes): {key}")

    try:
        file_bytes = response['Body'].read()
        image = Image.open(io.BytesIO(file_bytes))
        image.verify()
    except Exception as e:
        raise PrecheckFailedError(f"Corrupted or invalid image file ({key}): {str(e)}")

def find_id_card_key(bucket: str, application_id: str) -> str:
    """
    针对证件照扩展名：依次尝试 .jpg, .jpeg, .png
    路径统一使用连字符 raw/id-card/
    """
    for ext in ('.jpg', '.jpeg', '.png'):
        candidate_key = f"raw/id-card/{application_id}{ext}"
        try:
            s3_client.head_object(Bucket=bucket, Key=candidate_key)
            return candidate_key
        except Exception:
            continue
    raise PrecheckFailedError(f"ID card image not found for {application_id} (tried .jpg, .jpeg, .png under raw/id-card/)")

def lambda_handler(event, context):
    if not STATE_MACHINE_ARN:
        raise ValueError("Environment variable STATE_MACHINE_ARN is not configured.")

    for record in event.get('Records', []):
        body_str = record.get('body', '{}')
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            raise ValueError(f"Malformed SQS message body: {body_str}")

        # 兼容直接 S3 事件与 SNS 包装的 S3 事件
        if 'Message' in body and isinstance(body['Message'], str):
            s3_event = json.loads(body['Message'])
        else:
            s3_event = body

        # S3 首次配置通知时发来的测试消息，直接跳过
        if s3_event.get('Event') == 's3:TestEvent':
            print("Skipping S3 test event")
            continue

        s3_records = s3_event.get('Records', [])
        if not s3_records:
            raise ValueError("No S3 records found in the payload.")

        record_0 = s3_records[0]
        s3_info = record_0.get('s3', {})
        bucket = s3_info.get('bucket', {}).get('name')
        selfie_key = s3_info.get('object', {}).get('key')

        if not bucket or not selfie_key:
            raise ValueError(f"Missing bucket or object key: {s3_info}")

        created_at = record_0.get('eventTime')

        # 从 selfie 路径解析 application_id (路径约定: raw/selfie/<id>.*)
        filename = os.path.basename(selfie_key)
        application_id = os.path.splitext(filename)[0]

        # 路径使用 raw/id-card/ 连字符，并依次探测不同扩展名
        id_card_key = find_id_card_key(bucket, application_id)

        # 预检两张图片合法性
        validate_s3_image(bucket, selfie_key)
        validate_s3_image(bucket, id_card_key)

        # 构造下游标准 Payload
        payload = {
            "application_id": application_id,
            "bucket": bucket,
            "id_card_key": id_card_key,
            "selfie_key": selfie_key,
            "created_at": created_at
        }

        # 幂等启动状态机
        try:
            response = sfn_client.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                name=application_id,
                input=json.dumps(payload)
            )
            print(f"Successfully started execution for {application_id}: {response['executionArn']}")
        except sfn_client.exceptions.ExecutionAlreadyExists:
            print(f"Execution {application_id} already exists. Skipping duplicate.")
        except Exception as e:
            raise RuntimeError(f"Failed to start Step Functions execution: {str(e)}")

    return {
        "statusCode": 200,
        "body": json.dumps("Starter Lambda executed successfully.")
    }
