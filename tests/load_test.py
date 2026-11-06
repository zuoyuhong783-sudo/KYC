#!/usr/bin/env python3
"""
并发压测脚本 —— 60 秒内提交 100 个 KYC 申请（E / Li Hengchen）

流程（每个申请）：
  1. 生成本地 application_id (UUID v4)
  2. 生成两个预签名 PUT URL（5 分钟有效；可用 --presign-module 接 C 的实现）
  3. PUT 证件照 → PUT 自拍（自拍 = 触发信号，顺序不能反）
  4. 记录提交时间 / HTTP 状态，落盘 results/load_test_rN_submitted.csv

用法：
  # 默认：匀速度，验证稳态吞吐
  python tests/load_test.py --bucket vericloud-raw-xxxx --count 100 --duration 60 \\
      --out results/load_test_r1_submitted.csv

  # burst 档：几乎同时打满，观察冷启动与队列堆积（探索实验，不占 E6 的两轮名额）
  python tests/load_test.py --bucket vericloud-raw-xxxx --count 100 --duration 10 \\
      --profile burst --out results/load_test_burst_submitted.csv

  # 接 C 的 presign（需暴露 presign_put_url(bucket, key) -> str）
  python tests/load_test.py --bucket b --presign-module security.presign

  # 只验证参数与素材（素材缺失时 exit 1）
  python tests/load_test.py --bucket b --dry-run

前置：AWS 凭证（Academy Learner Lab → AWS Details → 复制到 ~/.aws/credentials）
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

MANIFEST = Path("tests/fixtures/manifest.csv")
URL_TTL_SECONDS = 300  # 必须与 01 方案 §12 一致：预签名 5 分钟


@dataclass
class Submission:
    application_id: str
    category: str
    case_id: str
    t_submit_utc: str
    t_done_utc: str
    upload_ms: int
    id_card_put: int
    selfie_put: int
    id_card_key: str
    selfie_key: str
    error: str


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_pools(repo_root: Path) -> tuple[dict[str, list[dict]], list[str]]:
    path = repo_root / MANIFEST
    if not path.exists():
        sys.exit(f"找不到 {path}，请在仓库根目录运行")
    pools: dict[str, list[dict]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pools.setdefault(row["category"], []).append(row)

    missing = []
    for rows in pools.values():
        for r in rows:
            for key in ("id_card_file", "selfie_file"):
                if r[key] and not (repo_root / r[key]).exists():
                    missing.append(r[key])
    if missing:
        print(f"[warn] 有 {len(missing)} 个素材文件缺失（先跑 tests/gen_fixtures.py）")
        for m in sorted(set(missing))[:5]:
            print("   ", m)
    return pools, sorted(set(missing))


def main() -> None:
    ap = argparse.ArgumentParser(description="VeriCloud 并发压测（E）")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--duration", type=float, default=60.0, help="提交窗口秒数")
    ap.add_argument("--invalid-ratio", type=float, default=0.2, help="坏文件占比（按概率混入）")
    ap.add_argument("--valid-category", default="normal")
    ap.add_argument("--invalid-categories", default="zero_byte,wrong_format",
                    help="坏文件类别，逗号分隔（interface §9：zero_byte / wrong_format）")
    ap.add_argument("--profile", choices=["uniform", "burst"], default="uniform")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--presign-module", default=None,
                    help="C 的 presign 模块，如 security.presign；不填则用内置实现")
    ap.add_argument("--presign-func", default="presign_put_url",
                    help="模块内的函数名，签名需为 (bucket, key) -> str")
    ap.add_argument("--sse", action="store_true", help="上传时带 SSE-S3 头（桶策略要求时用）")
    ap.add_argument("--out", default="results/load_test_r1_submitted.csv")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--dry-run", action="store_true", help="只做参数/素材校验")
    ap.add_argument("--allow-missing-fixtures", action="store_true",
                    help="只校验参数，不校验素材是否存在")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    root = Path(args.repo_root).resolve()
    pools, missing = load_pools(root)
    if missing and not args.allow_missing_fixtures:
        sys.exit(f"[FAIL] 缺 {len(missing)} 个素材文件，dry-run 不通过。"
                 f"先生成素材，或确认只查参数时加 --allow-missing-fixtures")

    if args.valid_category not in pools:
        sys.exit(f"manifest 里没有类别 {args.valid_category}")
    valid_pool = pools[args.valid_category]
    invalid_cats = [c.strip() for c in args.invalid_categories.split(",") if c.strip()]
    invalid_pool = [row for c in invalid_cats for row in pools.get(c, [])]
    if not invalid_pool:
        print(f"[warn] manifest 里没有 {invalid_cats} 类用例，本轮只跑正常流")

    interval = 0.0 if args.profile == "burst" else args.duration / max(1, args.count)
    if args.profile == "burst":
        args.workers = max(args.workers, min(args.count, 100))

    print(f"计划提交 {args.count} 个申请：约 {round(args.count * (1 - args.invalid_ratio))} 个 "
          f"{args.valid_category} + 约 {round(args.count * args.invalid_ratio)} 个 {','.join(invalid_cats)}")
    print(f"窗口 {args.duration}s，并发上限 {args.workers}，profile={args.profile}，桶 {args.bucket}")
    if args.profile == "uniform":
        print("[note] uniform 档是匀速铺开，峰值并发通常 1–3；要测冷启动并发请用 --profile burst")

    if args.dry_run:
        print("[dry-run] 不访问 AWS，退出。")
        return

    import boto3
    from botocore.config import Config
    import requests

    s3 = boto3.client("s3", region_name=args.region, config=Config(signature_version="s3v4"))

    if args.presign_module:
        import importlib
        mod = importlib.import_module(args.presign_module)
        fn = getattr(mod, args.presign_func, None)
        if fn is None:
            sys.exit(f"[FAIL] {args.presign_module} 里没有 {args.presign_func}(bucket, key)")
        print(f"[info] 使用 {args.presign_module}.{args.presign_func} 生成预签名 URL")

        def presign(key: str) -> str:
            return fn(args.bucket, key)
    else:
        print("[warn] 内置 presign：C 的 security/presign.py 交付后请改用 --presign-module")

        def presign(key: str) -> str:
            return s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": args.bucket, "Key": key},
                ExpiresIn=URL_TTL_SECONDS,
            )

    rows: list[Submission] = []

    def one(category: str, case: dict, app_id: str) -> Submission:
        id_key = f"raw/id-card/{app_id}.jpg"
        selfie_key = f"raw/selfie/{app_id}.jpg"
        t0 = iso_now()
        started = time.monotonic()
        code_id = code_selfie = 0
        err = ""
        headers = {"Content-Type": "image/jpeg"}
        if args.sse:
            headers["x-amz-server-side-encryption"] = "AES256"
        try:
            body_id = (root / case["id_card_file"]).read_bytes() if case.get("id_card_file") else b""
            body_selfie = (root / case["selfie_file"]).read_bytes() if case.get("selfie_file") else b""
            code_id = requests.put(presign(id_key), data=body_id, headers=headers, timeout=15).status_code
            # 自拍必须后传：它是触发 S3 事件的那一张
            code_selfie = requests.put(presign(selfie_key), data=body_selfie, headers=headers, timeout=15).status_code
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        return Submission(
            application_id=app_id,
            category=category,
            case_id=case["case_id"],
            t_submit_utc=t0,
            t_done_utc=iso_now(),
            upload_ms=int((time.monotonic() - started) * 1000),
            id_card_put=code_id,
            selfie_put=code_selfie,
            id_card_key=id_key,
            selfie_key=selfie_key,
            error=err,
        )

    start = time.monotonic()
    futures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i in range(args.count):
            # uniform：第 i 个在 start + i*interval 之后才提交；burst：不等待
            delay = (start + i * interval) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            # 坏文件按概率混入整个窗口，而不是集中在前若干秒
            if invalid_pool and rng.random() < args.invalid_ratio:
                case = rng.choice(invalid_pool)
            else:
                case = rng.choice(valid_pool)
            cat = case["category"]
            futures.append(pool.submit(one, cat, case, str(uuid.uuid4())))

        for done, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if done % 10 == 0 or done == len(futures):
                print(f"  已提交 {done}/{len(futures)}")

    elapsed = time.monotonic() - start
    ok = sum(1 for r in rows if r.id_card_put == 200 and r.selfie_put == 200)
    n_normal = sum(1 for r in rows if r.category not in invalid_cats)
    n_bad = len(rows) - n_normal
    print(f"\n完成：{len(rows)} 个（实际 normal/valid={n_normal}，corrupted={n_bad}），"
          f"成功上传 {ok} 个，耗时 {elapsed:.1f}s")
    print("[note] 报告里的分母用 submitted.csv 的实际计数，不要用计划值")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for r in sorted(rows, key=lambda x: x.t_submit_utc):
            writer.writerow(asdict(r))
    print(f"已写入 {out}（压测结束后等 10 分钟再跑 collect_results.py）")

    failed = [r for r in rows if r.id_card_put != 200 or r.selfie_put != 200]
    if failed:
        print(f"[warn] {len(failed)} 个上传失败，首个错误：{failed[0].error or 'HTTP ' + str(failed[0].selfie_put)}")
        sys.exit(2)


if __name__ == "__main__":
    main()
