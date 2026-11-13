# E（Li Hengchen）交付状态板

> 更新：2026-11-13 ｜ 角色：QA & Monitoring Engineer
> 契约：`docs/interface.md` **v1.3.1**（桶 `vericloud-raw-1009-a`、区域 `us-east-1`、`received_at`、完整解码预检、8 类 27 例）
> 对应：01 方案 §4.5（E1–E9）、§5 交接契约表、§9.2 四道关卡

**状态图例**：✅ 已交付（别人可直接用）｜🟡 已就绪但未产出交付物｜⛔ 阻塞｜⬜ 未开始

> 口径提醒：E1 / E4 / E5 的交付物是**素材、截图、邮件**，不是生成它们的脚本。🟡 不算交付。

---

## 一、已完成、可直接交付的文件

| 文件 | 内容 | 交给谁 |
|---|---|---|
| `tests/gen_fixtures.py` | 合成证件（GB 11643 校验位、区间有效期、SAMPLE 水印、卡底编号只留后 4 位）、换人/模糊/无脸/过期/字段缺失/坏文件、`--check` 比脸自检、SHA256SUMS | **B / C / D** |
| `tests/fixtures/manifest.csv` | 27 例、8 类、6 列（含 `expected_reason`，对齐 v1.3.1） | **B / C / D** |
| `tests/fixtures/SHA256SUMS` | 48 个文件校验清单（已入库） | **B / C / D** |
| `tests/fixtures/README.md` | 素材规格、造图规则、评审结论、分发流程 | **B / C / D** |
| `tests/load_test.py` | 60 s / 100 申请；uniform + burst；坏文件按概率混入；接 C 的 `security.presign` | **F**（取调用量）、**C** |
| `tests/collect_results.py` | 三口径延迟（ingress / service / end-to-end）、DLQ 逐条比对、reason 比对、LaTeX 表 | **F**、**A**（数字关） |
| `tests/preflight.py` | 资源 + 红线 + 三条连线（S3→SQS、SQS→starter、Streams→notify） | **A / C / D** |
| `tests/check_precheck.py` | 本地验证坏文件在「完整解码」口径下被拦下 | **D** |
| `tests/README.md` | 运行手册（含退出码 0/3/4/5） | 全组 |
| `tests/requirements.txt` | Python 依赖 | 全组 |
| `samples/faces/` + `samples/README.md` | 组员本人照片（替换了早前的 AI 合成脸），做证件照与自拍的底图 | 自己 |
| `report/sections/sec6_testing.tex` | Ch6 正文初稿（三口径、负载与故障注入、告警、局限）；Results 段留 TODO | **A** |
| `docs/e_monitoring_spec.md` | 仪表盘三行 widget + 三条告警 + 截图落点 | **A**、自己 |
| `docs/e_bib_entries.bib` | `aws2024cloudwatch` 条目 | **F** |
| `results/README.md` | 压测 CSV 字段与口径 | **F / A** |
| `docs/e_cost_review_checklist.md` | E8 复核清单（单价 / 调用量 / 70% 结论） | **F** |
| `docs/e_defence_script.md` | E9 两分钟讲稿 + 2 页幻灯 + 4 个提问 | **A** |
| `docs/interface_change_proposal_E.md` | 已评审、已采纳进 v1.3 | **A** |
| `.gitignore` | 挡凭证与照片，保留 `results/*.csv` | **A** |

---

## 二、部分完成

| 交付物 | 现状 | 缺什么 |
|---|---|---|
| Ch6（`sec6_testing.tex`） | 除 Results 外全部成文 | 两轮压测数字、3 张图（`fig_e_dashboard.png`/`fig_e_latency.pdf`/`fig_e_alarm.png`） |
| 素材包 | 27 例已从组员照片生成，SHA 校验通过 | 5 张 `printed` 真拍样本（可选） |

---

## 三、阻塞清单

| 交付物 | 缺什么 | 找谁 |
|---|---|---|
| 仪表盘 / 告警截图（E4/E5） | Lambda / 状态机 / 表 / SNS 部署到演示账号并跑出数据 | A（A6 联调）、C/D/F |
| 两轮压测数据（E6） | M2 端到端跑通 | **A** 主持；B/C/D/F 配合 |
| Ch6 的 Results 段 + 3 张图 | 上述压测数据与截图 | 自己 |
| E8 复核意见 | F 的成本稿已提交（`sec5b_cost.tex`、`tab_f_tco.tex`、`fig_f_tco.pdf`），可开始复核 | **F**（已交）→ 自己复核 |
| 共享盘放 27 例素材的目录 | A 在 11-11 M1 会上定（图片不进 git） | **A** |

---

## 四、已经解决（不再阻塞）

- ~~§9 加 `expired`/`missing_field`~~ → 已采纳进 v1.3（2026-11-10 发布）。
- ~~§5.2 预检改完整解码~~ → D 已实现；`check_precheck.py` 可本地复现新旧口径差异。
- ~~§5.1 `received_at`~~ → starter 与状态机均已写入 DynamoDB。
- ~~C 的 presign 默认桶名~~ → A 已改为 `vericloud-raw-1009-a`，`load_test.py` 的调用签名匹配。

---

## 五、提交状态

- 远端已同步到 `origin/main` 最新（本次已 rebase）。
- 本轮本地改动（素材从真人照片重生成 + 文档刷新）待提交 / 推送；推送需本人在本机用 token（或双击桌面的 `一键上传.command`）。
- 仓库内不记录任何令牌或带 `<PAT>` 的命令行。
