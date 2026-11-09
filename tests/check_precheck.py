#!/usr/bin/env python3
"""
预检口径自检 —— 不需要 AWS，本地判断"坏文件是否真的会被 starter 拦下"（E / Li Hengchen）

为什么需要：
  `docs/interface.md` §5.2 目前只要求「能被 PIL.Image.open() 打开」。
  实测发现，JPEG 截断到 2000 B 时 PIL 仍能打开，于是这类文件会进入 OCR 分支，
  最终变成 FAIL/ocr_failed，而不是 manifest 期望的 DLQ。

本脚本对每个坏文件跑两种判定，并把差距打出来：
  · current   —— 按 §5.2 现行文字（PIL 能打开即通过）
  · contract  —— 按提案 v1.3（在 PIL 之上补文件完整性：JPEG 结尾 FF D9、PNG 结尾 IEND）

用法：
  python tests/check_precheck.py
  python tests/check_precheck.py --manifest tests/fixtures/manifest.csv

退出码：0 = 所有坏文件在 contract 口径下都会被拦下；1 = 有漏网（需要 D 改预检）。
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
BAD_CATEGORIES = {"zero_byte", "wrong_format"}


def pil_opens(data: bytes) -> bool:
    try:
        Image.open(io.BytesIO(data)).verify()
        return True
    except Exception:  # noqa: BLE001
        return False


def layer_ok(data: bytes) -> bool:
    """§5.2 现行口径：非空 + 能被 PIL 打开。"""
    return len(data) > 0 and pil_opens(data)


def complete_ok(data: bytes) -> bool:
    """提案口径：再多一层文件完整性判定（EOI / IEND）。"""
    if data[:3] == b"\xff\xd8\xff":
        return b"\xff\xd9" in data[-64:]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return b"IEND" in data[-16:]
    return False


def contract_rejects(data: bytes) -> bool:
    """不满足任一条即应被判为坏文件。"""
    return (not layer_ok(data)) or (not complete_ok(data))


def main() -> None:
    ap = argparse.ArgumentParser(description="预检口径自检（E）")
    ap.add_argument("--manifest", default="tests/fixtures/manifest.csv")
    ap.add_argument("--fixtures-root", default=".")
    args = ap.parse_args()

    manifest = Path(args.manifest)
    rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
    root = Path(args.fixtures_root)

    bad = [r for r in rows if r["category"] in BAD_CATEGORIES]
    normal = [r for r in rows if r["category"] == "normal"]

    if not bad:
        print("manifest 里没有坏文件用例")
        return

    print(f"{'case_id':22s} {'bytes':>7s}  {'current(PIL)':12s} {'integrity':10s} {'contract':10s}")
    print("-" * 70)
    leaks: list[str] = []
    for r in bad:
        path = root / r["selfie_file"]
        if not path.exists():
            print(f"{r['case_id']:22s} {'--':>7s}  文件缺失：{r['selfie_file']}")
            leaks.append(r["case_id"])
            continue
        data = path.read_bytes()
        cur = "通过(漏)" if layer_ok(data) else "拦下"
        integ = "完整" if complete_ok(data) else "不完整"
        con = "漏网" if not contract_rejects(data) else "拦下"
        print(f"{r['case_id']:22s} {len(data):7d}  {cur:12s} {integ:10s} {con:10s}")
        if con == "漏网":
            leaks.append(r["case_id"])

    # 正常件必须完整，否则说明素材本身坏了
    broken_normal = []
    for r in normal:
        path = root / r["id_card_file"]
        if path.exists() and not complete_ok(path.read_bytes()):
            broken_normal.append(r["case_id"])

    print()
    if broken_normal:
        print(f"[warn] 正常件的证件图不完整：{broken_normal}")

    if leaks:
        print(f"[FAIL] {len(leaks)} 个坏文件会漏过预检：{leaks}")
        print("       按 interface v1.3 §5.2 的提案，starter 需要补 EOI/IEND 完整性判定。")
        print("       证据请贴给 D（见 docs/interface_change_proposal_E.md）。")
        sys.exit(1)

    print(f"[ok] {len(bad)} 个坏文件在 contract 口径下全部被拦下。")
    # 现行口径下漏网的数量，单独提示
    cur_leaks = [r["case_id"] for r in bad
                 if (root / r["selfie_file"]).exists()
                 and layer_ok((root / r["selfie_file"]).read_bytes())]
    if cur_leaks:
        print(f"[info] 按 §5.2 现行文字（只看 PIL）会放过：{cur_leaks}")


if __name__ == "__main__":
    main()
