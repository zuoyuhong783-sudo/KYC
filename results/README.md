# `results/`

**Owner:** E · Li Hengchen（压测数据）, F · Yang Xueli（成本数据）
**Tasks**（01 方案 §4）：E6、F5、F6、F7

Raw result data used in the report. Every number in the report must be traceable to a file here.

## 1. 文件命名

> A 的骨架里写的是 `load_test_round1.csv`；实际脚本把一轮拆成"提交记录 + 汇总"两个文件，
> 两轮合计 4 个，字段是骨架版本的超集（见下）。

| 文件 | 产出者 | 内容 |
|---|---|---|
| `load_test_r1_submitted.csv` | E | 第 1 轮每个申请的提交记录（含客户端时间戳） |
| `load_test_r1_summary.csv` | E | 第 1 轮汇总指标（含双口径分位数、DLQ 命中） |
| `load_test_r2_submitted.csv` / `_summary.csv` | E | 第 2 轮，同构 |
| `load_test_burst_submitted.csv` / `_summary.csv` | E | burst 档探索实验（不占正式两轮名额） |
| `tco_estimate.csv` + Pricing Calculator 导出链接 | F | 两套方案的成本估算 |
| `cost_actual.csv` | F | 实测成本（E 的调用量 × 单价） |

## 2. `*_submitted.csv` 的列

| 列 | 含义 |
|---|---|
| `application_id` | UUID v4，与 S3 key、DynamoDB 主键一致 |
| `category` | 取自 `tests/fixtures/manifest.csv`（`normal`/`different_person`/`blurry`/`no_face`/`zero_byte`/`wrong_format`） |
| `case_id` | 对应 manifest 的用例编号 |
| `t_submit_utc` | **客户端**上传完成时间（端到端延迟的起点） |
| `t_done_utc` | 客户端记录写入时间 |
| `upload_ms` | 两次 PUT 的耗时 |
| `id_card_put` / `selfie_put` | HTTP 状态码（200 才算成功） |
| `id_card_key` / `selfie_key` | S3 对象键 |
| `error` | 失败原因（空表示成功） |

## 3. `*_summary.csv` 的指标

| 指标 | 口径 |
|---|---|
| `submitted` | 本轮实际提交数（报告的分母，**不要用计划值 100**） |
| `in_table` | DynamoDB 里命中本轮时间窗的记录数 |
| `pass` / `review` / `fail` | 三种 `review_status` 的计数 |
| `dlq` | 本轮 application_id 在 DLQ 中命中的条数（按消息体比对，不是队列累计值） |
| `dlq_corrupted` | `命中数/本轮坏文件数`，例如 `20/20` |
| `pending` | 既不在表里也不在 DLQ 的申请数（>0 说明有问题） |
| `reason_match` | `reason` 与 manifest 的 `expected_reason` 一致数 / 可比对数 |
| `queue_p50_s` / `queue_p95_s` | **ingress latency**：`created_at`（S3 eventTime）→ `received_at` |
| `p50_s` … `p99_s` | **service latency**：`received_at` → `processed_at`（无 `received_at` 时退回 `created_at`，会打印警告） |
| `e2e_p50_s` … `e2e_p99_s` | **end-to-end**：`t_submit_utc` → `processed_at` |
| `match_rate` | 预期结论与实际一致的用例数 / 可比对用例数 |

口径定义同步写在 `tests/README.md` §5 与 Ch6 §6.1，三处必须一字不差。

**时钟前提**：`e2e_*` 用客户端的 `t_submit_utc`，要求压测机已完成 NTP 同步；
若超过 5% 的值为负，`collect_results.py` 会告警，此时只引用 service 口径。

## 4. 使用规则

1. **F 取调用量**：`submitted` × 2 = S3 PUT 次数；`in_table` = DynamoDB 写入次数；`submitted` = Step Functions 执行次数。不要自己估。
2. **A 抽查**：数字关时随机挑报告里 3 个数字，回到这里的 CSV 找到同一行。
3. **不要手改 CSV**。口径错了就改 `collect_results.py` 重跑，保留原始文件。
4. 两轮之间必须清 DLQ（`python tests/collect_results.py --purge-only --dlq-url <URL>`），否则第 2 轮的 `dlq` 会含第 1 轮残留。

## 5. 当前状态

目录里目前只有 `.gitkeep` 与本文件。数据要等 M2 端到端跑通（11-20）后由 E 在 11-21 压测产出。
