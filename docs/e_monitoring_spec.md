# E4/E5：CloudWatch 仪表盘与告警配置规格

> 负责人：Li Hengchen（E）｜交付对象：A（截图入报告）
> 用途：11-18 建仪表盘、11-20 建告警时照此操作，避免临场想指标
> 契约：区域 `us-east-1`；资源名见 `docs/interface.md` §3；指标口径见 `tests/README.md` §5

---

## 1. 仪表盘 `vericloud-dashboard`

一个仪表盘、三行布局，答辩投屏时能一屏讲完。所有 widget 用「Line」或「Stacked area」，周期 60 s。

### 第 1 行：弹性（证明会扩、会收）

| Widget | 指标 | 维度 | 统计量 |
|---|---|---|---|
| Invocations | `AWS/Lambda Invocations` | 四个函数：`vericloud-starter` / `-ocr` / `-face` / `-notify` | Sum |
| Concurrency | `AWS/Lambda ConcurrentExecutions` | 同上（四个一起画） | Maximum |

### 第 2 行：稳定（证明慢在哪、错在哪）

| Widget | 指标 | 维度 | 统计量 |
|---|---|---|---|
| Duration | `AWS/Lambda Duration` | `vericloud-ocr`、`vericloud-face` | p90 / p99（两个 widget 或四条线） |
| Errors | `AWS/Lambda Errors` + `AWS/Lambda Throttles` | 四个函数 | Sum |
| DynamoDB | `AWS/DynamoDB ThrottledRequests` + `UserErrors` | 表 `vericloud-kyc-table` | Sum |

### 第 3 行：积压与隔离（证明不堵、不漏）

| Widget | 指标 | 维度 | 统计量 |
|---|---|---|---|
| 入口队列 | `AWS/SQS ApproximateNumberOfMessagesVisible` | `vericloud-ingest-queue` | Average / Maximum |
| 死信队列 | `AWS/SQS ApproximateNumberOfMessagesVisible` | `vericloud-ingest-dlq` | Average / Maximum |
| 状态机 | `AWS/States ExecutionsSucceeded` + `ExecutionsFailed` | `vericloud-kyc-workflow` | Sum |

**时间范围**：压测那 60 秒 ± 5 分钟。截图前把 AWS 账号 ID、邮箱打码（截图关要求）。

---

## 2. 告警 `vericloud-ops-alarm`

SNS 主题 `vericloud-ops-alarm` 由 F 建并确认订阅；E 负责建下面三条告警。

| 告警名 | 指标 | 条件 | 周期 / 评估 | 缺数据处理 |
|---|---|---|---|---|
| `vericloud-worker-errors` | `AWS/Lambda Errors`，**只覆盖 `vericloud-ocr` / `-face` / `-notify`** | Sum > 5 | 300 s / 1 个周期 | `notBreaching` |
| `vericloud-dlq-not-empty` | `AWS/SQS ApproximateNumberOfMessagesVisible`（DLQ） | Maximum > 0 | 300 s / 1 个周期 | `notBreaching` |
| `vericloud-workflow-failed` | `AWS/States ExecutionsFailed` | Sum > 0 | 300 s / 1 个周期 | `notBreaching` |

**三条告警的分工要写进报告**：预检失败是**预期业务结果**，所以 `starter` 的报错**故意不接入** error 告警（20 个坏文件 × 3 次重试 ≈ 60 次报错，接进去每轮必响）；quarantine 用 DLQ 深度表达。error 告警只覆盖"本不该失败"的三个 worker；workflow 告警捕获在 worker 之前就中止的执行。

**压测时的预期现象**：20% 坏文件 → DLQ 告警**必然触发**。这不是事故；反过来，收到的那封邮件就是 E5 最有力的证据（比静态配置截图强）。

---

## 3. 截图清单（存 `screenshots/`，命名按 01 方案 §12.5）

**落点（E-09）**：原始截图存共享盘 `screenshots/`（按 01 §12.5 命名）；**入报告的图放 `report/figures/`**（Ch6 里写 `figures/xxx`，相对 `report/main.tex` 解析）。根目录的 `figures/` 是 D 的图，不要混。

| 原始截图（screenshots/） | 入报告（report/figures/） | 内容 | 截止 |
|---|---|---|---|
| `6_dashboard_overview_E.png` | `fig_e_dashboard.png` | 三行总览，压测时间窗 | 11-18 |
| `6_dashboard_latency_E.png` | `fig_e_latency.pdf` | Duration p90/p99 曲线放大 | 11-18 |
| `6_sqs_depth_E.png` | —（并入 dashboard） | 入口队列 + DLQ 消息数 | 11-18 |
| `6_alarm_config_E.png` | —（表格代替） | 三条告警的配置页 | 11-20 |
| `6_alarm_email_E.png` | `fig_e_alarm.png` | 收到告警邮件（打码） | 11-20 |

报告里对应 `figures/fig_e_dashboard.png`、`figures/fig_e_alarm.png`（02 指南 §1 的命名）。

---

## 4. 与报告的一致性（§9.2 一致关）

| 报告里写的 | 必须与这里一致 |
|---|---|
| 告警阈值 5 次 / 5 分钟 | 上表 |
| `DLQ > 0` 即告警 | 上表 |
| 四族指标 | 第 1–3 行 widget |
| 区域 `us-east-1` | 所有资源 |

改任何一项，先改本文件，再改报告，再改控制台。
