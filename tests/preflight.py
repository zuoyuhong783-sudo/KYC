#!/usr/bin/env python3
"""
压测前健康检查 + 契约自检 —— 一条命令核对演示账号是否符合 01 方案（E / Li Hengchen）

为什么需要：Learner Lab 会话约 4 小时自动停止，资源还在但 Lambda 要重新测活；
压测跑到一半发现状态机没 ACTIVE，一轮数据就废了。

除了"资源在不在"，还核对 §9.2「一致关」的硬指标：
  阈值 80 / 重试 3 次 / DLQ 保留 14 天 / 可见性超时 / 桶私有 / SSE-S3 / 生命周期 7 天 /
  Lambda 运行时 python3.12 + 1024MB + 60s / 状态机 STANDARD

用法：
  python tests/preflight.py --bucket vericloud-raw-xxxx --table vericloud-kyc-table
  # M2 之前 Lambda 还没全上，加 --allow-missing-functions
"""
from __future__ import annotations

import argparse
import json
import sys

OK, BAD, WARN = "✅", "❌", "⚠️ "


def main() -> None:
    ap = argparse.ArgumentParser(description="VeriCloud 压测前健康检查与契约自检（E）")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--table", default="vericloud-kyc-table")
    ap.add_argument("--queue", default="vericloud-ingest-queue")
    ap.add_argument("--dlq", default="vericloud-ingest-dlq")
    ap.add_argument("--state-machine", default="vericloud-kyc-workflow")
    ap.add_argument("--topics", default="vericloud-kyc-topic,vericloud-ops-alarm")
    ap.add_argument("--functions", default="vericloud-starter,vericloud-ocr,vericloud-face,vericloud-notify")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--allow-missing-functions", action="store_true",
                    help="M2 之前跑：允许 Lambda 还不存在")
    ap.add_argument("--allow-missing-topics", action="store_true",
                    help="M2 之前跑：允许 SNS 主题还没建（F 尚未交付）")
    args = ap.parse_args()

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    session = boto3.session.Session(region_name=args.region)
    problems: list[str] = []
    checks: list[tuple[str, str, str]] = []

    def record(name: str, ok: bool, detail: str, *, blocking: bool = True) -> None:
        checks.append((OK if ok else (BAD if blocking else WARN), name, detail))
        if not ok and blocking:
            problems.append(f"{name}: {detail}")

    # 0) 身份
    try:
        ident = session.client("sts").get_caller_identity()
        record("AWS 身份", True, ident["Arn"])
    except (BotoCoreError, ClientError) as exc:
        record("AWS 身份", False, f"凭证无效：{exc}")
        print("凭证都没配好，后面不用查了。")
        for mark, name, detail in checks:
            print(f"  {mark} {name}: {detail}")
        sys.exit(1)

    # 1) S3
    s3 = session.client("s3")
    try:
        s3.head_bucket(Bucket=args.bucket)
        record("S3 桶", True, args.bucket)
    except (BotoCoreError, ClientError) as exc:
        record("S3 桶", False, str(exc))

    # 1b) 桶的安全与生命周期（C 的职责，只有自检器能替他抓）
    try:
        pab = s3.get_public_access_block(Bucket=args.bucket)["PublicAccessBlockConfiguration"]
        ok = all(pab.get(k) for k in ("BlockPublicAcls", "IgnorePublicAcls",
                                      "BlockPublicPolicy", "RestrictPublicBuckets"))
        record("桶阻止公开访问", ok, "四项全部开启" if ok else f"未全开：{pab}")
    except (BotoCoreError, ClientError) as exc:
        record("桶阻止公开访问", False, str(exc))

    try:
        enc = s3.get_bucket_encryption(Bucket=args.bucket)["ServerSideEncryptionConfiguration"]
        algo = enc["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
        record("桶默认加密", algo == "AES256", f"SSEAlgorithm={algo}")
    except (BotoCoreError, ClientError):
        record("桶默认加密", False, "未配置默认加密（应为 SSE-S3）")

    try:
        rules = s3.get_bucket_lifecycle_configuration(Bucket=args.bucket)["Rules"]
        days = [r.get("Expiration", {}).get("Days") for r in rules]
        record("raw/ 生命周期 7 天", 7 in days, f"expiration days={days}")
    except (BotoCoreError, ClientError):
        record("raw/ 生命周期 7 天", False, "未配置生命周期规则", blocking=False)

    # 2) DynamoDB
    table_desc: dict = {}
    try:
        desc = session.client("dynamodb").describe_table(TableName=args.table)["Table"]
        table_desc = desc
        streams = desc.get("StreamSpecification", {}).get("StreamEnabled", False)
        record("DynamoDB 表", desc.get("TableStatus") == "ACTIVE",
               f"{args.table} status={desc.get('TableStatus')} streams={'ON' if streams else 'OFF'}")
        if not streams:
            record("DynamoDB Streams", False, "未开启，notify Lambda 收不到事件", blocking=False)
    except (BotoCoreError, ClientError) as exc:
        record("DynamoDB 表", False, str(exc))

    # 3) SQS + 红线
    sqs = session.client("sqs")
    for name in (args.queue, args.dlq):
        try:
            url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
            attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])["Attributes"]
            depth = attrs.get("ApproximateNumberOfMessages", "0")
            record(f"SQS {name}", True, f"depth={depth}{' (有积压)' if depth != '0' else ''}")

            if name == args.dlq:
                keep = int(attrs.get("MessageRetentionPeriod", "0"))
                record("DLQ 保留 14 天", keep == 1209600, f"MessageRetentionPeriod={keep}")
            else:
                redrive = json.loads(attrs.get("RedrivePolicy", "{}"))
                mrc = redrive.get("maxReceiveCount")
                record("重试上限 3 次", str(mrc) == "3", f"maxReceiveCount={mrc}")
                record("可见性超时 >= 6x starter 超时", int(attrs.get("VisibilityTimeout", 0)) >= 360,
                       f"VisibilityTimeout={attrs.get('VisibilityTimeout')}", blocking=False)
        except (BotoCoreError, ClientError) as exc:
            record(f"SQS {name}", False, str(exc))

    # 3b) 连线：资源全绿但线没接，包会全丢
    lam = session.client("lambda")
    queue_arn = None
    try:
        q_url = sqs.get_queue_url(QueueName=args.queue)["QueueUrl"]
        queue_arn = sqs.get_queue_attributes(
            QueueUrl=q_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]

        try:
            conf = s3.get_bucket_notification_configuration(Bucket=args.bucket)
            qc = conf.get("QueueConfigurations", [])
            hit = [c for c in qc if c.get("QueueArn") == queue_arn
                   and any(r.get("Name") == "prefix" and r.get("Value") == "raw/selfie/"
                           for r in c.get("Filter", {}).get("Key", {}).get("FilterRules", []))]
            record("S3→SQS 通知（raw/selfie/）", bool(hit),
                   f"{len(qc)} 条队列通知，命中 {len(hit)} 条")
        except (BotoCoreError, ClientError) as exc:
            record("S3→SQS 通知（raw/selfie/）", False, str(exc))

        try:
            m = lam.list_event_source_mappings(EventSourceArn=queue_arn,
                                               FunctionName="vericloud-starter")["EventSourceMappings"]
            record("SQS→starter 事件源", any(x["State"] == "Enabled" for x in m), f"{len(m)} 个映射")
        except (BotoCoreError, ClientError) as exc:
            record("SQS→starter 事件源", False, str(exc))

        stream_arn = table_desc.get("LatestStreamArn")
        if stream_arn:
            try:
                m = lam.list_event_source_mappings(EventSourceArn=stream_arn,
                                                   FunctionName="vericloud-notify")["EventSourceMappings"]
                record("Streams→notify 事件源", any(x["State"] == "Enabled" for x in m),
                       f"{len(m)} 个映射", blocking=False)
            except (BotoCoreError, ClientError) as exc:
                record("Streams→notify 事件源", False, str(exc), blocking=False)
        else:
            record("Streams→notify 事件源", False, "表没有 Stream ARN（Streams 未开启）", blocking=False)
    except (BotoCoreError, ClientError) as exc:
        record("S3→SQS 通知（raw/selfie/）", False, f"取队列 ARN 失败：{exc}")

    # 4) Step Functions
    try:
        sfn = session.client("stepfunctions")
        arn = f"arn:aws:states:{args.region}:{ident['Account']}:stateMachine:{args.state_machine}"
        desc = sfn.describe_state_machine(stateMachineArn=arn)
        record("Step Functions", desc["status"] == "ACTIVE", f"{args.state_machine} status={desc['status']}")
        record("状态机类型 STANDARD", desc["type"] == "STANDARD", f"type={desc['type']}", blocking=False)
    except (BotoCoreError, ClientError) as exc:
        record("Step Functions", False, str(exc))

    # 5) SNS
    try:
        topics = {t["TopicArn"].split(":")[-1] for t in session.client("sns").list_topics()["Topics"]}
        for name in args.topics.split(","):
            name = name.strip()
            record(f"SNS {name}", name in topics, "已存在" if name in topics else "未创建",
                   blocking=(not args.allow_missing_topics and name != "vericloud-ops-alarm"))
    except (BotoCoreError, ClientError) as exc:
        record("SNS", False, str(exc))

    # 6) Lambda 运行时与规格
    for name in args.functions.split(","):
        name = name.strip()
        try:
            cfg = lam.get_function(FunctionName=name)["Configuration"]
            record(f"Lambda {name}", True, "就绪")
            record(f"{name} 运行时", cfg.get("Runtime") == "python3.12",
                   cfg.get("Runtime", "?"), blocking=False)
            record(f"{name} 内存/超时", cfg.get("MemorySize", 0) >= 1024 and cfg.get("Timeout", 0) <= 60,
                   f"{cfg.get('MemorySize')}MB / {cfg.get('Timeout')}s", blocking=False)
        except (BotoCoreError, ClientError):
            record(f"Lambda {name}", False, "未部署", blocking=not args.allow_missing_functions)

    print(f"\n=== 压测前检查（{args.region}）===")
    for mark, name, detail in checks:
        print(f"  {mark} {name}: {detail}")

    if problems:
        print(f"\n[FAIL] {len(problems)} 项阻塞，先修再压测：")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\n[ok] 资源齐备，可以开始压测。建议先跑 10 个申请的预演。")


if __name__ == "__main__":
    main()
