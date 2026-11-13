import os
import json
import boto3
import io
from datetime import datetime, timezone
from PIL import Image, ImageOps

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
    3. PIL 完整性及像素解码校验 (load)
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
        image.load()
    except Exception as e:
        raise PrecheckFailedError(f"Corrupted or invalid image file ({key}): {str(e)}")
    return image

def _find_key(bucket: str, prefix: str, application_id: str):
    """在 prefix 下依次尝试 .jpg / .jpeg / .png，找不到返回 None"""
    for ext in ('.jpg', '.jpeg', '.png'):
        candidate_key = f"{prefix}{application_id}{ext}"
        try:
            s3_client.head_object(Bucket=bucket, Key=candidate_key)
            return candidate_key
        except Exception:
            continue
    return None

def stitch_front_back(front: Image.Image, back: Image.Image) -> bytes:
    """
    interface v1.5：身份证正面（姓名、号码、人像）在上，反面（签发机关、有效期限）在下，
    拼成一张图。OCR 与人脸比对都读这一张，所以它们的代码和镜像不用改。
    """
    width, gap = 1200, 40
    parts = []
    for img in (front, back):
        img = ImageOps.exif_transpose(img).convert('RGB')
        parts.append(img.resize((width, max(1, round(img.height * width / img.width))), Image.LANCZOS))
    canvas = Image.new('RGB', (width, parts[0].height + gap + parts[1].height), 'white')
    canvas.paste(parts[0], (0, 0))
    canvas.paste(parts[1], (0, parts[0].height + gap))
    out = io.BytesIO()
    canvas.save(out, format='JPEG', quality=92)
    return out.getvalue()

def find_id_card_key(bucket: str, application_id: str) -> str:
    """
    1) 单张证件图 raw/id-card/<id>.*（旧前端、测试素材）：直接使用。
    2) 正反两面 raw/id-card-front/<id>.* + raw/id-card-back/<id>.*（v1.5）：预检两面，
       拼成 raw/id-card/<id>.jpg 后返回这个 key。重试时第 1 步就能找到拼好的图。
    """
    key = _find_key(bucket, 'raw/id-card/', application_id)
    if key:
        return key
    front_key = _find_key(bucket, 'raw/id-card-front/', application_id)
    back_key = _find_key(bucket, 'raw/id-card-back/', application_id)
    if front_key and not back_key:
        raise PrecheckFailedError(f"ID card back side not found for {application_id} (raw/id-card-back/)")
    if not front_key:
        raise PrecheckFailedError(f"ID card image not found for {application_id} (tried raw/id-card/ and raw/id-card-front/)")
    front = validate_s3_image(bucket, front_key)
    back = validate_s3_image(bucket, back_key)
    key = f"raw/id-card/{application_id}.jpg"
    s3_client.put_object(Bucket=bucket, Key=key, Body=stitch_front_back(front, back), ContentType='image/jpeg')
    print(f"Stitched {front_key} + {back_key} -> {key}")
    return key

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

        # 在预检之后生成时间，并格式化为与 created_at 一致的毫秒级 Z 结尾格式
        received_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

        # 构造下游标准 Payload
        payload = {
            "application_id": application_id,
            "bucket": bucket,
            "id_card_key": id_card_key,
            "selfie_key": selfie_key,
            "created_at": created_at,
            "received_at": received_at
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
