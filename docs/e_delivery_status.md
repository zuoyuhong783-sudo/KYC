# E（Li Hengchen）交付状态板

> 更新：2026-11-09 15:30 ｜ 角色：QA & Monitoring Engineer
> 契约：`docs/interface.md` **v1.2**（桶 `vericloud-raw-1009`、区域 `us-east-1`、长期有效期 `9999-12-31`）
> 对应：01 方案 §4.5（E1–E9）、§5 交接契约表、§9.2 四道关卡

**状态图例**：✅ 已交付（别人可直接用）｜🟡 已就绪但未产出交付物｜⛔ 阻塞｜⬜ 未开始

> 口径提醒：E1 / E4 / E5 的交付物是**素材、截图、邮件**，不是生成它们的脚本。🟡 不算交付。

---

## 一、已完成、可直接交付的文件

| 文件 | 内容 | 交给谁 |
|---|---|---|
| `tests/gen_fixtures.py` | 合成证件（GB 11643 校验位、区间有效期、SAMPLE 水印、卡底编号只留后 4 位）、换人/模糊/无脸/过期/字段缺失/坏文件、`--check` 比脸自检、SHA256SUMS（**待真实素材生成后入库**） | **B / C / D** |
| `tests/load_test.py` | 60 s / 100 申请；uniform 与 burst 两档；坏文件按概率混入；**已接 C 的 `security.presign`**；`--sse`；素材缺失即 exit 1 | **C**（确认 presign 调用）、**F**（取调用量） |
| `tests/collect_results.py` | 双口径延迟（service / end-to-end）、DLQ 按 `application_id` 逐条比对、`--purge-only`、自动生成 LaTeX 表 | **F**、**A**（数字关） |
| `tests/preflight.py` | 资源 + 红线 + **三条连线**（S3→SQS、SQS→starter、Streams→notify）；SNS 未建不再算阻塞 | **A / C / D** |
| `tests/fixtures/manifest.csv` | 27 例、8 类、6 列（按 v1.3 提案，含 `expected_reason`） | **B / C / D** |
| `tests/fixtures/README.md` | 素材规格、造图规则、自检与分发流程 | **B / C / D** |
| `tests/README.md` | 运行手册：准备 → 造图 → 自检 → preflight → 压测 → 收集 | **全组** |
| `tests/check_precheck.py` | 本地判断坏文件会不会被 starter 拦下（复现 2000 B 截断漏网） | **D**（据此改预检） |
| `tests/requirements.txt` | Python 依赖 | 全组 |
| `report/sections/sec6_testing.tex` | **Ch6 正文初稿**：指标与双口径、负载与故障注入、告警设计、讨论与局限；结果段留 TODO | **A**（统稿） |
| `docs/e_monitoring_spec.md` | 仪表盘三行 widget 与三条告警（worker / DLQ / workflow）的配置规格 + 截图落点 | **A**、自己（11-18/20 建） |
| `docs/e_bib_entries.bib` | `aws2024cloudwatch` 条目 | **F**（追加进 `references.bib`） |
| `results/README.md` | 压测 CSV 的字段与口径，供 F 取数、A 抽查 | **F / A** |
| `docs/e_cost_review_checklist.md` | E8 复核清单（单价 / 调用量 / 70% 结论） | **F** |
| `docs/e_defence_script.md` | E9 两分钟讲稿、2 页幻灯、4 个预期提问 | **A** |
| `docs/interface_change_proposal_E.md` | 申请 §9 增 `expired`/`missing_field`（覆盖 FAIL） | **A** |
| `docs/e_delivery_status.md` | 本文件 | 全组 |
| `docs/e_upload_checklist.md` | 逐文件核对与上传步骤 | 自己 |
| `docs/e_fix_plan.md` | 14 条整改依据 | A（参考） |
| `.gitignore` | 挡凭证与组员照片，保留 `results/*.csv` | **A** |

---

## 二、部分完成

| 交付物 | 现状 | 缺什么 |
|---|---|---|
| Ch6（`sec6_testing.tex`） | 除 Results 外全部成文（约 1.5 页） | 两轮压测数字、3 张图 |
| 素材包 | 生成器与清单就绪 | 真人照片（见下） |

---

## 三、阻塞清单（缺谁 / 缺什么文件）

| 交付物 | 缺什么 | 找谁 |
|---|---|---|
| 首批 5 组 normal 素材（11-08，已逾期） | **≥2 位组员的自拍照片**（A 在 11-11 M1 协调提供人与共享盘目录） | A 协调；B / C / D / F 提供照片 |
| 全量 23 例 + SHA256SUMS | 同上 | 同上 |
| 5 张 `printed` 真拍样本 | 打印机 + 手机拍 | 自己（材料齐后 1 小时） |
| 仪表盘 / 告警截图 | Lambda 部署完成、SNS 主题 `vericloud-ops-alarm` 的 ARN | B/C/D 部署；**F** 建主题 |
| 两轮压测数据 | M2 端到端跑通（`ExecutionsSucceeded` 证据） | **A** 主持；B/C/D 配合 |
| Ch6 的 Results 段 | 上述压测数据 | 自己 |
| E8 复核意见 | F 的成本稿 `sec5b_cost.tex` + `tab_f_tco.tex` + `fig_f_tco.pdf` | **F**（12-01） |
| §9 的 FAIL 用例 | A 批准 `interface_change_proposal_E.md`（升 v1.3） | **A** |

---

## 四、需要别人拍板

1. **A**：批准 §9 增两类（`expired`、`missing_field`），否则 `FAIL` 分支没有真实用例。
2. **A**：共享盘放 27 例素材的目录（图片不进 git）。
3. **B**：确认 OCR 正则按"区间有效期 + 长期 = 9999-12-31"写（interface v1.2）。
4. **C**：确认压测调用 `generate_upload_urls(application_id)` 的方式与其 `profile` 约定一致。

---

## 五、提交状态

- 6 个提交已于 **2026-11-09 11:52** 推送到 `origin/main`（`e5a6600`），远端与本地差异当时为 `0 0`；
- 推送后 A 又推进了 1 个提交（`b064959`），本地落后 1 个，下次开工先 `git pull --rebase` 即可；
- 本轮按 A 的评审意见（`docs/review_A_on_E_proposal_v1.3.md`）继续修改，改完再推一次。

> 不在仓库里记录任何令牌或带 `<PAT>` 的命令行；token 只由本人在本机一次性使用。
