import os
import json
import boto3
import io
from datetime import datetime, timezone
from PIL import Image

s3_client = boto3.client('s3')
sfn_client = boto3.client('stepfunctions')

# 从环境变量读取状态机 ARN，避免硬编码
STATE_MACHINE_ARN = os.environ.get('STATE_MACHINE_ARN')

ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png')

class PrecheckFailedError(Exception):
    """文件预检失败异常"""
    pass

def validate_s3_image(bucket: str, key: str):
    """
    预检 S3 文件：
    1. 检查扩展名
    2. 检查文件是否存在且大于 0 字节
    3. 检查 PIL 能否正常解析
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

def lambda_handler(event, context):
    """
    处理 SQS 接收到的 S3 事件通知并启动 Step Functions 状态机
    """
    if not STATE_MACHINE_ARN:
        raise ValueError("Environment variable STATE_MACHINE_ARN is not configured.")

    for record in event.get('Records', []):
        body_str = record.get('body', '{}')
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            raise ValueError(f"Malformed SQS message body: {body_str}")

        # 支持 S3 直接发往 SQS 或通过 SNS 转发的包装格式
        if 'Message' in body and isinstance(body['Message'], str):
            s3_event = json.loads(body['Message'])
        else:
            s3_event = body

        s3_records = s3_event.get('Records', [])
        if not s3_records:
            raise ValueError("No S3 records found in the payload.")

        s3_info = s3_records[0].get('s3', {})
        bucket = s3_info.get('bucket', {}).get('name')
        selfie_key = s3_info.get('object', {}).get('key')

        if not bucket or not selfie_key:
            raise ValueError(f"Missing bucket or object key: {s3_info}")

        # 从 selfie 路径解析 application_id (路径约定: raw/selfie/<id>.jpg)
        filename = os.path.basename(selfie_key)
        application_id = os.path.splitext(filename)[0]

        # 根据约定推导身份证文件路径
        id_card_key = f"raw/id_card/{filename}"

        # 执行文件预检
        validate_s3_image(bucket, selfie_key)
        validate_s3_image(bucket, id_card_key)

        # 构建传递给下游状态机（Role B / Role C）的标准 Payload
        payload = {
            "application_id": application_id,
            "bucket": bucket,
            "id_card_key": id_card_key,
            "selfie_key": selfie_key,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # 启动状态机执行（使用 application_id 作为执行名防止重复执行）
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
