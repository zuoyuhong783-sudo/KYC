# 接口变更申请：`docs/interface.md` §9 增加 FAIL 用例类别

| 项目 | 内容 |
|---|---|
| 申请人 | E（Li Hengchen） |
| 日期 | 2026-11-06 |
| 目标版本 | v1.0 → v1.1 |
| 影响范围 | `docs/interface.md` §9、`tests/fixtures/manifest.csv`、D 的 Choice 单测 |
| 状态 | **待 A 批准**（未批准前 `manifest.csv` 保持 §9 的 6 类，不写入新类别） |

## 1. 问题

§9 目前只定义 6 个类别：`normal`、`different_person`、`zero_byte`、`wrong_format`、`blurry`、`no_face`。

它们覆盖了 `PASS`、`NEEDS_HUMAN_REVIEW` 和 `DLQ` 三种结果，但**没有覆盖 `FAIL`**。
而 01 方案 §1.3 与 §12.3 的判定表里，`FAIL` 有两条明确触发条件：

1. 证件已过期（`id_valid == false`）→ `reason = "id_expired"`
2. OCR 关键字段缺失 → `reason = "ocr_failed"`

后果：

- D 的 Choice 里第 1、2 条分支**没有任何真实用例可以验证**；
- M2 验收的"3 类用例"不含 `FAIL`，端到端测试存在盲区；
- Ch6 的结果表缺一行，答辩被问"怎么证明过期证件会被拒绝"时只能口头回答。

## 2. 提议（二选一，请 A 定）

### 方案 A（推荐）：新增两个 `category` 值

```diff
- | `category` 取值 | `normal`、`different_person`、`zero_byte`、`wrong_format`、`blurry`、`no_face` |
+ | `category` 取值 | `normal`、`different_person`、`zero_byte`、`wrong_format`、`blurry`、`no_face`、`expired`、`missing_field` |
```

| 新类别 | 数量 | 构造 | 预期 `expected_status` |
|---|---|---|---|
| `expired` | 2 | 同 `normal` 的图，有效期区间右端改到过去 | `FAIL` |
| `missing_field` | 2 | 同 `normal` 的图，遮住"签发机关"区域 | `FAIL` |

用例总数 23 → 27，其余类别不变。

### 方案 B（不改枚举）：复用 `normal` + `expected_status = FAIL`

把一个过期证件仍然算 `normal`（图片本身正常、同一个人），只把 `expected_status` 写成 `FAIL`。

- 好处：不动 §9 的类别列表；
- 代价：`normal` 类别内混入两种预期，`load_test.py` 按类别取样时会把 `FAIL` 用例混进正常流，
  `match_rate` 的分母也要按 `case_id` 而不是按类别算，容易出错。

## 3. 附带请求（可与上面一起批，也可单独）

`manifest.csv` 增一列 `expected_reason`（取值见 01 §12.3：`auto_approved`、`similarity_below_80`、
`face_error`、`id_expired`、`ocr_failed`、`precheck_failed`）。

- 作用：压测后能把"预期原因"与 DynamoDB 里的 `reason` 逐条比对，数字关更容易过；
- 兼容性：只是新增列，现有读取方（`load_test.py`）按列名取，不写死列序即可。

## 4. 批准后我要做的事（当天完成）

1. `manifest.csv` 增加 4 行（`expired_01/02`、`missing_field_01/02`）；
2. `gen_fixtures.py` 去掉 `--expired` / `--missing-field` 的"非契约"警告；
3. `docs/interface.md` 的变更记录加一行 v1.1；
4. 群里通知 D：`FAIL` 分支有真实用例可测了。

## 5. 附：当前 23 例与四类结论的覆盖情况

| 结论 | 现有覆盖 | 缺口 |
|---|---|---|
| `PASS` | `normal` ×10 | — |
| `NEEDS_HUMAN_REVIEW` | `different_person` ×3、`blurry` ×2、`no_face` ×2 | — |
| `DLQ` | `zero_byte` ×2、`wrong_format` ×4 | — |
| **`FAIL`** | **无** | `expired`、`missing_field` |
