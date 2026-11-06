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

## 2. 列（`docs/interface.md` §9）

`case_id, id_card_file, selfie_file, category, expected_status`

## 3. 类别与预期（§9 定义的 6 类，共 23 例）

| `category` | 数量 | 预期 `review_status` | 构成 |
|---|---|---|---|
| `normal` | 10 | PASS | 本人照片 + 合成证件，相似度 ≥ 90 |
| `different_person` | 3 | NEEDS_HUMAN_REVIEW | 证件是甲、自拍是乙（**必须两个真人**） |
| `blurry` | 2 | NEEDS_HUMAN_REVIEW | 自拍重度模糊，face Lambda 抛 `FaceNotDetectedError` |
| `no_face` | 2 | NEEDS_HUMAN_REVIEW | 自拍里没有人脸 |
| `zero_byte` | 2 | 进 DLQ | 自拍 0 字节（证件正常，保证消息能产生） |
| `wrong_format` | 4 | 进 DLQ | 文本改名 `.jpg` ×2、完整 JPEG 截断 600 字节 ×2 |

**为什么 `blurry` / `no_face` 不进 DLQ**：这两类能通过 starter 的 PIL 预检，会正常进入状态机，最终由 face Lambda 抛异常，按 01 方案 §1.3 判 `NEEDS_HUMAN_REVIEW`。若把它们当坏文件，压测里「坏文件 100% 进 DLQ」的指标必然失败。

## 4. 造图规则

```bash
# 至少 2 个不同的人的照片（different_person 组需要两张不同的脸）
python tests/gen_fixtures.py --selfie-dir ~/photos --out tests/fixtures
```

1. 卡面 1012×638 px（85.6×54 mm @300 dpi），四字段清晰：姓名 / 证件号 / 有效期 / 发证机关；
2. 照片位贴**本人**照片，禁止他人证件与真实证件扫描件；
3. 全卡叠加 `SAMPLE / 仅测试` 水印，不得去除；
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

## 7. 待 A 批准（interface v1.1）

§9 目前只定义 6 类，**`FAIL` 分支没有真实用例**（过期证件、OCR 字段缺失）。E 已提变更申请：
新增 `expired`、`missing_field` 两类，并在 `manifest.csv` 增 `expected_reason` 列。
批准前不写进 `manifest.csv`，避免违反"唯一事实来源"。
见 `docs/interface_change_proposal_E.md`。
