# E9：答辩讲稿（2 分钟）与 2 页幻灯

> 负责人：Li Hengchen（E）｜交付对象：A（合并进 PPT）
> 依据：01 方案 §10（答辩分工：E 讲"压测与监控结果"，约 2′）
> 状态：草稿。所有 `【XX】` 必须用 `results/load_test_r*_summary.csv` 的真实数字替换后才能上台。

---

## 1. 讲稿（英文，约 260 词 ≈ 2 分钟）

> **【Slide 1】Results at a glance**

"We tested the pipeline the way a bank would: one hundred applications in sixty
seconds, with twenty percent deliberately broken files mixed into the same window,
because a real onboarding queue never gives you a clean stream.

All 【XX】 valid packages reached a terminal verdict, and all 【XX】 corrupted
uploads were isolated in the dead-letter queue — and I can prove each one
individually, not just by a queue counter: every corrupted application ID was
matched against the messages actually sitting in the DLQ.

For latency we report two clocks. Service latency, from the pre-check function to
the database write, was 【XX】 seconds at p50 and 【XX】 at p99. End-to-end, from
the user's upload finishing to the record appearing, was 【XX】 at p50 and 【XX】
at p99. The gap between the two is the S3 event delivery and the cold start of
the first function — exactly the part a user feels and a service metric hides.

The dashboard in front of you was captured during that run: concurrency ramps up,
queue depth spikes and drains, and the dead-letter queue stays flat until the
corrupted files exhaust their retries."

> **【Slide 2】What broke, and what we learned**

"Two things surprised us. First, p99 is 【XX】 times p50. The tail is not random:
it is cold starts on the OCR function, which loads a fairly heavy model on first
invocation. Second, the DLQ alarm fired during the test — by design, because
broken files are supposed to be rejected. That is why we alarm on queue depth
rather than on error count alone; an error alarm would have been ringing the whole
time and everyone would have learned to ignore it.

The honest limitation is sample size: with one hundred packages, p99 is decided by
a single request. We report p50 and p95 next to it for that reason, and we do not
claim more precision than the data supports."

**收尾一句（交给 A）**："That's the performance picture — A will now walk through the demo."

---

## 2. 两页幻灯内容

### Slide 1 — "100 applications in 60 s: what held, what bent"

| 元素 | 内容 |
|---|---|
| 大数字（3 个） | `【XX】/80` valid processed · `【XX】/20` corrupted isolated · `【XX】` unhandled crashes |
| 图 | `figures/fig_e_dashboard.png`（整屏仪表盘，裁掉账号信息） |
| 一行小字 | "p50 【XX】s · p95 【XX】s · p99 【XX】s (end-to-end)" |

### Slide 2 — "The tail is cold start, not load"

| 元素 | 内容 |
|---|---|
| 图 | `figures/fig_e_latency.pdf`（延迟分布直方图或 CDF） |
| 标注 | 在尾部标一个箭头："cold start of vericloud-ocr" |
| 一句结论 | "Alarm on DLQ depth, not error count — broken files are expected traffic." |

---

## 3. 预期提问（准备到能脱口而出）

| # | 问题 | 要点 |
|---|---|---|
| 1 | 只测 100 个，凭什么说能扛 10 倍高峰？ | 单请求资源模型 + 并发自动扩展 + SQS 削峰；**承认**未做 1000 级压测是局限，burst 档是补充证据 |
| 2 | p99 为什么这么高？ | 冷启动（模型加载）+ 队列排队；用 burst vs uniform 两组数据对比说明 |
| 3 | 坏文件怎么保证没漏？ | 不是看队列计数，是按 `application_id` 与 DLQ 消息体逐条比对，`【XX】/20` |
| 4 | 监控指标为什么选这四个？ | 对应四类失败模式：不扩、慢、错、堵；引用 Well-Architected |

---

## 4. 上台前检查

- [ ] `【XX】` 全部替换为 `results/` 里的真实数字（禁止口算）
- [ ] 两张图已放进 `figures/`，文件名为 `fig_e_*`
- [ ] 幻灯片 2 页、总时长 ≤ 2′（对着计时器念两遍）
- [ ] 演示电脑上备份一份 PDF，防止 Overleaf/PPT 打不开
