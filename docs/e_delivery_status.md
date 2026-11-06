# E（Li Hengchen）交付状态板

> 更新：2026-11-06 16:20 ｜ 角色：QA & Monitoring Engineer
> **对齐说明**：已按 A 的 `docs/interface.md` v1.0 §9 把素材类别收敛为 6 类 / 23 例；
> `expired`、`missing_field` 两类因 §9 未定义，暂不写入 manifest，改提 `docs/interface_change_proposal_E.md`（待 A 批准）。
> 对应 01 方案 §4.5（E1–E9）、§5 交接契约表
> 整改依据：`docs/e_fix_plan.md`（P0–P3 全部条目）

**状态图例**：✅ 已交付（别人能直接用）｜🟡 脚本/骨架就绪，**尚未产出交付物**｜⛔ 阻塞｜⬜ 未开始

> 口径提醒：E1 / E4 / E5 的交付物是**素材、截图、邮件**，不是生成它们的脚本。
> 本表里 🟡 一律不算交付。

---

## 〇、整改对照表（e_fix_plan → 当前状态）

| 编号 | 条目 | 状态 | 说明 |
|---|---|---|---|
| P0-1 | 提交推送 | 🟡 | 本地已提交（`git log -1`）；**push 缺 GitHub 凭证**，需你本人登录 |
| P0-2 | `--dry-run` 假绿灯 | ✅ | 缺素材 exit 1；`--allow-missing-fixtures` 才 exit 0 |
| P0-3 | 换人组单张照片退化 | ✅ | 少于 2 人直接报错；配对改为 `(2i, 2i+1)` 必定不同人 |
| P1-1 | 有效期区间格式 | ✅ | 卡面印 `2012.03.05-2035.11.20`；`--legacy-expiry` 可回退 |
| P1-2 | 身份证校验位 | ✅ | GB 11643 mod 11-2，2000 个随机号 100% 通过 |
| P1-3 | 5 张真实拍摄样本 | ⛔ | 需打印 + 手机拍摄，11-08 手工做 |
| P1-4 | 素材 sha256 | ✅ | 生成时写 `SHA256SUMS`；`.gitignore` 只挡图片，不挡该文件（待真实素材生成后入库） |
| P2-1 | DLQ 累计值 → 本轮值 | ✅ | 按 `application_id` 与消息体做集合比对，`dlq_corrupted` 报 `x/20` |
| P2-2 | 延迟双口径 | ✅ | service（created_at→processed_at）与 e2e（t_submit→processed_at）；空样本直接 exit，不再输出 `nan` |
| P2-3 | 坏文件随机混入 + burst | ✅ | 按概率混入全窗口；`--profile burst`；实际计数以 submitted.csv 为准 |
| P2-4 | 接回 C 的 presign | ✅ | `--presign-module security.presign`，另有 `--sse` 补头 |
| P3-1 | Ch6 Alerting / 删预写结论 / 引用 | ✅ | 新增 `sec:alerting` 与告警表；结果段只留 TODO 模板；补 `aws2024cloudwatch` 条目（交 F 追加） |
| P3-2 | preflight 升格契约自检 | ✅ | 桶私有 / SSE-S3 / 生命周期 7 天 / 重试 3 次 / DLQ 14 天 / 可见性 / Lambda 规格 / STANDARD |
| P3-3 | 目录补齐 | ✅ | `figures/` `tables/` `screenshots/` |

---

## 一、我欠别人的文件（按截止日）

| 交付物 | 文件 | 欠谁 | 截止 | 状态 |
|---|---|---|---|---|
| manifest 清单 | `tests/fixtures/manifest.csv` | B/C/D | 11-08 | ✅ 23 例，对齐 `docs/interface.md` §9 |
| 生成/自检脚本 | `tests/gen_fixtures.py` | B/C/D | 11-08 | ✅ 可跑（demo 已验证） |
| **首批 5 组正常素材** | `tests/fixtures/id-card/normal_0{1..5}.jpg` + `selfie/` | **B（Li Donghan）** | **11-08** | ⛔ 等照片 + 等打印 |
| **全量 23 例素材 + SHA256SUMS** | `tests/fixtures/**` | **B/C/D** | **11-10** | ⛔ 等照片 |
| 压测脚本 | `tests/load_test.py` | 自己 / A 可复用 | 11-14 | 🟡 已就绪，未实战 |
| 结果收集脚本 | `tests/collect_results.py` | 自己 | 11-17 | 🟡 已就绪，未实战 |
| 契约自检器 | `tests/preflight.py` | 全组（A6 联调用） | 11-18 | 🟡 已就绪，未实战 |
| 仪表盘截图 ×3 | `screenshots/6_dashboard_*.png` | **A** | 11-18 | ⛔ 等资源 |
| 告警截图 + 邮件 | `screenshots/6_alarm_*.png` | A | 11-20 | ⛔ 等 F3 |
| 两轮压测数据 | `results/load_test_r{1,2}_{submitted,summary}.csv` | 自己 → **F** | 11-25 | ⛔ 等 M2 |
| 延迟曲线 | `figures/fig_e_latency.pdf` | A | 11-25 | ⛔ 等数据 |
| Ch6 正文（数字） | `report/sections/sec6_testing.tex` | **A** | **11-30** | 🟡 骨架已交，结果段为空 |
| 报告表格 | `tables/tab_e_loadtest.tex` | A | 11-30 | ⛔ 脚本可生成 |
| 成本复核意见 | Overleaf Comment | **F** | 12-01 | ⛔ 等 F 稿 |
| 幻灯 2 页 + 讲稿 | PPT | A | 彩排① 前 | ⬜ 未开始 |

---

## 二、我等别人的文件

| 我需要的 | 谁 | 具体文件 / 资源 | 截止 | 拿不到时 |
|---|---|---|---|---|
| 自拍照片（每人 1–2 张，**至少 2 个不同的人**） | **B / C / D / F / A** | 直接发群或共享盘 | 11-07 | 无法生成换人组，`gen_fixtures.py` 会拒绝运行 |
| 共享盘位置（放 23 例素材） | **A（Zuo Yuhong）** | 待定目录 | 11-08 | 素材只能本地各跑，三套图不一致 |
| S3 桶 | **C（Hu Zhongyuan）** | `vericloud-raw-<组号>` | 11-08 | 自建临时桶 |
| 预签名脚本 | **C** | `security/presign.py` | 11-10 | 内置实现，`--presign-module` 后补 |
| DynamoDB 表 | **F（Yang Xueli）** | `vericloud-kyc-table` | 11-08 | 自建临时表 |
| SQS + DLQ | **D（Su Changwei）** | `vericloud-ingest-queue` / `-dlq` | 11-09 | 无替代 |
| SNS 运维主题 ARN | **F** | `vericloud-ops-alarm` ARN | 11-10 | 临时 topic |
| `processed_at` 字段 | **D** | `stepfunctions/kyc_workflow.asl.json` 的 PutItem | 11-17 | 延迟算不出来，脚本会直接 exit |
| 端到端跑通（M2） | **A** 主持，B/C/D 配合 | `docs/integration_log.md` + `ExecutionsSucceeded` ARN | **11-20**（最迟 11-22） | 11-19 先跑 10 个预演 |
| 成本章节 | **F** | `sec5b_cost.tex`、`tab_f_tco.tex`、`fig_f_tco.pdf` | 12-01 | 只能等 |

---

## 三、还不能生成的文件

| 文件 | 卡在哪 | 依赖谁 + 什么文件 | 解锁条件 |
|---|---|---|---|
| `tests/fixtures/id-card/*`、`selfie/*` | 需要真人照片 | 全组 5 人自拍（无路径，直接发图） | 收到 ≥2 人照片 |
| `tests/fixtures/broken/*` | 由 `normal_01.jpg` 派生 | 上一条 | 同上 |
| `SHA256SUMS`（真实版） | 需要真实素材 | 同上 | 素材生成后自动产出 |
| `normal_01..05` 的 `printed` 版 | 需打印 + 手机拍摄 | 打印机 + 本人 | 11-08 手工 |
| `screenshots/6_dashboard_*.png` | 无 CloudWatch 数据 | B `lambda/ocr/`、C `lambda/face/`、D `lambda/starter/` | 状态机可执行 |
| `screenshots/6_alarm_*.png` | 告警发不出去 | F `vericloud-ops-alarm` ARN | 主题 + 邮件订阅确认 |
| `results/load_test_*_submitted.csv` | 无可压测环境 | A M2 + C 桶 + D 队列 | M2 通过 |
| `results/load_test_*_summary.csv` | 表里无记录 | 上一条 + F 表 + D `processed_at` | 压测后 10 分钟 |
| `tables/tab_e_loadtest.tex` | 由 summary 生成 | 上一条 | 同上 |
| `figures/fig_e_latency.pdf` | 由 summary 画图 | 同上 | 同上 |
| Ch6 的 Results / Discussion | 没有数字 | 同上 | 11-25 |
| E8 复核意见 | F 成本稿未出 | F `sec5b_cost.tex` | 12-01 |

---

## 四、需要别人拍板的三件事

1. **有效期格式（找 B，抄送 A）**
   fixture 卡面印区间 `2012.03.05-2035.11.20`，`vericloud-ocr` 的 `expiry_date` 仍输出单个失效日 `YYYY-MM-DD`（取右端）。请 B 确认正则按区间写；A 补进 `docs/interface.md`。B 若 11-13 前来不及改，用 `--legacy-expiry` 临时退回并群里声明。

2. **共享盘位置（找 A）**
   图片不进 git，23 例怎么分发给 B/C/D？需要 A 指定目录；否则三人各跑一次 `gen_fixtures.py`，得到三套不同的图，`SHA256SUMS` 就失去意义。

3. **`report/sections/` 目录（找 A）**
   按 02 指南 §4.4 的兜底路径建的 GitHub 暂存副本，最终以 Overleaf 为准。保留还是删除，A 定。

---

## 五、本地提交状态

- 提交：`[E] tests: fixture generator, load test, collector, preflight, Ch6 skeleton`（hash 见 `git log -1 --oneline`）
- 内容：`.gitignore`、`docs/`、`report/`、`results/`、`tests/`、`figures/.gitkeep`、`tables/.gitkeep`（无照片、无凭证）
- **push 未完成**：本机没有 GitHub 凭证（无 `~/.git-credentials`、无 SSH key、无 `gh`），`git push` 报 `could not read Username`。
