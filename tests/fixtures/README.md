# `tests/fixtures/`

**Owner:** E · Li Hengchen ｜ 交付对象：B（Li Donghan）、C（Hu Zhongyuan）、D（Su Changwei）
**Contract:** `docs/interface.md` §9 —— 列名与 `category` 取值以该节为准，本文只做解释。
首批 5 组 normal：**2026-11-08** ｜ 全量：**2026-11-10**

## 1. 目录

```
tests/fixtures/
├── manifest.csv     ← 用例清单，进仓库（唯一事实来源）
├── SHA256SUMS       ← 全组校验清单，进仓库
├── id-card/         ← 合成证件（不提交，本地生成）
├── selfie/          ← 自拍（不提交，本地生成）
└── broken/          ← 0 字节 / 文本改名 / 截断（不提交）
```

图片一律不进仓库（公开仓库 + 组员本人照片 = 隐私事故），走共享盘 + `SHA256SUMS`。

## 2. 列（`docs/interface.md` §9，v1.3 提案）

`case_id, id_card_file, selfie_file, category, expected_status, expected_reason`

`expected_reason` 用于压测后逐条比对 DynamoDB 的 `reason`；DLQ 用例填 `-`。

## 3. 类别与预期（8 类，共 27 例）

| `category` | 数量 | 预期 `review_status` | 构成 |
|---|---|---|---|
| `normal` | 10 | PASS | 本人照片 + 合成证件，相似度 ≥ 90 |
| `different_person` | 3 | NEEDS_HUMAN_REVIEW | 证件是甲、自拍是乙（**必须两个真人**） |
| `blurry` | 2 | NEEDS_HUMAN_REVIEW | 自拍重度模糊，可能 `face_error`，也可能 `similarity_below_80`（两种都算对，manifest 写 `face_error\|similarity_below_80`） |
| `no_face` | 2 | NEEDS_HUMAN_REVIEW | 自拍里没有人脸 |
| `expired` | 2 | FAIL | 有效期区间右端改到过去 → `id_expired` |
| `missing_field` | 2 | FAIL | 遮住"签发机关" → OCR 抽不到 → `ocr_failed` |
| `zero_byte` | 2 | 进 DLQ | 自拍 0 字节（证件正常，保证消息能产生） |
| `wrong_format` | 4 | 进 DLQ | 文本改名 ×2、截断 600 B ×1、**截断 2000 B ×1** |

**为什么 `blurry` / `no_face` 不进 DLQ**：这两类能通过 starter 的 PIL 预检，会正常进入状态机，最终由 face Lambda 抛异常，按 01 方案 §1.3 判 `NEEDS_HUMAN_REVIEW`。若把它们当坏文件，压测里「坏文件 100% 进 DLQ」的指标必然失败。

## 4. 造图规则

```bash
# 至少 2 个不同的人的照片（different_person 组需要两张不同的脸）
python tests/gen_fixtures.py --selfie-dir ~/photos --out tests/fixtures
```

1. 卡面 1012×638 px（85.6×54 mm @300 dpi），四字段清晰：姓名 / 证件号 / 有效期 / 发证机关；
2. 照片位贴**本人**照片，禁止他人证件与真实证件扫描件；
3. 全卡叠加 `SAMPLE / 仅测试` 水印，不得去除；卡底编号只印后 4 位（`****1234`），
   **任何字段都不得出现 18 位连续号码**（否则 OCR 会把它并进 `issuing_authority`，违反 §5.3）；
4. 证件号按 GB 11643 生成，末位校验位合法（B 若做真伪校验不会全判无效）；
5. **有效期印区间** `2015.05.01-2035.05.01`（真实卡面格式）；`expiry_date` 输出右端单日期。
   → 需 A 写进 `docs/interface.md`、B 确认正则；B 来不及改用 `--legacy-expiry` 临时回退。

## 5. 真拍样本（11-08 手工）

把 `normal_01..05` 打 A4、裁 85.6×54 mm，手机自然光下倾斜 10–15° 拍，覆盖原图。
之后把这几行 `case_id` 备注为 `printed`（§9 无 `capture` 列，写在 commit message 或共享盘清单里）。
Ch6 才能写"准确率不是数字图打数字图"。

## 6. 自检与分发

```bash
python tests/gen_fixtures.py --selfie-dir ~/photos --check   # 相似度 + 坏文件
cd tests/fixtures && shasum -a 256 -c SHA256SUMS             # 全组同一套图
```

> `SHA256SUMS` 覆盖**完整 27 例**后才提交进 git。当前本地只有不需要真人照片的部分
> （expired / missing_field / 坏文件），对应的校验清单是局部的、不提交，避免别人
> 按它校验时以为缺了 normal 等用例。

## 7. 评审结论（A，2026-11-09）

**已按 A 的评审意见执行，待 interface v1.3 正式发布**（`docs/review_A_on_E_proposal_v1.3.md`）。

- §9：同意加 `expired`、`missing_field` 两类与 `expected_reason` 列 → 现为 27 例 / 8 类 / 6 列；
- `blurry` 的预期结果有两种：模糊自拍可能仍检出人脸、只是相似度不足（`similarity_below_80`），
  也可能检不到脸（`face_error`），两者都是 `NEEDS_HUMAN_REVIEW`，故写
  `face_error|similarity_below_80`，收集脚本按 `|` 拆分、任一命中即算对；
- §5.2 预检改为**完整解码**（`Image.open(...).load()` 不报错），**不采用** EOI/IEND 尾部判断——
  手机会在 JPEG 结尾后附加数据，看尾部会误杀正常照片。

**已知缺口**：截断 2000 B（`wrong_format_04`）在旧口径（只看 `verify()`）下会漏过预检，
D 把 `verify()` 改成 `load()` 后即可拦下；`python tests/check_precheck.py` 可对比两种口径。
