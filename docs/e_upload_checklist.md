# E 交付物上传清单与逐文件核对（2026-11-06 14:50）

> 对照：`01_VeriCloud_六人分工与时间线执行方案.md` §4.5 / §5 / §9.2 / §12
> 对照：`02_VeriCloud_Overleaf协同写作与排版指南.md` §1 / §3.3 / §3.5
> 本地提交：`a6ac32f [E] tests: ...`（rebase 后）
> **2026-11-06 16:30 修订**：A 已发布 `docs/interface.md` v1.0，§9 把素材定为 **6 类 / 5 列**；
> **2026-11-09 再修订**：manifest 已按 v1.3 提案升到 **27 例 / 8 类 / 6 列**；`--sse` 已移除；延迟改三口径。本文其余段落为 11-06 快照，以 `docs/e_delivery_status.md` 为准。
> **远端状态：`main` 领先 `origin/main` 1 个提交，push 未完成（缺 GitHub 凭证）**

图例：✅ 可上传，无需改动 ｜ ⚠️ 可上传，但需在下一个提交里补 ｜ ⛔ 阻塞，需别人给东西

---

## 〇、先说结论

1. **15 个文件全部可以推。** 剩下的问题都是"内容待补 / 口径待对齐"，不是结构错误。11-08 首批素材是 B1 的前置，**先推让 B/C/D 拿到脚本和 manifest，比等完美更重要**。
2. **唯一挡住上传的是 GitHub 认证**（不是文件问题）。见第 3 节，三选一，5 分钟。
3. **还剩 3 个真问题**：Ch6 的 36 s / 60 s 自相矛盾、双轮表格没有生成器、`--check` 覆盖不全（README 承诺 4 类，实际只验 2 类）。

---

## 一、✅ 没有问题，可以立即上传（12 个）

| 文件名 | 我做了什么 | 功能 / 作用 | 谁需要 | 对方还要做什么 |
|---|---|---|---|---|
| `tests/gen_fixtures.py` | 1012×638 合成证件、GB 11643 合法校验位、区间有效期、SAMPLE 水印、坏文件、SHA256SUMS、`--check` 比脸自检 | 全组唯一造素材入口；保证 B/C/D 用的是同一套图 | **B / C / D**（造图与单测）、**A**（归档） | B/C/D：从共享盘取图后先 `shasum -c SHA256SUMS`；不要自己改脚本参数另造一套 |
| `tests/load_test.py` | 60 s / 100 申请；uniform 与 burst 两档；坏文件按概率混入；`--presign-module` 接 C 的实现；素材缺失直接 exit 1 | 产出 `results/load_test_rN_submitted.csv`，是全部延迟与调用量数字的唯一来源 | **自己**；**A**（A6 联调可复用）；**C**（提供 presign 函数名）；**F**（要调用量） | C：交付 `security/presign.py` 后告知函数名，E 改 `--presign-func`；F：用 `submitted.csv` 行数算实测成本 |
| `tests/collect_results.py` | ingress / service / end-to-end 三口径延迟；DLQ 按 `application_id` 集合比对；reason 比对；空样本 exit 5；导出 LaTeX 表 | 把 DynamoDB + DLQ 变成报告里可核对的数字 | **自己**；**F**（取数）；**A**（数字关抽查） | F：压测后向 E 索取 `summary.csv`，不得自行估算；A：数字关按 `results/` 核对 |
| `tests/preflight.py` | 资源存在性 + §9.2 一致关红线：桶四项私有、SSE-S3、生命周期 7 天、`maxReceiveCount=3`、DLQ 14 天、可见性超时、Lambda python3.12/1024MB/60s、状态机 STANDARD | 一条命令替 C/D 抓配置红线；Learner Lab 会话恢复后的自检 | **A / C / D**（联调前）、**自己**（每次压测前） | C/D：看到 ❌ 先修再联调，不要绕过 |
| `tests/fixtures/manifest.csv` | 27 例、8 类、6 列（含 `expected_reason`，按 v1.3 提案） | 单测与压测的**唯一事实来源** | **B / C / D** | D：Choice 的 `reason` 字符串仍按 §12.3（`face_error`/`similarity_below_80`/`auto_approved`）；FAIL 的 `id_expired`/`ocr_failed` 待 interface 升到 v1.3 后补用例 |
| `tests/fixtures/README.md` | 目录约定、六类预期、四个设计决定、造图规则、共享盘校验流程 | 素材的"说明书"，防止 B/C/D 各理解一套 | **B / C / D** | 按第 4 节规则造图；`printed` 5 张由 E 提供，不要自行替换 |
| `tests/README.md` | 一次性准备、造图、自检、压测四步（含 purge 时序）、指标口径表、五个常见坑 | 全组运行手册；**指标口径表是数字关的核对依据** | **A / B / C / D / F** | A：联调按第 3、4 节顺序执行；F：成本按第 5 节口径理解"调用量" |
| `tests/requirements.txt` | boto3 / requests / Pillow / numpy / pandas / matplotlib | 依赖锁定，避免版本差异导致的复现失败 | **全组** | 各自 `pip install -r tests/requirements.txt` |
| `docs/e_delivery_status.md` | 整改对照、欠谁 / 等谁 / 阻塞、需三人拍板事项、本地提交状态 | 让 A 一眼看到 E 的阻塞点与依赖 | **A**（统稿与调度）、全组可见 | A：处理第 4 节三件拍板事项（有效期格式、共享盘位置、`report/` 去留） |
| `.gitignore` | 挡 `.env`/`*.pem`/`credentials`/照片；**保留 `results/*.csv`**（数字关溯源）；挡 LaTeX 中间产物 | 防隐私事故 + 保证据链 | **A**（仓库骨架负责人） | A：确认后保留；如需调整请先告知 E，避免照片误入库 |
| `figures/.gitkeep`、`tables/.gitkeep` | 建目录占位（01 §12.4、02 §1 要求） | 让 `\includegraphics{figures/...}` 与 `\input{tables/...}` 路径存在 | **A**（Overleaf 同步时） | A：Overleaf 侧同名目录建好，图与表按 `fig_e_*` / `tab_e_*` 命名 |
| `docs/e_fix_plan.md` | 14 条整改方案（问题→改法→验证→时间表） | 团队可见的整改依据；也可作为 A 抽查 E 进度的对照 | **A**（可选） | A：只作参考，不必逐条回复 |

---

## 二、⚠️ 有问题，但**照样可以推**（3 个，下个提交修）

### 2.1 `report/sections/sec6_testing.tex` —— 两处硬伤 + 两个外部依赖

| 项 | 内容 |
|---|---|
| **问题 1（必改）** | 同一段自相矛盾：第 80 行写 "The four Lambdas ... a 60 s timeout"，第 82 行写 "the ingestion queue has a 36 s visibility timeout, six times the pre-check timeout"——36 = 6×6，与上一句的 60 s 冲突；且 `preflight.py:120` 校验的是 `>= 360`，三处口径不一致 |
| **问题 2（必改）** | `36` 应改为 `360`，并解释来源：pre-check Lambda 超时 60 s × 6 = 360 s（符合 01 §D1"可见性超时 ≥ starter 超时 × 6"） |
| **问题 3（需外部确认）** | `\cite{aws2024cloudwatch}` 的 bib 条目还只是文末注释，要 **F** 追加进 `references.bib`，否则编译出 `[?]` |
| **问题 4（需外部确认）** | `\ref{sec:fault}` 依赖 **D** 在 `sec4_fault_tolerance.tex` 里写 `\label{sec:fault}`，否则出 `??` |
| **问题 5（必补）** | 表格只有单轮生成器（见 2.2），但 caption 写的是 "two rounds" |
| 我做了什么 | 指标定义（四族 + 三口径延迟说明）、工作负载与故障注入、testbed 参数、27 例覆盖表、**新增 Alerting 小节与告警表**、结果段改为占位模板、补两条引用 |
| 功能 / 作用 | Ch6 正文，占报告 0.5–1.5 页；E4/E5 的截图与告警策略在这里落地 |
| 对接给谁 | **A**（统稿，注意 `report/` 目录去留）、**F**（补 bib key）、**D**（补 label） |
| 怎么改 | 见下方"改法 1" |

**改法 1（3 分钟，只改一句话）**

```latex
% 第 79-83 行整段替换
All experiments ran in \texttt{us-east-1} on AWS Academy Learner Lab. The four
Lambdas use the Python 3.12 runtime; the pre-check function has a 60\,s timeout
and the OCR and face workers 60\,s with 1024\,MB of memory. The state machine is
a Standard workflow. The ingestion queue uses a 360\,s visibility timeout, six
times the pre-check timeout, so that a message is never retried while it is still
being processed.
```

同时把 `preflight.py:120` 保持不变（它验的 360 是对的），并在群里给 D 一句话：
> starter 的 Lambda 超时按 60 s 配，SQS 可见性超时 360 s，与 Ch6 和 preflight 对齐。

### 2.2 `tests/collect_results.py` —— 没有"两轮合并成一张表"的能力

| 项 | 内容 |
|---|---|
| **问题** | `--latex` 每次只写单轮单列 `{lr}`，注释里让你"再合并成两列表格"——手工合并 = 手抄数字，直接踩 §9.2 数字关 |
| 我做了什么 | 三口径延迟、DLQ 逐条比对、reason 比对、LaTeX 导出 |
| 作用 | 报告 Table `tab:loadtest` 的唯一来源 |
| 对接给谁 | **A**（数字关抽查）、**F**（成本取数） |
| 怎么改 | 加一个 `--merge` 模式（约 25 行），见下 |

```python
    ap.add_argument("--merge", nargs=2, metavar=("R1_CSV", "R2_CSV"), default=None,
                    help="把两轮 summary.csv 合并成三列表格（与 Ch6 的 two rounds 对应）")

    if args.merge:
        def load_summary(p):
            rows = list(csv.reader(Path(p).open(encoding="utf-8")))
            return {r[0]: r[1] for r in rows if len(r) == 2 and r[0] in METRIC_COLUMNS}
        s1, s2 = load_summary(args.merge[0]), load_summary(args.merge[1])
        rows = [
            ("Applications submitted", s1["submitted"], s2["submitted"]),
            ("Records persisted", s1["in_table"], s2["in_table"]),
            ("Verdicts PASS / REVIEW / FAIL",
             f"{s1['pass']} / {s1['review']} / {s1['fail']}",
             f"{s2['pass']} / {s2['review']} / {s2['fail']}"),
            ("Corrupted isolated in DLQ", s1["dlq_corrupted"], s2["dlq_corrupted"]),
            ("p50 / p99 service latency (s)", f"{s1['p50_s']} / {s1['p99_s']}",
             f"{s2['p50_s']} / {s2['p99_s']}"),
            ("p95 / p99 end-to-end latency (s)", f"{s1['e2e_p95_s']} / {s1['e2e_p99_s']}",
             f"{s2['e2e_p95_s']} / {s2['e2e_p99_s']}"),
        ]
        out = ["% 由 tests/collect_results.py --merge 自动生成，请勿手改数字",
               "\\begin{tabular}{lrr}", "\\toprule",
               "Metric & Round 1 & Round 2 \\\\", "\\midrule"]
        out += [f"{k} & {a} & {b} \\\\" for k, a, b in rows]
        out += ["\\bottomrule", "\\end{tabular}"]
        Path(args.latex).parent.mkdir(parents=True, exist_ok=True)
        Path(args.latex).write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"已写入两轮合并表 {args.latex}")
        return
```

用法（写进 `tests/README.md` 第 4 节末尾）：

```bash
python tests/collect_results.py --table vericloud-kyc-table --dlq-url <URL> \
    --submitted results/load_test_r2_submitted.csv --out results/load_test_r2_summary.csv
python tests/collect_results.py --merge results/load_test_r1_summary.csv \
    results/load_test_r2_summary.csv --latex tables/tab_e_loadtest.tex
```
（`--submitted` 改为非必填，`--merge` 模式下不需要。）

### 2.3 `tests/gen_fixtures.py` `--check` 覆盖不全

| 项 | 内容 |
|---|---|
| **问题** | `fixtures/README.md` §5 承诺"无人脸/坏文件按预期失败"，但 `check()` 只验 `normal_*` 与 `different_person_*`。**模糊与无人脸两组从未被验证**：`GaussianBlur(18)` 之后 Rekognition 可能仍能检到脸，此时实际 `reason` 会是 `similarity_below_80` 而不是 manifest 写的 `face_error` |
| 后果 | D 的 Choice 按 `face_error` 路由，单测会"莫名失败"，然后跨人互相甩锅 |
| 我做了什么 | 生成器 + 自检 + SHA256SUMS |
| 作用 | 全组素材来源 |
| 对接给谁 | **C**（face Lambda 的异常类型）、**D**（Choice 路由）、**B**（不涉及但会看 manifest） |
| 怎么改 | 在 `check()` 里补两段；若实测确为 `similarity_below_80`，把 manifest 对应两行改过来并通知 C/D |

```python
        # 模糊 / 无人脸：必须让 compare_faces 抛异常或相似度极低
        for name in ("quality_blur_01", "quality_blur_02",
                     "quality_noface_01", "quality_noface_02"):
            idp, sp = out / "id-card" / f"{name}.jpg", out / "selfie" / f"{name}.jpg"
            if not (idp.exists() and sp.exists()):
                continue
            try:
                s = similarity(idp, sp)
                print(f"  {name:20s} similarity = {s:.2f}")
                if s >= 80:
                    problems.append(f"{name}: 相似度 {s:.1f}，会被判 similarity_below_80 而非 face_error，"
                                    f"请调整该样本的 expected_status 或重做样本")
            except Exception as exc:  # noqa: BLE001
                print(f"  {name:20s} 按预期抛异常（{type(exc).__name__}）")
```

> 附带一提：`fixtures/README.md` 标题写"三个必须知道的设计决定"，正文列了四条，把"三"改成"四"。

---

## 三、先解决上传：GitHub 认证（5 分钟，三选一）

现状：`git status -sb` 显示 `## main...origin/main [ahead 1]`；`git push` 报 `could not read Username`。本机无 `gh`、无 SSH key、无 `~/.git-credentials`。

**方案 A｜PAT + 钥匙串（推荐，最稳）**

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained token**，只勾 `zuoyuhong783-sudo/KYC`，权限 `Contents: Read and write`。
2. 终端执行：

```bash
cd ~/Desktop/kyc
git config --global credential.helper osxkeychain
git push origin main          # 提示 Username 填 GitHub 用户名，Password 粘 PAT（不是账号密码）
```

3. 之后系统钥匙串会记住，不用再输。**不要把 PAT 写进 remote URL 或任何文件**。

**方案 B｜SSH key**

```bash
ssh-keygen -t ed25519 -C "lihengchen@cds538" -f ~/.ssh/id_ed25519 -N ""
pbcopy < ~/.ssh/id_ed25519.pub        # 粘到 GitHub → Settings → SSH and GPG keys
cd ~/Desktop/kyc && git remote set-url origin git@github.com:zuoyuhong783-sudo/KYC.git
ssh -T git@github.com                 # 出现 "Hi <user>!" 即成功
git push origin main
```

**方案 C｜GitHub Desktop / VS Code 内置登录**：图形化登录后直接 Push 按钮。

> 前置确认：**A 是否已把你的 GitHub 账号加为协作者**（01 §A3、第十四节 checklist 该项未勾）。没加的话，PAT 也会 403。群里问一句："A，仓库协作者加我了吗？"

推送后立刻在群里发（模板）：

> E 已推 `3d68282`：`tests/`（造图 / 压测 / 汇总 / 契约自检）、`report/sections/sec6_testing.tex`（Ch6 骨架）、`docs/`、`.gitignore`。
> 三件事需要确认：
> 1. **A**：共享盘放 27 例素材的目录（图片不进 git，否则每人各跑一套图，`SHA256SUMS` 失效）；`report/sections/` 保留还是删。
> 2. **B**：fixture 卡面有效期印**区间** `2016.01.25-2038.03.11`，`expiry_date` 仍输出右端 `YYYY-MM-DD`，请确认正则；证件号带合法校验位，别按假号处理。
> 3. **C / D**：`tests/preflight.py` 会校验桶私有 + SSE-S3 + 生命周期 7 天 + 重试 3 次 + DLQ 14 天，联调前先跑一遍。

---

## 四、本次核对结论（对照 11-06 上午那批问题）

| 原问题 | 现状 | 证据 |
|---|---|---|
| 全部未提交 | ✅ 已提交 `3d68282`；⛔ push 未完成 | `git log`、`status -sb` |
| `--dry-run` 假绿灯 | ✅ 已修 | 缺素材 `exit 1`；实测 1 张照片生成直接报错退出 |
| 换人组单张照片退化 | ✅ 已修 | 实测单张 → `[FAIL] 需要至少 2 个不同的人`，exit 1 |
| 有效期单日期 | ✅ 已修 | 实测卡面 `2017.01.24-2033.05.08` |
| 身份证无校验位 | ✅ 已修 | 2000 个随机号，校验位不通过 0 个 |
| 素材无 sha256 | ✅ 已修 | 48 个文件写入 `SHA256SUMS`，`shasum -c` 全 OK |
| DLQ 累计值 | ✅ 已修 | 改为 `application_id` 集合比对，输出 `20/20` |
| 延迟口径错 | ✅ 已修 | service 与 e2e 双列，空样本 exit |
| 坏文件集中在前 20 个 | ✅ 已修 | 按概率混入全窗口 |
| 无 burst 对照 | ✅ 已修 | `--profile burst` |
| 绕过 C 的 presign | ✅ 已修 | `--presign-module`（`--sse` 因签名不匹配已移除） |
| Ch6 缺 Alerting / 预写结论 / 无引用 | ✅ 已修 | `sec:alerting` + 告警表 + 结果段改 TODO |
| preflight 不查红线 | ✅ 已修 | 桶/队列/Lambda/状态机共 9 项 |
| Ch6 36 s 与 60 s 矛盾 | ⚠️ **未修** | 见 2.1 |
| 双轮表无生成器 | ⚠️ **未修** | 见 2.2 |
| `--check` 不验模糊/无人脸 | ⚠️ **未修** | 见 2.3 |
| 5 张真实拍摄样本 | ⛔ 待 11-08 手工 | 需打印机 |

---

## 五、上传后 48 小时的动作

| 时间 | 动作 | 依赖 |
|---|---|---|
| 今天 | 解决认证 → `git push`；群里发第三节模板 | A 加协作者 |
| 今天 | 改 2.1 的 36→360，第二个提交推上去 | D 确认 starter 超时 |
| 11-07 | 收 ≥2 人照片 → 生成 → `--check`（含 2.3 补的两段）→ 首批 5 组交 B | B/C/D/F/A 各 1 张 |
| 11-08 | 打印 5 张 → 手机拍 → 覆盖 `normal_01..05` → 在共享盘清单标注 `printed` | 打印机 |
| 11-10 | 全量 27 例 + `SHA256SUMS` 打包上传共享盘，通知三人校验 | A 给目录 |
| 11-10 | 若 `--check` 发现模糊组实为 `similarity_below_80`，改 manifest 并通知 C/D | C 的 face Lambda 可跑 |
