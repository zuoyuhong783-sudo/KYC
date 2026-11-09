# E 角色交付整改方案（Li Hengchen）

> 依据：`01_VeriCloud_六人分工与时间线执行方案.md` §4.5 / §5 / §9.2 / §12
> 依据：`02_VeriCloud_Overleaf协同写作与排版指南.md` §1 / §3.3 / §3.5
> 编写：2026-11-06 ｜ 适用版本：当前仓库 HEAD（Initial commit 之后、未提交状态）

整改顺序按「先保住关键路径，再修证据链，最后补报告」三段。P0 当天做完，P1 到 11-10，P2 到 11-21。

---

## 总览

| 编号 | 问题 | 改哪个文件 | 预计 | 优先级 |
|---|---|---|---|---|
| P0-1 | 全部交付物未提交，队友拿不到 | git | 10 min | 最高 |
| P0-2 | `--dry-run` 素材全缺仍 exit 0 | `tests/load_test.py` | 10 min | 高 |
| P0-3 | 换人组单张照片退化 | `tests/gen_fixtures.py` | 15 min | 高 |
| P1-1 | 有效期格式与真实证件不符 | `tests/gen_fixtures.py` | 20 min | 高 |
| P1-2 | 身份证号无合法校验位 | `tests/gen_fixtures.py` | 15 min | 高 |
| P1-3 | 缺真实拍摄样本 | 手工 + manifest | 1 h | 高 |
| P1-4 | 素材无法逐份校验（无 sha256） | `tests/fixtures/manifest.csv` | 20 min | 中高 |
| P2-1 | DLQ 是累计值、无 case 级证据 | `tests/collect_results.py` | 40 min | 最高 |
| P2-2 | 延迟口径错 | `tests/collect_results.py` | 20 min | 高 |
| P2-3 | 坏文件集中在前 20 个、无 burst | `tests/load_test.py` | 25 min | 中高 |
| P2-4 | 压测绕过 C 的 presign | `tests/load_test.py` | 10 min | 中 |
| P3-1 | Ch6 缺 Alerting 小节、预写结论、无引用 | `report/sections/sec6_testing.tex` | 40 min | 高 |
| P3-2 | preflight 不校验契约硬指标 | `tests/preflight.py` | 40 min | 中高 |
| P3-3 | 目录缺失 figures/ tables/ | mkdir | 2 min | 低 |

---

## P0-1 先把东西推上去（10 分钟，今天就做）

> 2026-11-09 注：本节描述的仓库状态已过期。远端已有 13+ 个提交、`tests/` 等目录；最新状态见 `docs/e_delivery_status.md`。

```bash
cd ~/Desktop/kyc

# 只提交自己负责的目录（01 §12.4 Git 规则：每人只改自己的目录）
git add .gitignore
git add docs/e_delivery_status.md docs/e_fix_plan.md
git add report/ results/ tests/
git status --short          # 确认没有 .env / *.pem / 照片进暂存区

git commit -m "[E] tests: fixture generator, load test, collector, Ch6 skeleton"
git push origin main
```

然后给 A 发一条（建议直接贴群）：

> E 已推 `tests/`、`report/sections/sec6_testing.tex`、`docs/`。
> 两件事需要你定：
> 1. `.gitignore` 把 `tests/fixtures/**/*.jpg` 排除了（照片属个人敏感数据），所以**素材不走 git**。请确认共享盘 `fixtures/` 的位置，我把 27 例打包上传，B/C/D 从那里取，否则每人本地各跑一次会得到三套不同的图。
> 2. `report/sections/` 与 01 §12.4 的目录树不一致，按你之前的意见，我保留还是删除？

> 注意：`.gitignore` 是仓库级配置，严格说属于 A3 的范畴。你提交后要主动告知 A，避免他改仓库骨架时冲突。

---

## P0-2 `--dry-run` 假绿灯

**现状**：54 个素材文件全缺，只打一行 `[warn]`，然后 `exit 0`。而它的用途恰恰是"只验证素材与参数"（`tests/README.md` §5）。

**改 `tests/load_test.py`**，三处：

1) `load_pools()`（第 53–72 行）末尾，把 warn 改成可判定的返回值：

```python
    if missing:
        print(f"[warn] 有 {len(missing)} 个素材文件缺失（先跑 tests/gen_fixtures.py）")
        for m in sorted(set(missing))[:5]:
            print("   ", m)
    return pools, sorted(set(missing))
```

2) 调用处（第 97 行）：

```python
    pools, missing = load_pools(root)
    if missing and not args.allow_missing_fixtures:
        sys.exit(f"[FAIL] 缺 {len(missing)} 个素材文件，dry-run 不通过。"
                 f"先生成素材，或确认只查参数时加 --allow-missing-fixtures")
```

3) 参数区加一行：

```python
    ap.add_argument("--allow-missing-fixtures", action="store_true",
                    help="只校验参数，不校验素材是否存在")
```

**验证**：

```bash
python tests/load_test.py --bucket b --dry-run          # 应为 exit 1，报缺失数量
python tests/load_test.py --bucket b --dry-run --allow-missing-fixtures   # exit 0
```

---

## P0-3 换人组在单张照片下退化（会卡死你 11-08 的交付）

**现状**：`gen_fixtures.py:197` 取 `photos[i % n]` 与 `photos[(i+1) % n]`。`n == 1` 时两者是同一张脸，我实测 `mismatch_01..03` 证件照与自拍同一人。接着 `--check` 第 314 行报"相似度 ≥ 80，换人用例会误判 PASS"，而 README 写着"自检不过就别交付"——你会把自己锁死。

**改 `tests/gen_fixtures.py`**：

1) 照片加载后（第 171–175 行那段之后）加硬校验：

```python
    need_people = 2 if args.mismatch > 0 else 1
    if len(photos) < need_people:
        sys.exit(
            f"[FAIL] 换人组需要至少 {need_people} 个不同的人的自拍，当前只有 {len(photos)} 张。\n"
            f"  方案 A：找另外 1 位组员各发 1 张（推荐，5 分钟）\n"
            f"  方案 B：明确放弃换人组，加 --mismatch 0，并在状态板登记该指标缺失"
        )
```

2) 换人组配对（第 196–201 行）改成必定不同人：

```python
    for i in range(1, args.mismatch + 1):
        a = photos[(2 * (i - 1)) % len(photos)]
        b = photos[(2 * (i - 1) + 1) % len(photos)]
        card = make_card(photo=a, **fields(100 + i))
        save_jpeg(card, id_dir / f"mismatch_{i:02d}.jpg")
        save_jpeg(b, selfie_dir / f"mismatch_{i:02d}.jpg")
        made += 1
```

**验证**：单张照片目录跑 → 必须报错退出；两张照片目录跑 → `mismatch_01` 的证件照与自拍不是同一张脸（`--check` 相似度应 < 80）。

**顺带**：`normal` 组仍是 `photos[(i-1) % n]`，1 张照片时 10 例同脸。这不算错，但报告里别写"10 位不同申请人"，写"10 个申请包"。

---

## P1-1 有效期改成区间格式（与真实证件一致）

**现状**：卡面印 `2031-02-27`。真实身份证是 `2015.05.01-2035.05.01`。B 若按真实格式写正则，你的素材全抽不出；B 若迁就你的格式，答辩现场真图就崩。

**改 `tests/gen_fixtures.py`**：把 `fields()` 里的 `expiry` 换掉（第 177–183 行）。

```python
    def expiry_range(valid: bool) -> str:
        # 真实卡面格式：签发日期-失效日期，点分隔
        sy = rng.randint(2012, 2018)
        ey = (2032 + rng.randint(0, 7)) if valid else (2019 + rng.randint(0, 2))
        fmt = lambda: f"{rng.randint(1,12):02d}.{rng.randint(1,28):02d}"  # noqa: E731
        return f"{sy}.{fmt()}-{ey}.{fmt()}"
```

然后 `fields()` 返回：

```python
            "expiry": expiry_range(valid=False) if expired else expiry_range(valid=True),
```

**必须同步的一件事**（这是接口约定，不是代码问题）：在群里 @A 和 B 说清楚——

> fixture 卡面印**区间**（`2012.03.05-2035.11.20`），因为真实证件就是这个格式；
> `vericloud-ocr` 输出仍按 §12.3 只给**失效日** `expiry_date: "2035-11-20"`（取区间右端，转 `YYYY-MM-DD`）；
> 请 B 确认正则按区间写。这一条 A 应补进 `docs/interface.md`。

若 B 在 11-13 前已经按单日期写好、来不及改，加个兼容开关：

```python
    ap.add_argument("--legacy-expiry", action="store_true",
                    help="输出单日期 YYYY-MM-DD（兼容 B 的旧正则，仅临时用）")
```

---

## P1-2 身份证号补合法校验位

**现状**：`110101199404080001` 这类号码末位是流水号，GB 11643 的 mod 11-2 校验不通过。B 只要做一次校验位验证，27 例全判无效。

**改 `tests/gen_fixtures.py`**：常量区加上，`fields()` 改用：

```python
ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
ID_CHECK = "10X98765432"


def make_id_number(rng: random.Random, area: str = "110101") -> str:
    birth = f"{rng.randint(1980, 2002)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    body = f"{area}{birth}{rng.randint(1, 999):03d}"
    total = sum(int(c) * w for c, w in zip(body, ID_WEIGHTS))
    return body + ID_CHECK[total % 11]
```

`fields()` 里 `"id_number": make_id_number(rng)`。

自检里补一条（`check()` 的 `problems` 段）：

```python
    for p in sorted((out / "id-card").glob("*.jpg")):
        pass  # 图片无法反查号码，改在生成时断言
```

更实际的做法是在 `make_id_number` 里直接自检，避免写回图片再校验：

```python
    assert sum(int(c) * w for c, w in zip(body, ID_WEIGHTS)) % 11 == ID_CHECK.index(check)
```

**验证**：随便取一张生成结果，用任一在线 GB11643 校验器验一次（虚构号码，不涉及隐私）。

---

## P1-3 补 5 张真实拍摄样本（这条最影响 B 的准确率可信度）

脚本做不到，必须手工，但只做 5 张，1 小时够：

1. 生成 `normal_01..05` 的卡面（`--no-degrade --normal 5`），300 dpi 打 A4 → 裁成 85.6×54 mm。
2. 放在桌面，手机在自然光下、**略斜 10–15°、带一点投影**拍，别正对着平铺扫。
3. 覆盖 `tests/fixtures/id-card/normal_0{1..5}.jpg`（自拍保持原图）。
4. `manifest.csv` 加一列 `capture`，这 5 行填 `printed`，其余填 `synthetic`。

**报告里怎么写**（Ch6 §workload 补一句）：

> Five of the ten normal cases were printed at 300 dpi and re-photographed with a
> smartphone under ambient light and a 10--15° tilt, so that the measured OCR
> accuracy is not an artefact of digitally rendered card images.

这句能把"你的准确率是数字图打数字图"这个必被问的问题挡掉。

---

## P1-4 素材加 sha256（否则"唯一事实来源"名不副实）

图片不进 git，每人本地各跑一次 `gen_fixtures.py` 会得到内容不同的三套图，`manifest.csv` 的"唯一事实来源"就只剩文件名。B 报的 bug C 复现不了。

**做法**：`gen_fixtures.py` 生成完后输出校验文件。

```python
    # generate() 末尾
    import hashlib
    lines = []
    for p in sorted(list(id_dir.glob("*.jpg")) + list(selfie_dir.glob("*.jpg"))
                    + list(broken_dir.glob("*.jpg"))):
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}")
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ok] 已写 {out / 'SHA256SUMS'}（{len(lines)} 个文件）")
```

`SHA256SUMS` **要进 git**（`.gitignore` 只挡图片，不挡这个文件）。B/C/D 拿到共享盘素材后先跑：

```bash
cd tests/fixtures && shasum -a 256 -c SHA256SUMS      # macOS
```

全 `OK` 才算"用的是同一套素材"。这句话可以直接写进 Ch6 的可复现性说明。

---

## P2-1 DLQ：累计值 → 本轮值 + case 级证据（最影响数字关）

**现状两个毛病**：
- `collect_results.py:156` 用 `ApproximateNumberOfMessages`，是队列**生命周期累计**。两轮不 purge，第 2 轮报约 40，自动表出现 `submitted 100 = persisted 80 + dlq 40 = 120` 的自相矛盾。
- 只有聚合数，无法证明"20/20 坏文件都进了 DLQ"，而 §4.5 E6 的验收标准正是"坏文件 100% 进 DLQ"。

**改 `tests/collect_results.py`**：

1) 顶部加：

```python
import json
import re

APP_ID_RE = re.compile(r"raw/(?:id-card|selfie)/([0-9a-fA-F-]{36})")


def dlq_application_ids(sqs, url: str, max_msgs: int = 200) -> set[str]:
    """不删除、只看：从 DLQ 消息体里把 application_id 抠出来做集合比对。"""
    seen: set[str] = set()
    ids: set[str] = set()
    idle = 0
    while idle < 2 and len(seen) < max_msgs:
        resp = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10,
                                   AttributeNames=["All"], VisibilityTimeout=0)
        msgs = resp.get("Messages", [])
        if not msgs:
            idle += 1
            continue
        idle = 0
        for m in msgs:
            if m["MessageId"] in seen:
                continue
            seen.add(m["MessageId"])
            hit = APP_ID_RE.search(m.get("Body", ""))
            if hit:
                ids.add(hit.group(1).lower())
    return ids
```

2) 参数区加：

```python
    ap.add_argument("--purge-dlq", action="store_true",
                    help="压测前清空 DLQ（每轮开跑前用，避免累计值污染）")
```

3) 替换第 153–179 行整段汇总逻辑：

```python
    dlq_ids: set[str] = set()
    if args.dlq_url:
        sqs = boto3.client("sqs", region_name=args.region)
        if args.purge_dlq:
            sqs.purge_queue(QueueUrl=args.dlq_url)
            print("[info] 已请求清空 DLQ（约 60 s 生效，压测前执行）")
        dlq_ids = dlq_application_ids(sqs, args.dlq_url)
        print(f"DLQ 命中 {len(dlq_ids)} 条（本轮，按 application_id 去重）")

    submitted_ids = {s["application_id"] for s in submitted}
    corrupted_ids = {s["application_id"] for s in submitted if s["category"] == "corrupted"}
    dlq_hit = len(dlq_ids & submitted_ids)
    dlq_hit_corrupted = len(dlq_ids & corrupted_ids)

    summary = {
        "submitted": len(submitted),
        "in_table": len(items),
        "pass": status_counter.get("PASS", 0),
        "review": status_counter.get("NEEDS_HUMAN_REVIEW", 0),
        "fail": status_counter.get("FAIL", 0),
        "dlq": dlq_hit,
        "dlq_corrupted": f"{dlq_hit_corrupted}/{len(corrupted_ids)}",
        "pending": max(0, len(submitted) - len(items) - dlq_hit),
        "p50_s": round(percentile(latencies, 0.50), 2),
        ...
    }
```

`METRIC_COLUMNS` 里把 `dlq` 后加 `"dlq_corrupted"`。

4) 每轮流程改成（README §3 同步改）：

```bash
# 每轮开跑前先清 DLQ
python tests/collect_results.py --table vericloud-kyc-table --dlq-url <URL> \
    --submitted results/load_test_r1_submitted.csv --purge-dlq --no-wait --out /tmp/warmup.csv
```

> `purge_queue` 后约 60 s 才生效，所以要在压测**前**调用，不能压完再清。

这样报告里能写出真正有说服力的一句：

> All 20 corrupted packages were individually confirmed in the dead-letter queue
> (20/20 matched by `application_id`), not merely counted in aggregate.

---

## P2-2 延迟改双口径

**现状**：`created_at`（starter 收消息才写）→ `processed_at`，把 S3→SQS 排队和 starter 冷启动都扣掉了，却叫 end-to-end。漏掉的正好是 p99 的尾巴。

**改 `collect_results.py`**：

```python
    sub_by_id = {s["application_id"]: s for s in submitted}
    e2e_lat: list[float] = []     # 用户视角：PUT 完成 → 写库
    svc_lat: list[float] = []     # 服务视角：starter 收消息 → 写库
```

循环里（第 141–144 行位置）：

```python
            st = parse_iso(sub_by_id.get(app_id, {}).get("t_submit_utc", ""))
            if st and processed:
                e2e_lat.append((processed - st).total_seconds())
            if created and processed:
                svc_lat.append((processed - created).total_seconds())
```

`summary` 增加四列：`e2e_p50_s` / `e2e_p95_s` / `e2e_p99_s` / `svc_p99_s`。

> 口径必须在 Ch6 §metrics 里写死一句话，否则四道关卡的"数字关"无法核对：
> "End-to-end latency is measured from the client-side upload completion
> (`t_submit_utc`) to the DynamoDB `processed_at` timestamp; the service-side
> latency excludes S3 event delivery and starter cold start."

**同时修掉 `nan` 进表**：`latencies` 为空时不要输出 `nan`。

```python
def pct(values, q):
    if not values:
        sys.exit("[FAIL] 没有可计算的延迟样本：检查 D 是否写 processed_at")
    ...
```

---

## P2-3 坏文件随机混入 + 加 burst 对照

**现状**：`if i < n_invalid` 把 20 个坏文件全放在**前 12 秒**，与 Ch6 的 "concurrently with the happy path" 不符；1.7 rps 匀速提交，队列深度恒 0，"absorbs a burst" 无可支撑数据；Ch6 那句 "paced uniformly so that latency reflects queueing" 本身矛盾（不匀速才有排队）。

**改 `tests/load_test.py`**：

1) 随机混入（第 166–169 行）：

```python
            if invalid_pool and rng.random() < args.invalid_ratio:
                case, cat = rng.choice(invalid_pool), args.invalid_category
            else:
                case, cat = rng.choice(valid_pool), args.valid_category
```

2) 加 burst 档：

```python
    ap.add_argument("--profile", choices=["uniform", "burst"], default="uniform")
    ap.add_argument("--workers", type=int, default=16)
```

```python
    interval = 0.0 if args.profile == "burst" else args.duration / max(1, args.count)
    if args.profile == "burst":
        args.workers = max(args.workers, min(args.count, 100))
```

3) 日志里把真实并发说清楚（别让人以为 16 就是 16 并发）：

```python
    print(f"窗口 {args.duration}s，并发上限 {args.workers}，profile={args.profile}")
    print("[note] uniform 档是匀速铺开，峰值并发通常 1–3；要测冷启动并发请用 --profile burst")
```

> 改成按概率混入后，实际坏文件数会在 20 上下浮动（二项分布），不再恒为 20。
> 所以第 105 行那句 `计划提交 {n_valid} 个 ... + {n_invalid} 个` 要改成提交完再统计：
> `print(f"实际提交 normal={sum(1 for r in rows if r.category=='normal')} corrupted={sum(...)}")`。
> 报告里的分母用 `submitted.csv` 的实际计数，不要用计划值。

**跑法**（两轮正式压测之外，加一轮 burst 探索，不占 E6 的"两轮"名额）：

```bash
python tests/load_test.py --bucket <桶> --count 100 --duration 10 --profile burst \
    --out results/load_test_burst_submitted.csv
```

Ch6 里这组数据放 Discussion，写"峰值并发远超稳态，p99 从 X s 涨到 Y s，主要来自冷启动"——这才是评分表想看的分析。

---

## P2-4 接回 C 的 presign（消掉两份实现）

**现状**：E2 明确要求"调用 C 的 `presign.py` 获取 URL"，你自实现了一份，会漂移；且 PUT 没带 `Content-Type`/SSE 头，C 的桶策略若有要求就 403。

**改 `tests/load_test.py`**：加可选注入，C 交付后一行接上。

```python
    ap.add_argument("--presign-module", default=None,
                    help="C 的 presign 模块，如 security.presign；不填则用内置实现")
```

```python
    if args.presign_module:
        import importlib
        mod = importlib.import_module(args.presign_module)
        presign = mod.presign_put_url          # 按 C 的实际函数名改这一行
        print(f"[info] 使用 {args.presign_module} 生成预签名 URL")
    else:
        print("[warn] 内置 presign：C 的 security/presign.py 交付后请改用 --presign-module")
```

PUT 时补头（若 C 的桶策略要求 SSE）：

```python
            headers = {"Content-Type": "image/jpeg"}
            if args.sse:
                headers["x-amz-server-side-encryption"] = "AES256"
            code_id = requests.put(presign(id_key), data=body_id, headers=headers, timeout=15).status_code
```

---

## P3-1 Ch6：补 Alerting、拆掉预写结论、加引用

**现状三个问题**：
- 标题是 Performance Testing **and Monitoring**，但 E4 仪表盘、E5 告警在正文里没有任何落点——你 9 项任务里权重第二大的两块等于没写。
- 第 82–84 行已经写成结论（"In both rounds all valid applications reached a terminal verdict..."），而数据还没有。这条直接违反 §9.2 数字关。
- 全章 0 个 `\cite`。

**改 `report/sections/sec6_testing.tex`**：

1) 结果段改成占位（第 82–84 行）：

```latex
\subsection{Results}\label{sec:results}

Table~\ref{tab:loadtest} summarises two consecutive runs of the same workload.
% TODO(E) 11-25: 用下面模板填，禁止先写结论
% Round 1 processed X/80 valid packages and isolated Y/20 corrupted uploads;
% round 2 processed X'/80 and isolated Y'/20. {No | N} executions terminated in
% an unhandled state. Median latency was ... s (p50) and ... s (p99).
```

2) 新增 Alerting 小节（插在 `\subsection{Results}` 之前）：

```latex
\subsection{Alerting and Operational Response}\label{sec:alerting}

A dashboard is only useful if somebody is told when it turns red. Two alarms
were configured against the \texttt{vericloud-ops-alarm} topic
(Table~\ref{tab:alarms}), and both were exercised during the load test:
Fig.~\ref{fig:alarm} shows the notification that reached the operations inbox.

\begin{table}[htbp]
  \centering
  \small
  \caption{Operational alarms and their rationale.}
  \label{tab:alarms}
  \begin{tabular}{llll}
    \toprule
    Alarm & Condition & Period & Rationale \\
    \midrule
    Lambda errors & Errors $>$ 5 & 5 min & Worker or pre-check failures \\
    DLQ depth & Visible $>$ 0 & 5 min & A package was rejected for good \\
    \bottomrule
  \end{tabular}
\end{table}

% TODO(E) 11-20: 补一句"为什么不用单一阈值"——预检失败是预期业务结果，
% 单看 Errors 会在正常流量下反复触发，所以 DLQ depth 才是真正的隔离信号。

\begin{figure}[htbp]
  \centering
  \includegraphics[width=0.85\linewidth]{figures/fig_e_alarm.png}
  \caption{Alarm notification delivered to the operations inbox.}
  \label{fig:alarm}
\end{figure}
```

3) 参考文献（`references.bib` 末尾追加，正文 `\cite`）：

```bibtex
@misc{aws2024cloudwatch,
  author = {{Amazon Web Services}},
  title  = {Amazon {CloudWatch} User Guide: Metrics and Alarms},
  year   = {2024},
  howpublished = {\url{https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/}}
}
```

正文 §sec:metrics 开头加一句：

```latex
The metric families below follow the operational-visibility guidance of the
AWS Well-Architected Framework~\cite{aws2023security}; alarm thresholds are
derived from the failure taxonomy in Section~\ref{sec:fault}.
```

4) 补 testbed 参数（第 59 行的 TODO）：

```latex
All experiments ran in \texttt{us-east-1} on AWS Academy Learner Lab. The four
Lambdas use the Python 3.12 runtime with 1024\,MB of memory and a 60\,s timeout;
the state machine is a Standard workflow; the ingestion queue uses a 360\,s
visibility timeout, six times the 60\,s Lambda timeout, so that a message is
never retried while still being processed.
```

---

## P3-2 把 preflight 升格成"契约自检器"（你最容易加分的地方）

**现状**：`preflight.py:81-83` 读了 `RedrivePolicy` 却只用了 `depth`。而 §9.2 的"一致关"要核对的就是 **阈值 80 / 重试 3 次 / DLQ 14 天 / URL 5 分钟 / 桶私有** 这些硬指标——一个都没查。

在 `# 1) S3` 段后加：

```python
    # 1b) 桶的安全与生命周期（C 的职责，只有自检器能替他抓）
    s3 = session.client("s3")
    try:
        pab = s3.get_public_access_block(Bucket=args.bucket)["PublicAccessBlockConfiguration"]
        ok = all(pab.get(k) for k in ("BlockPublicAcls", "IgnorePublicAcls",
                                      "BlockPublicPolicy", "RestrictPublicBuckets"))
        record("桶阻止公开访问", ok, "四项全部开启" if ok else f"未全开：{pab}")
    except (BotoCoreError, ClientError) as exc:
        record("桶阻止公开访问", False, str(exc))

    try:
        enc = s3.get_bucket_encryption(Bucket=args.bucket)["ServerSideEncryptionConfiguration"]
        algo = enc["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
        record("桶默认加密", algo == "AES256", f"SSEAlgorithm={algo}")
    except (BotoCoreError, ClientError) as exc:
        record("桶默认加密", False, "未配置默认加密（应为 SSE-S3）")

    try:
        rules = s3.get_bucket_lifecycle_configuration(Bucket=args.bucket)["Rules"]
        days = [r.get("Expiration", {}).get("Days") for r in rules]
        record("raw/ 生命周期 7 天", 7 in days, f"expiration days={days}")
    except (BotoCoreError, ClientError) as exc:
        record("raw/ 生命周期 7 天", False, "未配置生命周期规则", blocking=False)
```

在 `# 3) SQS` 段里补红线校验（替换第 81–84 行那段）：

```python
            attrs = sqs.get_queue_attributes(
                QueueUrl=url,
                AttributeNames=["All"])["Attributes"]
            depth = attrs.get("ApproximateNumberOfMessages", "0")
            record(f"SQS {name}", True, f"depth={depth}")

            if name == args.dlq:
                keep = int(attrs.get("MessageRetentionPeriod", "0"))
                record("DLQ 保留 14 天", keep == 1209600, f"MessageRetentionPeriod={keep}")
            else:
                import json as _json
                redrive = _json.loads(attrs.get("RedrivePolicy", "{}"))
                mrc = redrive.get("maxReceiveCount")
                record("重试上限 3 次", str(mrc) == "3", f"maxReceiveCount={mrc}")
                record("可见性超时 >= 6x starter 超时", int(attrs.get("VisibilityTimeout", 0)) >= 360,
                       f"VisibilityTimeout={attrs.get('VisibilityTimeout')}", blocking=False)
```

在 `# 6) Lambda` 段里补运行时与规格：

```python
            cfg = lam.get_function(FunctionName=name)["Configuration"]
            ok = cfg.get("Runtime") == "python3.12"
            record(f"{name} 运行时", ok, cfg.get("Runtime", "?"), blocking=False)
            record(f"{name} 内存/超时", cfg.get("MemorySize", 0) >= 1024 and cfg.get("Timeout", 0) <= 60,
                   f"{cfg.get('MemorySize')}MB / {cfg.get('Timeout')}s", blocking=False)
```

在 `# 4) Step Functions` 里补类型：

```python
        record("状态机类型 STANDARD", desc["type"] == "STANDARD", f"type={desc['type']}", blocking=False)
```

这样 A6 联调时，你一条命令就能把 C/D 的配置红线全查出来，且"一致关"有据可依。**在群里发一次这个输出，你的角色价值立刻不一样。**

---

## P3-3 目录补齐

01 §12.4 要求 `figures/`；02 §1 要求 `tables/`。

```bash
cd ~/Desktop/kyc
mkdir -p figures tables screenshots
touch figures/.gitkeep tables/.gitkeep screenshots/.gitkeep
git add figures/.gitkeep tables/.gitkeep
```

`screenshots/` 已被 `.gitignore` 排除（截图放共享盘，01 §12.5），所以 `screenshots/.gitkeep` 不会被跟踪，属正常。

---

## 时间表（对齐 01 §六）

| 日期 | 做完哪些 |
|---|---|
| 11-06 今天 | P0-1 提交推送、P0-2、P0-3、P3-3；群里 @A 要共享盘位置与有效期格式确认 |
| 11-07 | P1-1、P1-2；收到 ≥2 人照片 → `--check` → 首批 5 组交 B |
| 11-08 | P1-3 打印拍摄 5 张；P1-4 sha256；首批 5 组正式交付 |
| 11-10 | 全量 27 例 + SHA256SUMS 上传共享盘，通知 B/C/D 校验 |
| 11-14 | P2-4 接 presign；P2-3 加 burst 档 |
| 11-18 | E4 仪表盘截图（顺手存 `docs/monitoring.md` 记下每个 widget 的指标与周期） |
| 11-20 | E5 告警 + 邮件截图；P3-2 preflight 升格，跑一次发群 |
| 11-21 | P2-1、P2-2 压测两轮 + 一轮 burst |
| 11-25 | 结果表 + `fig_e_latency.pdf`；P3-1 Ch6 填数、补 Alerting |
| 11-30 | Ch6 交 A |
| 12-01 | E8 复核 F 的成本数字 |

---

## 两个不要再犯的判断错误

1. **不要把"脚本写好"当成"任务完成"**。E1/E4/E5 的交付物是**素材、截图、邮件**，不是生成它们的脚本。状态板目前标 ✅ 的行里，有一半是"脚本已生成"，这不是交付。
2. **不要用一句 `[warn]` 掩盖阻塞**。`--dry-run` 假绿灯、`dlq_count or ...` 的兜底、`max(0, pending)` 的抹零，这三处都是在让脚本"看起来能跑"。数字关查的是原始 CSV 与报告是否一致，兜底逻辑最后都会变成报告里的假数字。
