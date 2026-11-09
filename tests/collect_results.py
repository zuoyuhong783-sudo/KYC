#!/usr/bin/env python3
"""
压测结果收集器 —— 从 DynamoDB + SQS 汇总指标（E / Li Hengchen）

必须等重试跑完再跑本脚本（坏文件要经 3 次 retry 才进 DLQ，约 12–15 分钟），
默认轮询到「表行数 + DLQ 深度」两个信号都稳定，或超时为止。

三个时钟（与 docs/interface.md / Ch6 一致）：
  · ingress  = created_at  → received_at   （S3 事件投递 + 排队 + starter 冷启动）
  · service  = received_at → processed_at  （真正的流水线耗时）
  · end-to-end = t_submit_utc → processed_at（用户视角）
  记录里没有 received_at 时，service 退回 created_at → processed_at 并打印警告（含排队）。

退出码：
  0 全部出结果
  3 仍有 pending（既不在表里也不在 DLQ）
  4 结论或 reason 与 manifest 不符
  5 没有可计算的延迟样本

用法：
  # 每轮开跑前先清 DLQ（purge 约 60 s 生效，必须在压测前调用）
  python tests/collect_results.py --dlq-url <URL> --purge-only

  # 压测后
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
                  "pending", "match_rate", "reason_match", "queue_p50_s", "queue_p95_s",
                  "p50_s", "p90_s", "p95_s", "p99_s",
                  "e2e_p50_s", "e2e_p95_s", "e2e_p99_s"]

APP_ID_RE = re.compile(r"raw/(?:id-card|selfie)/([0-9a-fA-F-]{36})")
CORRUPT_CATEGORIES = {"zero_byte", "wrong_format"}


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
        print(f"[FAIL] 没有可计算的延迟样本（{label}）：检查 D 是否写 processed_at，"
              f"以及 submitted.csv 的 t_submit_utc 是否为空")
        sys.exit(5)
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


def dlq_depth(sqs, url: str) -> int:
    """轻量：只看可见消息数，不发 receive_message（那会把消息短暂置为 in-flight）。"""
    attrs = sqs.get_queue_attributes(
        QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])["Attributes"]
    return int(attrs.get("ApproximateNumberOfMessages", 0))


def wait_until_stable(table, since_iso, stable_window, max_wait,
                      dlq_depth=None, expected_total=None) -> list[dict]:
    """双信号：表行数 + DLQ 深度。两者都稳定，且总数达到预期，才算跑完。"""
    deadline = time.monotonic() + max_wait
    last_sig, stable_since = None, time.monotonic()
    items: list[dict] = []
    while time.monotonic() < deadline:
        items = scan_since(table, since_iso)
        dlq_n = dlq_depth() if dlq_depth else 0
        sig = (len(items), dlq_n)
        done = expected_total is None or (len(items) + dlq_n) >= expected_total
        if sig != last_sig:
            last_sig, stable_since = sig, time.monotonic()
            print(f"  表中 {sig[0]} 条 / DLQ {sig[1]} 条，继续等待…")
        elif done and time.monotonic() - stable_since >= stable_window:
            print(f"  已稳定：表中 {sig[0]} 条，DLQ {sig[1]} 条")
            return items
        time.sleep(10)
    print(f"[warn] 等待超时，按表中 {len(items)} 条汇总")
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
                    help="压测前清空 DLQ（与 --purge-only 等价）")
    ap.add_argument("--purge-only", action="store_true",
                    help="只清空 DLQ 然后退出（不需要 --submitted）")
    ap.add_argument("--submitted", default=None, help="load_test.py 产出的 submitted.csv")
    ap.add_argument("--manifest", default="tests/fixtures/manifest.csv")
    ap.add_argument("--out", default="results/load_test_r1_summary.csv")
    ap.add_argument("--latex", default=None, help="可选：输出 booktabs 表格 .tex")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--max-wait", type=int, default=1500,
                    help="最长等待秒数（默认 1500 s，覆盖 2×360 s 可见性超时）")
    ap.add_argument("--stable-window", type=int, default=60, help="双信号稳定多少秒算跑完")
    ap.add_argument("--no-wait", action="store_true", help="不等待，立即汇总")
    ap.add_argument("--allow-pending", action="store_true",
                    help="仍有 pending 时只警告、不 exit 3（预热轮用）")
    args = ap.parse_args()

    import boto3

    if args.purge_only or args.purge_dlq:
        if not args.dlq_url:
            sys.exit("--purge-only / --purge-dlq 需要 --dlq-url")
        boto3.client("sqs", region_name=args.region).purge_queue(QueueUrl=args.dlq_url)
        print(f"[ok] 已请求清空 DLQ：{args.dlq_url}（约 60 s 生效，请在压测开始前至少 1 分钟执行）")
        if args.purge_only:
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

    items: list[dict] = []
    if args.table:
        table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
        if args.no_wait:
            items = scan_since(table, since_iso)
        else:
            counter = (lambda: dlq_depth(sqs, args.dlq_url)) if (sqs and args.dlq_url) else None
            items = wait_until_stable(table, since_iso, args.stable_window, args.max_wait,
                                      dlq_depth=counter, expected_total=len(submitted))
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

    corrupted_ids = {s["application_id"] for s in submitted if s["category"] in CORRUPT_CATEGORIES}
    dlq_hit = len(dlq_ids & {s["application_id"] for s in submitted})
    dlq_hit_corrupted = len(dlq_ids & corrupted_ids)

    by_id = {it["application_id"]: it for it in items}
    status_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()
    queue_lat: list[float] = []   # created_at → received_at（投递+排队+冷启动）
    svc_lat: list[float] = []     # received_at → processed_at
    e2e_lat: list[float] = []     # t_submit_utc → processed_at
    per_category: dict[str, Counter] = {}
    matched = 0
    reasons_checked = 0
    reason_mismatch: list[str] = []
    missing_received = 0

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
            received = parse_iso(item.get("received_at", ""))
            processed = parse_iso(item.get("processed_at", ""))
            if received is None:
                missing_received += 1
                received = created
            elif created:
                queue_lat.append((received - created).total_seconds())
            if received and processed:
                svc_lat.append((processed - received).total_seconds())
            started = parse_iso(sub.get("t_submit_utc", ""))
            if started and processed:
                e2e_lat.append((processed - started).total_seconds())
        per_category[cat][actual] += 1

        exp = expected.get(sub["case_id"], {})
        exp_status = exp.get("expected_status")
        if exp_status and exp_status != "DLQ" and actual == exp_status:
            matched += 1

        exp_reason = (exp.get("expected_reason") or "").strip()
        if exp_reason and exp_reason != "-" and item is not None and actual != "DLQ":
            reasons_checked += 1
            if item.get("reason") != exp_reason:
                reason_mismatch.append(
                    f"{sub['case_id']}: reason={item.get('reason')!r} != {exp_reason!r}")

    if missing_received:
        print(f"[warn] {missing_received} 条记录没有 received_at，service 口径退回 created_at（含排队）；"
              f"请 D 按 interface v1.3 补该字段")
    if e2e_lat:
        neg = sum(1 for v in e2e_lat if v < 0)
        if neg / len(e2e_lat) > 0.05:
            print(f"[warn] {neg}/{len(e2e_lat)} 条端到端延迟为负，客户端时钟可能偏快；"
                  f"用 NTP 校时后重跑，或只引用 service latency")

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
        "match_rate": f"{matched}/{comparable}" if comparable else "n/a",
        "reason_match": f"{reasons_checked - len(reason_mismatch)}/{reasons_checked}"
        if reasons_checked else "n/a",
        "queue_p50_s": round(percentile(queue_lat, 0.50, "ingress p50"), 2) if queue_lat else "n/a",
        "queue_p95_s": round(percentile(queue_lat, 0.95, "ingress p95"), 2) if queue_lat else "n/a",
        "p50_s": round(percentile(svc_lat, 0.50, "service p50"), 2),
        "p90_s": round(percentile(svc_lat, 0.90, "service p90"), 2),
        "p95_s": round(percentile(svc_lat, 0.95, "service p95"), 2),
        "p99_s": round(percentile(svc_lat, 0.99, "service p99"), 2),
        "e2e_p50_s": round(percentile(e2e_lat, 0.50, "end-to-end p50"), 2),
        "e2e_p95_s": round(percentile(e2e_lat, 0.95, "end-to-end p95"), 2),
        "e2e_p99_s": round(percentile(e2e_lat, 0.99, "end-to-end p99"), 2),
    }

    print("\n=== 汇总 ===")
    for k in METRIC_COLUMNS:
        print(f"  {k:14s} {summary[k]}")
    print("\n=== 分类实际分布 ===")
    for cat, counter in sorted(per_category.items()):
        print(f"  {cat:16s} {dict(counter)}")
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
            f"Ingress p50 / p95 (s) & {summary['queue_p50_s']} / {summary['queue_p95_s']} \\\\",
            f"Service p50 / p90 / p95 / p99 (s) & {summary['p50_s']} / {summary['p90_s']} / "
            f"{summary['p95_s']} / {summary['p99_s']} \\\\",
            f"End-to-end p50 / p95 / p99 (s) & {summary['e2e_p50_s']} / {summary['e2e_p95_s']} / "
            f"{summary['e2e_p99_s']} \\\\",
            "\\bottomrule",
            "\\end{tabular}",
        ]
        Path(args.latex).parent.mkdir(parents=True, exist_ok=True)
        Path(args.latex).write_text("\n".join(latex) + "\n", encoding="utf-8")
        print(f"已写入 {args.latex}")

    if reason_mismatch:
        print(f"\n[FAIL] {len(reason_mismatch)} 条 reason 与 manifest 不符（前 10 条）：")
        for m in reason_mismatch[:10]:
            print("  -", m)
        sys.exit(4)

    if summary["pending"] > 0:
        msg = (f"仍有 {summary['pending']} 个申请未出结果（既不在表里也不在 DLQ），"
               f"可能还在重试或真的丢了")
        if args.allow_pending:
            print(f"[warn] {msg}（--allow-pending，不报错）")
        else:
            print(f"[warn] {msg}")
            sys.exit(3)


if __name__ == "__main__":
    main()
