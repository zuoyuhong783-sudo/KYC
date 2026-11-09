# 接口变更申请：v1.2 → v1.3（E）

| 项目 | 内容 |
|---|---|
| 申请人 | E（Li Hengchen） |
| 日期 | 2026-11-09 |
| 目标版本 | **v1.2 → v1.3** |
| 状态 | **待 A 批准（11-11 M1 会上定）** |
| 影响范围 | §5.1、§5.2、§5.3、§9；D 的 starter 与状态机、B 的 OCR 抽取、E 的素材与收集脚本 |
| 批准后我要做的 | 当天补 4 行 manifest、打开 `--expired/--missing-field`、更新 Ch6 表格 |

一次提 4 条，都是"没有它就有分支测不到 / 有个数算错"的，不是风格问题。

---

## 1. §9 测试素材：加两类 + 一列

### 现状

6 类：`normal`、`different_person`、`zero_byte`、`wrong_format`、`blurry`、`no_face`；
5 列：`case_id, id_card_file, selfie_file, category, expected_status`。

覆盖 `PASS`、`NEEDS_HUMAN_REVIEW`、`DLQ` 三种结论，**`FAIL` 零用例**。
而 §5.5 的 Choice 有两条 `FAIL` 分支（`id_expired`、`ocr_failed`），现在没有任何真实输入验证过。

另外：`blurry` 和 `different_person` 都写 `NEEDS_HUMAN_REVIEW`，只有 `expected_status` 时，
无法证明命中的是"相似度 < 80"还是"比脸异常"。

### 提案

```diff
- | `category` 取值 | `normal`、`different_person`、`zero_byte`、`wrong_format`、`blurry`、`no_face` |
+ | `category` 取值 | `normal`、`different_person`、`zero_byte`、`wrong_format`、`blurry`、`no_face`、`expired`、`missing_field` |
+ | 清单列 | `case_id, id_card_file, selfie_file, category, expected_status, expected_reason` |
```

| 新增类别 | 数量 | 构造 | 预期 |
|---|---|---|---|
| `expired` | 2 | 同 normal 的图，有效期区间右端改到过去 | `FAIL` / `id_expired` |
| `missing_field` | 2 | 同 normal 的图，遮住"签发机关" | `FAIL` / `ocr_failed` |

`expected_reason` 取值同 §5.5：`auto_approved`、`similarity_below_80`、`face_error`、
`id_expired`、`ocr_failed`；DLQ 用例填 `-`。

用例总数 23 → **27**。

---

## 2. §5.1 状态机输入：加 `received_at`

### 现状

`lambda/starter/handler.py` 把 `created_at` 设成 S3 的 `eventTime`（上传完成时间）。
于是"从 created_at 到 processed_at"这一段**包含** S3 事件投递、SQS 排队和 starter 冷启动，
不能叫 service latency。报告里若写"不含投递与冷启动"，一次执行记录就能证伪。

### 提案

```diff
   "created_at": "2026-11-20T08:30:00Z",
+  "received_at": "2026-11-20T08:30:04Z",
```

starter 在收到 SQS 消息、通过预检后写入 `received_at`（UTC ISO 8601）。

三个时钟随之成立：

| 名称 | 区间 | 覆盖 |
|---|---|---|
| ingress | `created_at` → `received_at` | S3 事件投递 + 排队 + starter 冷启动 |
| service | `received_at` → `processed_at` | 流水线本身 |
| end-to-end | `t_submit_utc` → `processed_at` | 用户视角 |

**兜底**：D 到 11-13 仍未加，E 的脚本自动退回 `created_at` 口径并打印警告，报告改称
"post-upload latency"。

---

## 3. §5.2 预检：补文件完整性判定

### 现状与实测

§5.2 只要求「能被 `PIL.Image.open()` 打开」。E 在本地复刻验证（`tests/check_precheck.py`）：

| 输入 | PIL 能否打开 |
|---|---|
| 0 字节 / 文本改名 / 截断 600 B | 否 |
| **截断 2000 B** | **能** |

后果：`wrong_format_04`（截断 2000 B）会通过预检 → 进 OCR → 抽不到字段 → `FAIL/ocr_failed`，
而 manifest 期望它进 DLQ。E6 的「坏文件 6/6 进 DLQ」永远差一例。

### 提案

```diff
 4. 两张图都能被 `PIL.Image.open()` 打开
+5. 文件是完整的：JPEG 以 FF D9 结尾、PNG 以 IEND 结尾；不完整按损坏处理
```

D 只需在 starter 里加十行左右（读尾部若干字节判断）。

**证据**：`python tests/check_precheck.py` 的输出（`wrong_format_04` 一行 `current=通过(漏)`、
`contract=拦下`）。

---

## 4. §5.3 OCR：`issuing_authority` 剥离卡底编号

### 现状

卡面若把"签发机关"和"编号"排在同一行，OCR 可能把整串（含 18 位号码）写进
`issuing_authority`，违反 §5.3「禁止写入完整证件号」。

E 这边已把模型卡的卡底改成 `编号 ****1234`（只留后 4 位），但真实证件/其它模板仍可能触发。

### 提案（B）

```python
value = re.split(r"\s*(?:编\s*号|編\s*號|No\.?)\s*[:：]?\s*[0-9Xx]{4,}", value)[0].strip()
if re.search(r"\d{8,}", value):
    raise OcrExtractionError("issuing_authority contains a long digit run")
```

---

## 5. 批准后的连锁改动（E 侧，当天完成）

1. `manifest.csv` 补 4 行、加第 6 列（27 例）；
2. `gen_fixtures.py` 的 `--expired` / `--missing-field` 默认值恢复为 2；
3. `collect_results.py` 输出 `reason_match`，不符时 `exit 4`；
4. Ch6 的 `tab:fixtures` 变 8 行 / 27 例、正文改「four verdicts」；
5. `docs/e_delivery_status.md` 同步。

---

## 6. 一句话发群里

> `docs/interface_change_proposal_E.md` 已更新到 **v1.3**：§9 加 `expired`/`missing_field` 两类与
> `expected_reason` 列，§5.1 加 `received_at`，§5.2 预检补 EOI/IEND 完整性判定，§5.3 让 B 剥离卡底编号。
> 请在 11-11 M1 会上批；批完我当天补 4 行 manifest，D 的 FAIL 分支就有真实用例了。
> 截断 2000 B 的实测证据在 `tests/check_precheck.py`，现在会漏过预检。
