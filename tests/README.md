# `tests/`

**Owner:** E · Li Hengchen ｜ 交付对象：B、C、D、F、A
**Tasks**（01 方案 §4.5）：E1、E2、E3、E6
**Contract:** `docs/interface.md` v1.2 §2（上传顺序）、§3（桶 `vericloud-raw-1009-a`（v1.3.1）、5 分钟 URL）与 §9（测试素材）。不要自创字段名或类别名。

首批素材 11-08 ｜ 全量 11-10 ｜ 压测 11-21 ｜ Ch6 11-30

## 0. 一次性准备

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt

# AWS 凭证（Academy Learner Lab → AWS Details → 三条一次性凭证）
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...
export AWS_DEFAULT_REGION=us-east-1
```

凭证**只能放环境变量或 `~/.aws/credentials`**，`.gitignore` 已挡住 `.env` / `credentials` / `*.pem`。

## 1. 测试素材（11-08 / 11-10）

```bash
# 先看卡面版式（不需要照片）
python tests/gen_fixtures.py --demo --out /tmp/fx-demo

# 正式生成：selfie-dir 里至少 2 个不同的人（different_person 组需要两张不同的脸）
python tests/gen_fixtures.py --selfie-dir ~/photos --out tests/fixtures

# 兼容 B 的旧正则（单日期），仅临时用，需在群里声明
python tests/gen_fixtures.py --selfie-dir ~/photos --legacy-expiry
```

- 只有 1 张照片时脚本会**直接报错退出**（不会生成"同人比对"的假换人组）。
- 卡面「有效期限」印区间 `2012.03.05-2035.11.20`；OCR 输出的 `expiry_date` 仍是单个失效日。
- 证件号按 GB 11643 生成，末位校验位合法。
- 生成后写 `tests/fixtures/SHA256SUMS`（图片不进 git，靠它保证全组同一套图）：

```bash
cd tests/fixtures && shasum -a 256 -c SHA256SUMS     # macOS，全 OK 才算同一套
```

类别与列的定义见 `docs/interface.md` §9 和 `tests/fixtures/README.md`。

## 2. 交付前自检（必须过）

```bash
python tests/gen_fixtures.py --selfie-dir ~/photos --check
```

`normal_*` 相似度 ≥ 90、`different_person_*` < 80、坏文件打不开，任一条不过就重做。

## 3. 压测前检查（每次会话都跑）

```bash
python tests/preflight.py --bucket vericloud-raw-1009-a --table vericloud-kyc-table
```

除了"资源在不在"，还核对 §9.2 一致关的硬指标：桶私有 + SSE-S3 + 生命周期 7 天、
重试 3 次、DLQ 保留 14 天、可见性超时、Lambda python3.12/1024MB/60s、状态机 STANDARD。
M2 之前可加 `--allow-missing-functions`。

## 4. 正式压测（11-21，两轮）

```bash
# ① 每轮开跑前先清 DLQ（purge 约 60 s 生效，不能压完再清）
python tests/collect_results.py --dlq-url <dlq-url> --purge-only

# ② 第 1 轮
python tests/load_test.py --bucket vericloud-raw-1009-a \
    --presign-module security.presign \
    --count 100 --duration 60 --invalid-ratio 0.2 \
    --out results/load_test_r1_submitted.csv

# ③ 至少等 13 分钟（2×360 s 可见性超时 + 处理）；脚本会自己轮询，不用人盯
python tests/collect_results.py --table vericloud-kyc-table --dlq-url <dlq-url> \
    --submitted results/load_test_r1_submitted.csv \
    --out results/load_test_r1_summary.csv --latex tables/tab_e_loadtest.tex

# ④ 第 2 轮：r1 → r2
```

**burst 探索（不占两轮名额）**：

```bash
python tests/load_test.py --bucket <桶> --count 100 --duration 10 --profile burst \
    --out results/load_test_burst_submitted.csv
```

## 4.1 `collect_results.py` 的退出码

| 码 | 含义 | 怎么办 |
|---|---|---|
| 0 | 全部出结果，结论与 reason 都对上 | 收工 |
| 3 | 还有 pending（既不在表里也不在 DLQ） | 再等 5 分钟；仍为 3 说明有包真丢了 |
| 4 | 结论或 `reason` 与 manifest 不符 | 看打印的前 10 条，找对应 owner |
| 5 | 没有延迟样本 | 检查 D 是否写 `processed_at`、`received_at` |

预热轮（只想看链路通不通）可以加 `--allow-pending`，避免半途的 pending 让脚本报错。

## 5. 指标口径（写进 Ch6，数字关按这个核）

| 指标 | 定义 |
|---|---|
| ingress latency | `created_at` → `received_at`（S3 事件投递 + 排队 + starter 冷启动） |
| service latency | `received_at` → `processed_at`（流水线本身；无 `received_at` 时退回 `created_at` 并告警） |
| end-to-end latency | 客户端 `t_submit_utc` → `processed_at`（含 S3 事件与冷启动） |
| DLQ 命中 | 用 `application_id` 与 DLQ 消息体做集合比对，不是队列累计数 |
| 坏文件隔离率 | `dlq_corrupted` = 命中数 / 本轮坏文件提交数 |

## 6. 仪表盘与告警（11-18 / 11-20）

控制台手工配置，命名与指标见 01 方案 §4.5 E4/E5。截图存 `screenshots/`：

| 文件 | 内容 |
|---|---|
| `6_dashboard_overview_E.png` | 五组指标总览（压测时间窗） |
| `6_dashboard_latency_E.png` | Duration p90/p99 曲线 |
| `6_sqs_depth_E.png` | 入口队列 + DLQ 消息数 |
| `6_alarm_config_E.png` | 告警规则配置 |
| `6_alarm_email_E.png` | 收到告警邮件（打码） |

## 7. 脚本清单

| 文件 | 作用 | 何时能跑 |
|---|---|---|
| `gen_fixtures.py` | 合成证件 / 换人 / 模糊 / 坏文件 + 自检 + SHA256SUMS | **现在** |
| `preflight.py` | 资源 + 契约红线自检 | 资源建好后任意时刻 |
| `load_test.py` | 60 秒 100 申请，uniform / burst 两档 | M2 之后 |
| `collect_results.py` | 三口径延迟、DLQ 逐条比对、reason 比对、LaTeX 表 | 每轮压测后立即跑（自动等到齐） |
| `check_precheck.py` | 本地判断坏文件会不会被 starter 拦下（不需要 AWS） | **现在** |
| `fixtures/manifest.csv` | 用例清单，唯一事实来源 | **现在** |

## 8. 常见坑

1. **顺序**：先 PUT 证件、后 PUT 自拍——自拍才是触发 S3 事件的那一张。
2. **URL 5 分钟过期**：100 个申请要在窗口内发完，别先生成 100 对 URL 再慢慢传。
3. **DLQ 计数要等**：重试 3 次 + 可见性超时（360 s），最坏要 2 个周期≈12 分钟才进 DLQ，加处理约 12–15 分钟。收集脚本默认等 1500 s，不要以为它卡住了。
4. **告警会响**：压测里有 20% 坏文件，`DLQ > 0` 的告警按设计必然触发，这是预期行为。
5. **会话到期**：Learner Lab 约 4 小时，压测前 30 分钟重开会话，Lambda 逐个手动跑一次。
6. **不要用队列累计数当本轮结果**：两轮不清 DLQ，第 2 轮会报 40，出现 `100 = 80 + 40` 的矛盾。
