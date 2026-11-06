#!/usr/bin/env python3
"""
压测结果收集器 —— 从 DynamoDB + SQS 汇总指标（E / Li Hengchen）

必须等重试跑完再跑本脚本（坏文件要经 3 次 retry 才进 DLQ），
默认会轮询到数据稳定（--stable-window 秒内计数不变）或超时为止。

两处口径：
  · service latency  = created_at  → processed_at（starter 收到消息 → 写库）
  · end-to-end       = t_submit_utc → processed_at（客户端上传完成 → 写库，含 S3 事件与冷启动）

DLQ 用 application_id 做集合比对，证明"20/20 坏文件都进了 DLQ"，而不是只看一个累计数。

用法：
  # 每轮开跑前先清 DLQ（purge 约 60 s 生效，所以必须在压测前调用）
  python tests/collect_results.py --table T --dlq-url URL \\
      --submitted /tmp/warmup.csv --purge-dlq --no-wait --out /tmp/warmup.csv

  # 压测后 10 分钟
  python tests/collect_results.py --table vericloud-kyc-table \\
      --dlq-url <dlq-url> --submitted results/load_test_r1_submitted.csv \\
      --out results/load_test_r1_summary.csv --latex tables/tab_e_loadtest.tex
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

METRIC_COLUMNS = ["submitted", "in_table", "pass", "review", "fail", "dlq", "dlq_corrupted",
                  "pending", "p50_s", "p90_s", "p95_s", "p99_s",
                  "e2e_p50_s", "e2e_p95_s", "e2e_p99_s", "match_rate"]

APP_ID_RE = re.compile(r"raw/(?:id-card|selfie)/([0-9a-fA-F-]{36})")


def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(ts, fmt)
            return dt.replace(tzinfo=dt.tzinfo or timezone.utc)
        except ValueError:
            continue
    return None


def percentile(values: list[float], q: float, label: str) -> float:
    if not values:
        sys.exit(f"[FAIL] 没有可计算的延迟样本（{label}）：检查 D 是否写 processed_at，"
                 f"以及 submitted.csv 的 t_submit_utc 是否为空")
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def scan_since(table, since_iso: str) -> list[dict]:
    items: list[dict] = []
    kwargs = {
        "FilterExpression": "created_at >= :s",
        "ExpressionAttributeValues": {":s": since_iso},
    }
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def wait_until_stable(table, since_iso: str, stable_window: int, max_wait: int) -> list[dict]:
    deadline = time.monotonic() + max_wait
    last_count, stable_since = -1, time.monotonic()
    items: list[dict] = []
    while time.monotonic() < deadline:
        items = scan_since(table, since_iso)
        if len(items) != last_count:
            last_count, stable_since = len(items), time.monotonic()
            print(f"  表中记录 {last_count} 条，继续等待…")
        elif time.monotonic() - stable_since >= stable_window:
            print(f"  记录数已稳定在 {last_count} 条（{stable_window}s 无变化）")
            return items
        time.sleep(10)
    print(f"[warn] 等待超时，按当前 {len(items)} 条汇总")
    return items


def dlq_application_ids(sqs, url: str, max_msgs: int = 300) -> set[str]:
    """不删除、只看：从 DLQ 消息体里把 application_id 抠出来做集合比对。"""
    seen: set[str] = set()
    ids: set[str] = set()
    idle = 0
    attempts = 0
    max_attempts = max_msgs // 10 + 3
    while idle < 2 and len(seen) < max_msgs and attempts < max_attempts:
        attempts += 1
        resp = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10,
                                   AttributeNames=["All"], VisibilityTimeout=0, WaitTimeSeconds=1)
        msgs = resp.get("Messages", [])
        if not msgs:
            idle += 1
            continue
        idle = 0
        for m in msgs:
            if m["MessageId"] in seen:
                continue
            seen.add(m["MessageId"])
            hit = APP_ID_RE.search(m.get("Body", ""))
            if hit:
                ids.add(hit.group(1).lower())
    return ids


def main() -> None:
    ap = argparse.ArgumentParser(description="压测结果收集（E）")
    ap.add_argument("--table", default=None, help="DynamoDB 表名；只清 DLQ 时可为空")
    ap.add_argument("--queue-url", default=None)
    ap.add_argument("--dlq-url", default=None)
    ap.add_argument("--purge-dlq", action="store_true",
                    help="压测前清空 DLQ（每轮开跑前用，避免累计值污染）")
    ap.add_argument("--purge-only", action="store_true",
                    help="只清空 DLQ 然后退出（不需要 --submitted）")
    ap.add_argument("--submitted", default=None, help="load_test.py 产出的 submitted.csv")
    ap.add_argument("--manifest", default="tests/fixtures/manifest.csv")
    ap.add_argument("--out", default="results/load_test_r1_summary.csv")
    ap.add_argument("--latex", default=None, help="可选：输出 booktabs 表格 .tex")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--max-wait", type=int, default=900, help="最长等待秒数")
    ap.add_argument("--stable-window", type=int, default=60, help="计数稳定多少秒算跑完")
    ap.add_argument("--no-wait", action="store_true", help="不等待，立即汇总")
    args = ap.parse_args()

    import boto3

    if args.purge_only:
        if not args.dlq_url:
            sys.exit("--purge-only 需要 --dlq-url")
        boto3.client("sqs", region_name=args.region).purge_queue(QueueUrl=args.dlq_url)
        print(f"[ok] 已请求清空 DLQ：{args.dlq_url}（约 60 s 生效，请在压测开始前至少 1 分钟执行）")
        return

    if not args.submitted:
        sys.exit("缺少 --submitted（load_test.py 产出的 CSV）；只清 DLQ 请用 --purge-only")
    submitted = list(csv.DictReader(Path(args.submitted).open(encoding="utf-8")))
    if not submitted:
        sys.exit("submitted.csv 为空")
    since = min(s["t_submit_utc"] for s in submitted)
    since_dt = parse_iso(since) or datetime.now(timezone.utc)
    since_iso = (since_dt - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"收集窗口：created_at >= {since_iso}（提交数 {len(submitted)}）")

    sqs = boto3.client("sqs", region_name=args.region) if (args.dlq_url or args.queue_url) else None

    if args.purge_dlq:
        if not args.dlq_url:
            sys.exit("--purge-dlq 需要同时给 --dlq-url")
        sqs.purge_queue(QueueUrl=args.dlq_url)
        print("[info] 已请求清空 DLQ（约 60 s 生效，务必在压测前执行）")

    items: list[dict] = []
    if args.table:
        table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
        items = scan_since(table, since_iso) if args.no_wait \
            else wait_until_stable(table, since_iso, args.stable_window, args.max_wait)
        print(f"表中命中 {len(items)} 条")

    # 预期结论
    expected: dict[str, dict] = {}
    expected_by_cat: dict[str, Counter] = {}
    manifest = Path(args.manifest)
    if manifest.exists():
        for row in csv.DictReader(manifest.open(encoding="utf-8")):
            expected[row["case_id"]] = row
            expected_by_cat.setdefault(row["category"], Counter())[row["expected_status"]] += 1

    # DLQ：按 application_id 做集合比对，拿本轮的真实命中数
    dlq_ids: set[str] = set()
    if sqs and args.dlq_url:
        dlq_ids = dlq_application_ids(sqs, args.dlq_url)
        print(f"DLQ 命中 {len(dlq_ids)} 条（按 application_id 去重，未删除消息）")

    submitted_ids = {s["application_id"] for s in submitted}
    CORRUPT_CATEGORIES = {"zero_byte", "wrong_format"}
    corrupted_ids = {s["application_id"] for s in submitted if s["category"] in CORRUPT_CATEGORIES}
    dlq_hit = len(dlq_ids & submitted_ids)
    dlq_hit_corrupted = len(dlq_ids & corrupted_ids)

    by_id = {it["application_id"]: it for it in items}
    status_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()
    svc_lat: list[float] = []     # starter 收消息 → 写库
    e2e_lat: list[float] = []     # 客户端上传完成 → 写库
    per_category: dict[str, Counter] = {}
    matched = 0

    for sub in submitted:
        app_id = sub["application_id"]
        cat = sub["category"]
        per_category.setdefault(cat, Counter())
        item = by_id.get(app_id)
        if item is None:
            actual = "DLQ" if app_id in dlq_ids else "PENDING"
        else:
            actual = item.get("review_status", "UNKNOWN")
            status_counter[actual] += 1
            if actual != "PASS":
                reason_counter[item.get("reason", "-")] += 1
            created = parse_iso(item.get("created_at", ""))
            processed = parse_iso(item.get("processed_at", ""))
            if created and processed:
                svc_lat.append((processed - created).total_seconds())
            started = parse_iso(sub.get("t_submit_utc", ""))
            if started and processed:
                e2e_lat.append((processed - started).total_seconds())
        per_category[cat][actual] += 1

        exp = expected.get(sub["case_id"], {})
        if exp.get("expected_status") and exp["expected_status"] != "DLQ" \
                and actual == exp["expected_status"]:
            matched += 1

    comparable = sum(1 for s in submitted
                     if expected.get(s["case_id"], {}).get("expected_status") not in (None, "DLQ"))

    summary = {
        "submitted": len(submitted),
        "in_table": len(items),
        "pass": status_counter.get("PASS", 0),
        "review": status_counter.get("NEEDS_HUMAN_REVIEW", 0),
        "fail": status_counter.get("FAIL", 0),
        "dlq": dlq_hit,
        "dlq_corrupted": f"{dlq_hit_corrupted}/{len(corrupted_ids)}",
        "pending": max(0, len(submitted) - len(items) - dlq_hit),
        "p50_s": round(percentile(svc_lat, 0.50, "service p50"), 2),
        "p90_s": round(percentile(svc_lat, 0.90, "service p90"), 2),
        "p95_s": round(percentile(svc_lat, 0.95, "service p95"), 2),
        "p99_s": round(percentile(svc_lat, 0.99, "service p99"), 2),
        "e2e_p50_s": round(percentile(e2e_lat, 0.50, "end-to-end p50"), 2),
        "e2e_p95_s": round(percentile(e2e_lat, 0.95, "end-to-end p95"), 2),
        "e2e_p99_s": round(percentile(e2e_lat, 0.99, "end-to-end p99"), 2),
        "match_rate": f"{matched}/{comparable}" if comparable else "n/a",
    }

    print("\n=== 汇总 ===")
    for k in METRIC_COLUMNS:
        print(f"  {k:14s} {summary[k]}")
    print("\n=== 分类实际分布 ===")
    for cat, counter in sorted(per_category.items()):
        print(f"  {cat:14s} {dict(counter)}")
    if reason_counter:
        print("\n=== 非 PASS 原因 ===")
        for reason, n in reason_counter.most_common():
            print(f"  {reason:24s} {n}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        for k in METRIC_COLUMNS:
            writer.writerow([k, summary[k]])
        writer.writerow([])
        writer.writerow(["category", "PASS", "NEEDS_HUMAN_REVIEW", "FAIL", "DLQ", "PENDING", "expected"])
        for cat, counter in sorted(per_category.items()):
            writer.writerow([cat, counter.get("PASS", 0), counter.get("NEEDS_HUMAN_REVIEW", 0),
                             counter.get("FAIL", 0), counter.get("DLQ", 0), counter.get("PENDING", 0),
                             ";".join(f"{k}x{v}" for k, v in sorted(expected_by_cat.get(cat, {}).items())) or "-"])
    print(f"\n已写入 {out}")

    if args.latex:
        latex = [
            "% 由 tests/collect_results.py 自动生成，请勿手改数字",
            "% 两轮数据：每轮各生成一份，再合并成两列表格",
            "\\begin{tabular}{lr}",
            "\\toprule",
            "Metric & Value \\\\",
            "\\midrule",
            f"Applications submitted & {summary['submitted']} \\\\",
            f"Records persisted & {summary['in_table']} \\\\",
            f"Verdicts PASS / REVIEW / FAIL & {summary['pass']} / {summary['review']} / {summary['fail']} \\\\",
            f"Corrupted isolated in DLQ (matched by id) & {summary['dlq_corrupted']} \\\\",
            f"p50 / p90 / p95 / p99 service latency (s) & {summary['p50_s']} / {summary['p90_s']} / "
            f"{summary['p95_s']} / {summary['p99_s']} \\\\",
            f"p50 / p95 / p99 end-to-end latency (s) & {summary['e2e_p50_s']} / {summary['e2e_p95_s']} / "
            f"{summary['e2e_p99_s']} \\\\",
            "\\bottomrule",
            "\\end{tabular}",
        ]
        Path(args.latex).parent.mkdir(parents=True, exist_ok=True)
        Path(args.latex).write_text("\n".join(latex) + "\n", encoding="utf-8")
        print(f"已写入 {args.latex}")

    if summary["pending"] > 0:
        print(f"[warn] 仍有 {summary['pending']} 个申请未出结果（既不在表里也不在 DLQ），"
              f"可能还在重试或真的丢了")
        sys.exit(3)


if __name__ == "__main__":
    main()
