#!/usr/bin/env python3
"""
预检口径自检 —— 不需要 AWS，本地判断"坏文件是否真的会被 starter 拦下"（E / Li Hengchen）

口径来源：A 对 v1.3 提案的评审（docs/review_A_on_E_proposal_v1.3.md）
  §5.2 第 4 条改为「完整解码」：Image.open(...).load() 不报错才算通过，
  **不用** EOI/IEND 尾部判断——手机会在 JPEG 的 FF D9 之后附加数据（动态照片、厂商元数据），
  看结尾会把正常照片误判成损坏。

本脚本对每个坏文件跑两种判定：
  · current  —— §5.2 旧文字：Image.open().verify()
  · contract —— v1.3 采用：Image.open().load()（完整解码）
另带一个内置自检：完整 JPEG + 尾部附加数据必须判为「通过」，截断一半必须「拦下」。

用法：
  python tests/check_precheck.py
  python tests/check_precheck.py --fixtures-root /tmp/fx

退出码：0 = 所有坏文件在 contract 口径下都会被拦下；1 = 有漏网（需要 D 改预检）。
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

from PIL import Image, ImageFile

# 明确关闭"容忍截断"的模式，否则 load() 在截断图上也可能不报错
ImageFile.LOAD_TRUNCATED_IMAGES = False

BAD_CATEGORIES = {"zero_byte", "wrong_format"}


def verify_ok(data: bytes) -> bool:
    """旧口径：Image.open + verify（只看文件头，不看像素能否解出来）。"""
    try:
        Image.open(io.BytesIO(data)).verify()
        return True
    except Exception:  # noqa: BLE001
        return False


def decode_ok(data: bytes) -> bool:
    """v1.3 口径：完整解码——open 之后必须能 load() 出全部像素。"""
    if not data:
        return False
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return True
    except Exception:  # noqa: BLE001
        return False


def contract_rejects(data: bytes) -> bool:
    return not decode_ok(data)


def builtin_selftest() -> bool:
    """构造样本，验证口径本身没有写反。"""
    img = Image.new("RGB", (400, 300), (200, 210, 220))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    full = buf.getvalue()

    with_tail = full + b"TRAILER" * 200          # 模拟 FF D9 之后附加厂商数据
    half = full[: len(full) // 2]

    ok = True
    checks = [
        ("完整 JPEG", decode_ok(full), True),
        ("完整 JPEG + 尾部附加数据", decode_ok(with_tail), True),
        ("截断一半", decode_ok(half), False),
    ]
    for name, got, want in checks:
        mark = "✓" if got == want else "✗"
        print(f"  自检 {mark} {name}: 判为{'通过' if got else '拦下'}")
        ok = ok and got == want
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="预检口径自检（E）")
    ap.add_argument("--manifest", default="tests/fixtures/manifest.csv")
    ap.add_argument("--fixtures-root", default=".")
    args = ap.parse_args()

    print("== 口径自检（不需要 AWS）==")
    if not builtin_selftest():
        print("[FAIL] 口径自检失败：完整解码判定写错了，先修脚本本身")
        sys.exit(1)
    print()

    rows = list(csv.DictReader(Path(args.manifest).open(encoding="utf-8")))
    root = Path(args.fixtures_root)

    bad = [r for r in rows if r["category"] in BAD_CATEGORIES]
    normal = [r for r in rows if r["category"] == "normal"]

    if not bad:
        print("manifest 里没有坏文件用例")
        return

    print(f"{'case_id':22s} {'bytes':>7s}  {'old(verify)':13s} {'new(full decode)':16s}")
    print("-" * 66)
    leaks: list[str] = []
    for r in bad:
        path = root / r["selfie_file"]
        if not path.exists():
            print(f"{r['case_id']:22s} {'--':>7s}  文件缺失：{r['selfie_file']}")
            leaks.append(r["case_id"])
            continue
        data = path.read_bytes()
        old = "通过(漏)" if verify_ok(data) else "拦下"
        new = "漏网" if not contract_rejects(data) else "拦下"
        print(f"{r['case_id']:22s} {len(data):7d}  {old:13s} {new:16s}")
        if new == "漏网":
            leaks.append(r["case_id"])

    broken_normal = []
    for r in normal:
        path = root / r["id_card_file"]
        if path.exists() and not decode_ok(path.read_bytes()):
            broken_normal.append(r["case_id"])

    print()
    if broken_normal:
        print(f"[warn] 正常件的证件图无法完整解码：{broken_normal}")

    if leaks:
        print(f"[FAIL] {len(leaks)} 个坏文件会漏过预检（完整解码口径）：{leaks}")
        print("       请 D 把 starter 里的 image.verify() 改成 image.load()（interface v1.3 §5.2）。")
        sys.exit(1)

    print(f"[ok] {len(bad)} 个坏文件在「完整解码」口径下全部被拦下。")


if __name__ == "__main__":
    main()
