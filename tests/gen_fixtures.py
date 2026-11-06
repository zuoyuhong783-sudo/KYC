#!/usr/bin/env python3
"""
测试素材生成器 —— VeriCloud / E（Li Hengchen）

用途
  1. 用组员本人照片生成"合成证件"（带 SAMPLE 水印，虚构字段），
  2. 生成换人 / 模糊 / 无人脸 / 过期 / 字段缺失 用例，
  3. 生成 0 字节、文本改名、截断 JPEG 三类坏文件，
  4. 输出 SHA256SUMS（素材不进 git，靠它保证全组用的是同一套图），
  5. --check 模式：交付前用 Rekognition 自检相似度。

用法
  # 先看卡面长什么样（不需要任何照片）
  python tests/gen_fixtures.py --demo --out /tmp/fx-demo

  # 正式生成（selfie-dir 里放 person_01.jpg ... 至少 2 人）
  python tests/gen_fixtures.py --selfie-dir ~/photos --out tests/fixtures

  # 兼容 B 的旧正则（单日期 YYYY-MM-DD），仅临时用
  python tests/gen_fixtures.py --selfie-dir ~/photos --out tests/fixtures --legacy-expiry

  # 交付前自检（需要 AWS 凭证 + Rekognition 权限）
  python tests/gen_fixtures.py --selfie-dir ~/photos --check

接口约定（要同步给 A 和 B，见 docs/interface.md）
  · 卡面"有效期限"印**区间**：`2012.03.05-2035.11.20`，与真实证件一致；
  · vericloud-ocr 的 `expiry_date` 仍输出**单个失效日** `YYYY-MM-DD`（取区间右端）。

合规
  · 只用本人照片，禁止他人证件、禁止真实证件扫描件；
  · 证件号按 GB 11643 生成（虚构，但校验位合法，便于 B 做真伪校验）；
  · 全卡叠加 SAMPLE 水印，不得去除；
  · 生成物已被 .gitignore 排除，不进公开仓库。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- 常量
CARD_W, CARD_H = 1012, 638          # 85.6 × 54 mm @ 300 dpi
PHOTO_BOX = (56, 150, 356, 530)     # 证件照区域
FIELD_X = 396
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

SURNAMES = ["张", "李", "王", "赵", "陈", "刘", "杨", "黄"]
GIVEN = ["测试", "样例", "演示", "验证", "虚拟"]
AUTHORITIES = ["北京市公安局", "上海市公安局", "广州市公安局", "深圳市公安局"]

# GB 11643-1999：mod 11-2 校验位
ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
ID_CHECK = "10X98765432"


# ---------------------------------------------------------------- 工具
def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_id_number(rng: random.Random, area: str = "110101") -> str:
    """按 GB 11643 生成 18 位号码，末位校验位合法（否则 B 一验就判无效）。"""
    birth = f"{rng.randint(1980, 2002)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    body = f"{area}{birth}{rng.randint(1, 999):03d}"
    total = sum(int(c) * w for c, w in zip(body, ID_WEIGHTS))
    return body + ID_CHECK[total % 11]


def expiry_range(rng: random.Random, *, valid: bool) -> str:
    """真实卡面格式：签发日-失效日，点分隔，如 2015.05.01-2035.05.01。"""
    sy = rng.randint(2012, 2018)
    ey = (2032 + rng.randint(0, 7)) if valid else (2019 + rng.randint(0, 2))
    start = f"{sy}.{rng.randint(1, 12):02d}.{rng.randint(1, 28):02d}"
    end = f"{ey}.{rng.randint(1, 12):02d}.{rng.randint(1, 28):02d}"
    return f"{start}-{end}"


def center_crop(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    ratio = max(target_w / img.width, target_h / img.height)
    resized = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def add_watermark(img: Image.Image, text: str = "SAMPLE 仅测试") -> Image.Image:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = load_font(34)
    tile = Image.new("RGBA", (460, 220), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.text((16, 90), text, font=font, fill=(220, 30, 30, 42))
    tile = tile.rotate(28, expand=1, resample=Image.BICUBIC)
    for y in range(-120, img.height + 120, 230):
        for x in range(-120, img.width + 120, 470):
            layer.alpha_composite(tile, (x, y))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def gradient(width: int, height: int) -> Image.Image:
    """无人脸用例用：纯渐变，Rekognition 检测不到人脸。"""
    base = Image.new("RGB", (width, height), (120, 140, 160))
    px = base.load()
    for y in range(height):
        for x in range(0, width, 4):
            v = int(80 + 120 * (x / width) + 40 * (y / height))
            for dx in range(4):
                if x + dx < width:
                    px[x + dx, y] = (v, v // 2 + 40, 255 - v)
    return base


def demo_selfie(variant: int = 0) -> Image.Image:
    """没有照片时的占位人像（仅用于看版式，不能用于比脸测试）。
    variant 用于造出两个"不同的人"，让 demo 也能走通换人组的分支逻辑。"""
    skin = [(205, 175, 150), (170, 135, 110)][variant % 2]
    shirt = [(90, 110, 140), (60, 130, 110)][variant % 2]
    img = Image.new("RGB", (600, 800), (232, 236, 240))
    d = ImageDraw.Draw(img)
    d.ellipse((180 - 10 * variant, 120, 420 - 10 * variant, 380), fill=skin)
    d.rounded_rectangle((120, 400, 480, 800), radius=60, fill=shirt)
    return img


# ---------------------------------------------------------------- 卡面
def make_card(*, name: str, id_number: str, expiry: str, authority: str,
              photo: Image.Image, hide_authority: bool = False) -> Image.Image:
    card = Image.new("RGB", (CARD_W, CARD_H), (233, 239, 245))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((8, 8, CARD_W - 8, CARD_H - 8), radius=18, outline=(150, 170, 190), width=3)

    f_title, f_label, f_value, f_small = load_font(34), load_font(22), load_font(30), load_font(18)
    d.text((60, 36), "中华人民共和国居民身份证", font=f_title, fill=(40, 60, 90))
    d.text((60, 92), "SAMPLE DOCUMENT - FOR TESTING ONLY - NOT A REAL ID", font=f_small, fill=(190, 40, 40))

    x1, y1, x2, y2 = PHOTO_BOX
    card.paste(center_crop(photo, (x2 - x1, y2 - y1)), (x1, y1))
    d.rectangle(PHOTO_BOX, outline=(150, 170, 190), width=2)

    rows = [("姓　　名", name), ("公民身份号码", id_number), ("有效期限", expiry), ("签发机关", authority)]
    y = 160
    for label, value in rows:
        d.text((FIELD_X, y), label, font=f_label, fill=(120, 130, 145))
        d.text((FIELD_X, y + 34), value, font=load_font(30 if label != "有效期限" else 26), fill=(30, 40, 60))
        if label == "签发机关" and hide_authority:
            d.rectangle((FIELD_X - 6, y + 28, FIELD_X + 520, y + 78), fill=(233, 239, 245))
        y += 104

    d.text((60, CARD_H - 44), "编号 " + id_number, font=f_small, fill=(150, 160, 175))
    return add_watermark(card)


def degrade(img: Image.Image, rng: random.Random) -> Image.Image:
    """模拟手机拍摄：轻微旋转 + 亮度抖动 + 轻度模糊 + 重新压缩。"""
    out = img.rotate(rng.uniform(-1.8, 1.8), resample=Image.BICUBIC, expand=False, fillcolor=(240, 242, 245))
    out = Image.eval(out, lambda v: min(255, max(0, int(v * rng.uniform(0.95, 1.06)))))
    out = out.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.8)))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=rng.randint(72, 90))
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def save_jpeg(img: Image.Image, path: Path, quality: int = 88) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=quality)


# ---------------------------------------------------------------- 生成
def generate(args) -> None:
    rng = random.Random(args.seed)
    out = Path(args.out)
    id_dir, selfie_dir, broken_dir = out / "id-card", out / "selfie", out / "broken"
    for d in (id_dir, selfie_dir, broken_dir):
        d.mkdir(parents=True, exist_ok=True)

    photos: list[Image.Image] = []
    if args.selfie_dir:
        for p in sorted(Path(args.selfie_dir).glob("*")):
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic"}:
                try:
                    photos.append(Image.open(p).convert("RGB"))
                except Exception as exc:  # noqa: BLE001
                    print(f"[skip] {p.name}: {exc}")
    if not photos:
        if not args.demo:
            sys.exit("没有可用照片：请用 --selfie-dir 指定照片目录，或加 --demo 只看版式。")
        photos = [demo_selfie(0), demo_selfie(1)]
        print("[warn] demo 模式：使用占位人像，生成物只能看版式，不能用于比脸测试。")

    # 换人组必须来自两个不同的人，否则生成出来是"同人比对"，自检必然不过
    need_people = 2 if args.different_person > 0 else 1
    if len(photos) < need_people:
        sys.exit(
            f"[FAIL] 换人组需要至少 {need_people} 个不同的人的自拍，当前只有 {len(photos)} 张。\n"
            f"  方案 A：找另外 1 位组员各发 1 张（推荐，5 分钟）\n"
            f"  方案 B：明确放弃换人组，加 --different-person 0，并在状态板登记该指标缺失"
        )

    def fields(idx: int, *, expired: bool = False) -> dict:
        if args.legacy_expiry:
            expiry = "2020-01-01" if expired else f"203{rng.randint(0, 5)}-0{rng.randint(1, 9)}-{rng.randint(10, 28)}"
        else:
            expiry = expiry_range(rng, valid=not expired)
        return {
            "name": rng.choice(SURNAMES) + rng.choice(GIVEN),
            "id_number": make_id_number(rng),
            "expiry": expiry,
            "authority": rng.choice(AUTHORITIES),
        }

    if args.expired or args.missing_field:
        print("[warn] expired / missing_field 不在 interface §9 的 6 个类别内，"
              "需 A 升 v1.1 后才算正式用例；当前仅作本地探索用")

    made = 0

    # normal
    for i in range(1, args.normal + 1):
        p = photos[(i - 1) % len(photos)]
        card = make_card(photo=p, **fields(i))
        save_jpeg(card, id_dir / f"normal_{i:02d}.jpg")
        save_jpeg(p, selfie_dir / f"normal_{i:02d}.jpg")
        made += 1

    # different_person：证件照用甲，自拍用乙，必定不同人
    for i in range(1, args.different_person + 1):
        a = photos[(2 * (i - 1)) % len(photos)]
        b = photos[(2 * (i - 1) + 1) % len(photos)]
        card = make_card(photo=a, **fields(100 + i))
        save_jpeg(card, id_dir / f"different_person_{i:02d}.jpg")
        save_jpeg(b, selfie_dir / f"different_person_{i:02d}.jpg")
        made += 1

    # poor_quality：模糊 / 无人脸（注意：这两类不进 DLQ，判 NEEDS_HUMAN_REVIEW）
    for i in range(1, args.blur + 1):
        p = photos[(i - 1) % len(photos)]
        card = make_card(photo=p, **fields(200 + i))
        save_jpeg(card, id_dir / f"blurry_{i:02d}.jpg")
        save_jpeg(p.filter(ImageFilter.GaussianBlur(18)), selfie_dir / f"blurry_{i:02d}.jpg")
        made += 1
    for i in range(1, args.noface + 1):
        p = photos[(i - 1) % len(photos)]
        card = make_card(photo=p, **fields(300 + i))
        save_jpeg(card, id_dir / f"no_face_{i:02d}.jpg")
        save_jpeg(gradient(600, 800), selfie_dir / f"no_face_{i:02d}.jpg")
        made += 1

    # expired
    for i in range(1, args.expired + 1):
        p = photos[(i - 1) % len(photos)]
        card = make_card(photo=p, **fields(400 + i, expired=True))
        save_jpeg(card, id_dir / f"expired_{i:02d}.jpg")
        save_jpeg(p, selfie_dir / f"expired_{i:02d}.jpg")
        made += 1

    # missing_field：遮住签发机关
    for i in range(1, args.missing_field + 1):
        p = photos[(i - 1) % len(photos)]
        card = make_card(photo=p, hide_authority=True, **fields(500 + i))
        save_jpeg(card, id_dir / f"missing_field_{i:02d}.jpg")
        save_jpeg(p, selfie_dir / f"missing_field_{i:02d}.jpg")
        made += 1

    # corrupted：自拍是坏文件（自拍才是触发信号）
    good = Image.open(id_dir / "normal_01.jpg") if (id_dir / "normal_01.jpg").exists() else None
    for i in range(1, args.corrupt + 1):
        (broken_dir / f"zero_byte_{i:02d}.jpg").write_bytes(b"")
        (broken_dir / f"wrong_format_{i:02d}.jpg").write_text("This is not a JPEG image.\n", encoding="utf-8")
        if good is not None:
            buf = io.BytesIO()
            good.save(buf, "JPEG", quality=90)
            (broken_dir / f"wrong_format_{args.corrupt + i:02d}.jpg").write_bytes(buf.getvalue()[:600])

    # degrade：把正常类再"拍一次"
    if args.degrade:
        for path in list(id_dir.glob("normal_*.jpg")) + list(selfie_dir.glob("normal_*.jpg")):
            save_jpeg(degrade(Image.open(path), rng), path)

    # 校验清单：素材不进 git，靠它保证三台机器上跑的是同一套图
    lines = []
    for p in sorted(list(id_dir.glob("*.jpg")) + list(selfie_dir.glob("*.jpg"))
                    + list(broken_dir.glob("*.jpg"))):
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}")
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[ok] 生成 {made} 组配对素材 + 坏文件若干 → {out}")
    print(f"     id-card/: {len(list(id_dir.glob('*.jpg')))} 张, selfie/: {len(list(selfie_dir.glob('*.jpg')))} 张, "
          f"broken/: {len(list(broken_dir.glob('*.jpg')))} 个")
    print(f"[ok] 已写 {out / 'SHA256SUMS'}（{len(lines)} 个文件）")


# ---------------------------------------------------------------- 自检
def check(args) -> int:
    out = Path(args.out)
    problems: list[str] = []

    # 1) 坏文件必须打不开
    for p in sorted((out / "broken").glob("*.jpg")):
        try:
            Image.open(p).verify()
            problems.append(f"{p.name}: 竟然能被 PIL 打开，无法触发预检失败")
        except Exception:  # noqa: BLE001
            pass

    # 2) 所有正常图必须可打开
    for p in sorted((out / "id-card").glob("*.jpg")) + sorted((out / "selfie").glob("*.jpg")):
        try:
            Image.open(p).verify()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{p.name}: 打不开（{exc}）")

    # 3) Rekognition 相似度自检（需要凭证）
    try:
        import boto3
    except ImportError:
        print("[warn] 未安装 boto3，跳过 Rekognition 自检（pip install -r tests/requirements.txt）")
    else:
        client = boto3.client("rekognition", region_name=args.region)

        def similarity(idp: Path, sp: Path) -> float:
            resp = client.compare_faces(
                SourceImage={"Bytes": sp.read_bytes()},
                TargetImage={"Bytes": idp.read_bytes()},
                SimilarityThreshold=0,
            )
            matches = resp.get("FaceMatches", [])
            return max((m["Similarity"] for m in matches), default=0.0)

        for idp in sorted((out / "id-card").glob("normal_*.jpg")):
            sp = out / "selfie" / idp.name
            if not sp.exists():
                problems.append(f"{idp.name}: 缺少配对自拍")
                continue
            try:
                s = similarity(idp, sp)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{idp.name}: 比脸调用失败（{exc}）")
                continue
            print(f"  normal {idp.stem:12s} similarity = {s:.2f}")
            if s < 90:
                problems.append(f"{idp.name}: 相似度 {s:.1f} < 90，PASS 用例会跑不出来")

        for idp in sorted((out / "id-card").glob("different_person_*.jpg")):
            sp = out / "selfie" / idp.name
            if not sp.exists():
                continue
            try:
                s = similarity(idp, sp)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{idp.name}: 比脸调用失败（{exc}）")
                continue
            print(f"  different_person {idp.stem:10s} similarity = {s:.2f}")
            if s >= 80:
                problems.append(f"{idp.name}: 相似度 {s:.1f} >= 80，different_person 用例会误判 PASS")

    if problems:
        print("\n[FAIL] 自检未通过：")
        for p in problems:
            print("  -", p)
        return 1
    print("\n[ok] 自检通过，可以交付。")
    return 0


# ---------------------------------------------------------------- CLI
def main() -> None:
    ap = argparse.ArgumentParser(description="VeriCloud 测试素材生成器（E）")
    ap.add_argument("--out", default="tests/fixtures")
    ap.add_argument("--selfie-dir", default=None, help="本人照片目录（换人组至少需要 2 人）")
    ap.add_argument("--demo", action="store_true", help="用占位人像生成一套版式样本")
    ap.add_argument("--degrade", action="store_true", default=True, help="模拟手机拍摄（默认开）")
    ap.add_argument("--no-degrade", dest="degrade", action="store_false")
    ap.add_argument("--legacy-expiry", action="store_true",
                    help="输出单日期 YYYY-MM-DD（兼容 B 的旧正则，仅临时用）")
    ap.add_argument("--normal", type=int, default=10)
    ap.add_argument("--different-person", dest="different_person", type=int, default=3)
    ap.add_argument("--blur", type=int, default=2)
    ap.add_argument("--noface", type=int, default=2)
    ap.add_argument("--expired", type=int, default=0,
                    help="非 §9 类别，需 interface v1.1 批准后才用")
    ap.add_argument("--missing-field", dest="missing_field", type=int, default=0,
                    help="非 §9 类别，需 interface v1.1 批准后才用")
    ap.add_argument("--corrupt", type=int, default=2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--check", action="store_true", help="只做交付前自检")
    ap.add_argument("--region", default="us-east-1")
    args = ap.parse_args()

    if args.check:
        sys.exit(check(args))
    if args.demo:
        args.normal = args.different_person = args.blur = args.noface = 1
        args.expired = args.missing_field = 0
        args.degrade = False
    generate(args)


if __name__ == "__main__":
    main()
