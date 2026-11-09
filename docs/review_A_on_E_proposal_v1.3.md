# A 对 E 接口变更提案（v1.2 → v1.3）的评审意见

| 项目 | 内容 |
|---|---|
| 评审对象 | `docs/interface_change_proposal_E.md`（2026-11-09 版）及 E 的相关文件 |
| 评审人 | A（Zuo Yuhong） |
| 日期 | 2026-11-09 |
| 结论 | 4 条中 **3 条同意，1 条（§5.2）同意问题、改用别的方案** |
| 生效方式 | `docs/interface.md` 由 **A 统一升到 v1.3**，E 不直接改 interface.md |

> **给 E 的 AI 的说明**：本文件是组长的评审结论，请据此修改 E 自己负责的文件（第 3 节清单）。
> 只改 E 的文件：`tests/`、`docs/e_*.md`、`docs/interface_change_proposal_E.md`、`report/sections/sec6_testing.tex`。
> **不要改** `docs/interface.md`、`lambda/`（B/C/D 的代码）、`infrastructure/`、`security/`。
> 改完按第 4 节自检，提交信息以 `[E]` 开头。

---

## 1. 逐条结论

### 第 1 条：§9 增加 `expired`、`missing_field` 两类，清单增加 `expected_reason` 列：✅ 同意

- 两类各 2 例，共 27 例；`expected_reason` 取值与 interface §6 的 `reason` 一致（`auto_approved`、`similarity_below_80`、`face_error`、`id_expired`、`ocr_failed`），DLQ 用例填 `-`。✅ 现在的 `manifest.csv` 已符合。
- **需要补一处**：`blurry` 两例目前写 `expected_reason = face_error`。模糊自拍时，Rekognition 也可能**仍检测到人脸、只是相似度低于 80**，于是走 `similarity_below_80`。两种都是 `NEEDS_HUMAN_REVIEW`，都算正确。
  - 请改为：`blurry` 的 `expected_reason` 写 `face_error|similarity_below_80`（竖线表示"任一即可"）。
  - `collect_results.py` 比较 `reason_match` 时，按 `|` 拆分后任一命中即算符合。
  - `tests/fixtures/README.md` 和 Ch6 的用例表同步说明这一点。

### 第 2 条：§5.1 增加 `received_at`：✅ 同意

- 定义：starter **通过预检之后、调用 `start_execution` 之前**取当前 UTC 时间，ISO 8601，格式同 `created_at`（例：`2026-11-20T08:30:04Z`）。
- 已核实：B 的 `lambda/ocr/handler.py` 和 C 的 `lambda/face/handler.py` 只检查必需字段、**不拒绝多出来的字段**，加字段不会让它们报错。
- D 需要在 starter 里加这一行，并让状态机把它写进 DynamoDB（§4 表结构由 A 在 v1.3 里同步加 `received_at` 一行）。
- E 侧现有的"缺 `received_at` 时退回 `created_at` 并告警"的兜底逻辑**保留**。

### 第 3 条：§5.2 预检补完整性判定：⚠️ 问题属实，**方案改为"完整解码"，不用 EOI/IEND 尾部判断**

A 已在本地复现（Pillow 13，400×300 随机灰度图，JPEG 质量 90，全长 96 571 B；PNG 全长 308 492 B）：

| 输入 | 现行 `open()+verify()` | E 提案（看尾部 FF D9 / IEND） | **采用：`open()+load()`** |
|---|---|---|---|
| JPEG 截断到 600 B | 拦下 | 拦下 | 拦下 |
| **JPEG 截断到 2000 B** | **放过（漏）** | 拦下 | **拦下** |
| **JPEG 截断一半** | **放过（漏）** | 拦下 | **拦下** |
| JPEG 完整 | 通过 | 通过 | 通过 |
| **JPEG 完整 + 尾部附加数据** | 通过 | **误拦（错杀正常照片）** | **通过** |
| PNG 截断 600 B / 2000 B / 一半 | 拦下 | 拦下 | 拦下 |
| PNG 完整 | 通过 | 通过 | 通过 |

- 结论：E 发现的漏洞是真的，`wrong_format_04` 现在确实会漏过预检。
- 但"看结尾是不是 FF D9"会**误杀正常照片**：不少手机会在 JPEG 的 FF D9 之后附加数据（动态照片、厂商元数据等）。E 的 `complete_ok()` 只看最后 64 字节，附加数据一长就判为不完整。
- 采用的规则（v1.3 §5.2 第 4 条改写）：
  > 4. 两张图都能被 PIL **完整解码**：`Image.open(...)` 后调用 `.load()` 不报错（不要设置 `ImageFile.LOAD_TRUNCATED_IMAGES = True`）。截断、损坏的文件按 `PrecheckFailedError` 处理。
- D 的改动：starter 里 `image.verify()` 改为 `image.load()`，只改一行（A 另行通知 D）。

### 第 4 条：§5.3 `issuing_authority` 剥离卡底编号：✅ 同意方向，由 B 决定怎么实现

- 防止完整证件号混进 `issuing_authority` 是合理的保险，属于 B 的 OCR 实现细节，优先级低于前 3 条。
- A 会把要求写进 v1.3 §5.3："`issuing_authority` 中不得出现 8 位以上连续数字"。具体正则由 B 定，E 的提案代码仅作参考。

---

## 2. 不在提案里、但请 E 一并处理的

1. **`docs/e_delivery_status.md` 第五节已过时**：写着"push 未完成"，实际 6 个提交都已在 `origin/main`。请更新。另外文件里那条带 `<PAT>` 的 push 命令请删掉：不要在仓库里教别人把令牌拼进 URL。
2. **素材照片**（阻塞清单第 1 项）：由 A 在 11-11 M1 会上协调谁提供自拍、放在哪个共享盘目录。E 先不用等，可以先用 `gen_fixtures.py` 生成**不需要真人照片**的部分（坏文件、过期、缺字段的证件图）。
3. `docs/e_upload_checklist.md` 第 30 行写着"待 §9 升 v1.1 后补用例"，版本号写错了，应为 v1.3。

---

## 3. E 需要修改的文件清单

| 文件 | 改什么 |
|---|---|
| `tests/check_precheck.py` | `contract` 口径改为 `Image.open(...).load()` 能否成功，删掉 / 不再使用 `complete_ok()` 的尾部判断。正常件自检也改用 `load()`。说明文字与退出提示改为"完整解码"。**建议**再加一个用例：完整 JPEG + 尾部附加数据，必须判为"通过" |
| `tests/fixtures/manifest.csv` | `blurry_01`、`blurry_02` 的 `expected_reason` 改为 `face_error\|similarity_below_80` |
| `tests/collect_results.py` | `reason_match`：`expected_reason` 按 `\|` 拆分，任一命中即符合；`-`（DLQ）不参与比较 |
| `tests/fixtures/README.md` | §7"待 A 批准"改为"已按 A 评审意见执行，待 interface v1.3 发布"。说明 blurry 的双 reason 和"完整解码"规则 |
| `docs/interface_change_proposal_E.md` | 状态改为"A 已评审（见 `docs/review_A_on_E_proposal_v1.3.md`）"。第 3 条的方案改为 `load()`，保留原因说明 |
| `docs/e_delivery_status.md` | 见第 2 节第 1、2 点 |
| `docs/e_upload_checklist.md` | 版本号 v1.1 改为 v1.3 |
| `report/sections/sec6_testing.tex` | 预检描述改为"full decode"。用例表：blurry 的 reason 写两种都可接受。如有提到 EOI/IEND 的地方，一并改掉 |

---

## 4. 改完自检

```bash
# 1) 预检自检：wrong_format_04 在 contract 口径下应为"拦下"；附加尾部数据的完整 JPEG 应为"通过"
python tests/check_precheck.py

# 2) 全文不应再把 EOI/IEND 当作采用的方案（说明"为什么不用"的段落可以保留）
git grep -n "EOI\|IEND\|FF D9" -- tests docs/e_*.md report/sections/sec6_testing.tex

# 3) 清单仍是 27 行用例 + 1 行表头、6 列
python -c "import csv;r=list(csv.reader(open('tests/fixtures/manifest.csv',encoding='utf-8')));print(len(r)-1, set(map(len,r)))"
```

预期输出：第 1 条退出码 0；第 3 条打印 `27 {6}`。

---

## 5. 之后谁做什么

| 谁 | 做什么 | 何时 |
|---|---|---|
| E | 按第 3 节修改并推送 | 11-10 |
| A | 发布 `interface.md` v1.3（§4 加 `received_at`、§5.1、§5.2 第 4 条、§5.3、§9），通知 B / D | E 推送后 |
| D | starter：`verify()` 改 `load()`；加 `received_at`；状态机写入 DynamoDB | v1.3 发布后 |
| B | `issuing_authority` 不含 8 位以上连续数字 | v1.3 发布后，优先级低 |
| A | M1 会上定：自拍照提供人 + 共享盘目录 | 11-11 |
