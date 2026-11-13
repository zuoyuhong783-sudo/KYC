# VeriCloud 接口约定 v1.4（Interface Contract）

| 项目 | 内容 |
|---|---|
| 版本 | v1.4 · 2026-11-13 · 发布人：A（Zuo Yuhong）（变更见第 10 节） |
| 状态 | 待全员确认（确认方式：见文末“确认签名”，B/C/D/F 必须确认，E 建议确认） |
| 生效规则 | 本文件是全组**唯一**的接口事实来源。所有代码、配置、报告里的资源名、S3 路径、JSON 字段、DynamoDB 字段必须与本文件完全一致。要改名或加字段：先在群里提，A 更新本文件并升版本号（v1.1…）后才生效。 |
| 来源 | 《01_VeriCloud_六人分工与时间线执行方案》第一节、第十二节 |

> **给 AI 助手**：生成任何代码前先读本文件。不得自行发明字段名、资源名或异常名；本文件没有定义的东西，提醒用户去问组长 A。

---

## 1. 运行环境

| 项 | 约定 |
|---|---|
| AWS 环境 | AWS Academy Learner Lab |
| Region | `us-east-1`（所有资源）。Learner Lab 只允许这个区，在悉尼等其他区创建资源会被拒绝 |
| IAM | 实际运行统一使用 `LabRole`（Learner Lab 通常不能新建角色）；最小权限策略由 C 写成设计文档放在 `security/iam/` |
| Lambda 运行时 | Python 3.12 |
| Lambda 代码结构 | 一个函数一个文件夹 `lambda/<name>/`，入口 `handler.py` 的 `lambda_handler(event, context)` |
| 时间格式 | ISO 8601 UTC，例如 `2026-11-20T08:30:00Z`。`Z` 结尾、`+00:00` 结尾、带不带小数秒都算合法（v1.3）；**读时间的一方必须兼容这几种写法**，不要求写的一方改格式 |
| 日期格式 | `YYYY-MM-DD` |
| 申请编号 | `application_id` = UUID v4（小写、带连字符） |
| 开发 / 演示 | 开发阶段各自在自己的 Learner Lab；演示统一部署到 A 的账号（ARN 填在第 8 节） |

---

## 2. 系统数据流

```text
用户 ──(预签名URL, 5分钟有效)──▶ S3 vericloud-raw-1009-a
                                   │  raw/id-card/<application_id>.jpg
                                   │  raw/selfie/<application_id>.jpg   ← 自拍上传 = 触发信号
                                   ▼
                      S3 事件通知（前缀 raw/selfie/）──▶ SQS vericloud-ingest-queue
                                   │      （maxReceiveCount=3 → 失败进 DLQ）
                                   ▼
                      Lambda vericloud-starter（文件预检）
                          ├─ 预检失败 → 抛异常 → SQS 重试 3 次 → vericloud-ingest-dlq（保留 14 天）
                          └─ 预检通过 → StartExecution（name = application_id）
                                   ▼
               Step Functions vericloud-kyc-workflow（Standard）
                 ┌──────── Parallel ────────┐
                 ▼                          ▼
          Lambda vericloud-ocr       Lambda vericloud-face
                 └──────── 合并结果 ────────┘
                                   ▼
                           Choice 判定（第 6 节）
                                   ▼
                     DynamoDB PutItem → vericloud-kyc-table
                                   ▼
          DynamoDB Streams ──▶ Lambda vericloud-notify ──▶ SNS vericloud-kyc-topic ──▶ 邮件

  全程监控：CloudWatch 仪表盘 vericloud-dashboard；告警 → SNS vericloud-ops-alarm
```

**上传顺序约定**：客户端（压测脚本 / 将来的前端）必须**先上传证件照，再上传自拍**。只有自拍上传会触发流程；starter 会检查证件照是否已存在。

---

## 3. 资源命名

所有资源以 `vericloud-` 开头。

| 资源 | 名称 | 负责人 |
|---|---|---|
| S3 桶 | `vericloud-raw-1009-a`（v1.3.1 起的正式名；原名 `vericloud-raw-1009` 留在 C 的个人账号放人脸测试素材。桶名全球唯一，各人自己账号里测试时可加个人后缀，演示账号用此名） | C |
| S3 路径（证件） | `raw/id-card/<application_id>.jpg`（或 `.png`） | C |
| S3 路径（自拍） | `raw/selfie/<application_id>.jpg`（或 `.png`） | C |
| SQS 入口队列 | `vericloud-ingest-queue` | D |
| SQS 死信队列 | `vericloud-ingest-dlq` | D |
| Lambda | `vericloud-starter` | D |
| Lambda | `vericloud-ocr` | B |
| Lambda | `vericloud-face` | C |
| Lambda | `vericloud-notify` | F |
| Step Functions | `vericloud-kyc-workflow`（Standard 类型） | D |
| DynamoDB 表 | `vericloud-kyc-table` | F |
| SNS（申请人通知） | `vericloud-kyc-topic` | F |
| SNS（运维告警） | `vericloud-ops-alarm` | F 建，E 使用 |
| CloudWatch 仪表盘 | `vericloud-dashboard` | E |

**关键参数（报告与配置必须一致）**

| 参数 | 值 |
|---|---|
| 预签名 URL 有效期 | 300 秒（5 分钟） |
| 允许的图片格式 | `.jpg`、`.jpeg`、`.png` |
| SQS `maxReceiveCount` | 3 |
| DLQ 消息保留 | 14 天（1209600 秒） |
| 人脸相似度阈值 | 80（`similarity >= 80` 才算通过） |
| S3 生命周期 | `raw/` 前缀对象 7 天后删除 |

---

## 4. DynamoDB 表结构：`vericloud-kyc-table`

- 分区键：`application_id`（String）；无排序键
- 容量模式：按需（On-Demand）
- Streams：开启，`NEW_AND_OLD_IMAGES`

| 字段 | 类型 | 必有 | 说明 | 写入来源 |
|---|---|---|---|---|
| `application_id` | S | 是 | UUID v4 | 上传时生成，starter 传入 |
| `created_at` | S | 是 | 提交时间（ISO 8601 UTC），取自 S3 事件的 `eventTime` | starter 传入 |
| `received_at` | S | 是（v1.3） | starter 开始处理这条 SQS 消息的时间（ISO 8601 UTC） | starter 传入 |
| `processed_at` | S | 是 | 写库时间（ISO 8601 UTC） | 状态机 |
| `name` | S | OCR 成功时 | 姓名 | OCR |
| `id_number_masked` | S | OCR 成功时 | 证件号脱敏，只保留后 4 位，例：`**************1234` | OCR |
| `expiry_date` | S | OCR 成功时 | `YYYY-MM-DD` | OCR |
| `issuing_authority` | S | OCR 成功时 | 发证机关 | OCR |
| `id_valid` | BOOL | OCR 成功时 | 证件是否在有效期内（`expiry_date >= 今天`） | OCR |
| `similarity` | N | 比脸成功时 | 0–100，保留 2 位小数 | Face |
| `face_error` | S | 比脸失败时 | 异常名，如 `FaceNotDetectedError` | 状态机 Catch |
| `review_status` | S | 是 | `PASS` / `NEEDS_HUMAN_REVIEW` / `FAIL` | 状态机 Choice |
| `reason` | S | 是 | 见第 6 节的取值 | 状态机 Choice |

**禁止写入**：完整证件号、图片二进制、预签名 URL。

---

## 5. 各模块输入 / 输出 JSON

### 5.1 状态机输入（`vericloud-starter` → `vericloud-kyc-workflow`）

```json
{
  "application_id": "3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b",
  "bucket": "vericloud-raw-1009-a",
  "id_card_key": "raw/id-card/3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b.jpg",
  "selfie_key": "raw/selfie/3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b.jpg",
  "created_at": "2026-11-20T08:30:00Z",
  "received_at": "2026-11-20T08:30:04.512+00:00"
}
```

`vericloud-ocr` 和 `vericloud-face` 的输入都是上面这个对象**原样**（它们只检查自己需要的字段，多出的字段忽略）。

- `created_at`：S3 上传完成时间（S3 事件 `eventTime`）。
- `received_at`（v1.3）：starter 开始处理这条消息时的 UTC 时间。`created_at → received_at` = 投递 + 排队 + 冷启动；`received_at → processed_at` = 流水线处理时间（E 的延迟统计口径）。状态机须把它原样写入 DynamoDB。

### 5.2 `vericloud-starter` 预检规则（D）

输入：SQS 消息（body 为 S3 事件通知）。从自拍的 key 中取 `application_id`，然后检查：

1. 证件照和自拍两个对象都存在（证件照可能是 `.jpg` / `.jpeg` / `.png` 任一种）
2. 两个文件都不是 0 字节
3. 扩展名在允许列表中
4. 两张图都能被 PIL **完整解码**：`Image.open(...)` 后调用 `.load()` 不报错（v1.3；不要设置 `ImageFile.LOAD_TRUNCATED_IMAGES = True`）。只用 `verify()` 会放过截断的 JPEG；也不要用「文件结尾是不是 `FF D9`」判断，会误杀尾部带附加数据的正常手机照片

任一不满足：抛 `PrecheckFailedError`（消息写明原因）→ SQS 重试，3 次后进 DLQ。全部满足：`start_execution(name=application_id, input=<5.1 的 JSON>)`；若报 `ExecutionAlreadyExists`，视为成功（防重复）。

### 5.3 `vericloud-ocr` 输出（B）

```json
{
  "name": "ZHANG SAN",
  "id_number_masked": "**************1234",
  "expiry_date": "2030-05-01",
  "issuing_authority": "XX Public Security Bureau",
  "id_valid": true
}
```

失败：抛 `OcrExtractionError`（消息写明哪个字段没识别出来）。

**`issuing_authority` 不得含 8 位以上连续数字（v1.3）**：防止卡面同一行的证件编号被一起识别进来、导致完整证件号外泄。具体剥离方式由 B 实现。

**有效期为「长期」（v1.2）**：证件上有效期写「长期 / 長期」时，`expiry_date` 固定填 `"9999-12-31"`，`id_valid` 为 `true`，**不抛异常**。下游（D 的 Choice、F 的表和邮件）把 `9999-12-31` 当作「长期有效」处理即可；报告和演示中如需展示，写作「长期」。

### 5.4 `vericloud-face` 输出（C）

```json
{ "similarity": 92.37, "face_matched": true }
```

- 调用：`rekognition.compare_faces(SourceImage=自拍, TargetImage=证件照, SimilarityThreshold=0)`，取最高 `Similarity`
- `face_matched` = `similarity >= 80`
- 失败：图中没有人脸 / 太模糊 → 抛 `FaceNotDetectedError`；其他错误 → 抛 `FaceCompareError`

### 5.5 Parallel 合并后的状态（D）

正常情况：

```json
{
  "application_id": "3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b",
  "bucket": "vericloud-raw-1009-a",
  "id_card_key": "raw/id-card/3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b.jpg",
  "selfie_key": "raw/selfie/3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b.jpg",
  "created_at": "2026-11-20T08:30:00Z",
  "received_at": "2026-11-20T08:30:04.512+00:00",
  "ocr": {
    "name": "ZHANG SAN",
    "id_number_masked": "**************1234",
    "expiry_date": "2030-05-01",
    "issuing_authority": "XX Public Security Bureau",
    "id_valid": true
  },
  "face": { "similarity": 92.37, "face_matched": true }
}
```

比脸失败时，`face` 变为：

```json
"face": { "face_error": "FaceNotDetectedError" }
```

OCR 失败时，`ocr` 变为：

```json
"ocr": { "ocr_error": "OcrExtractionError" }
```

路径约定：OCR 结果在 `$.ocr`，比脸结果在 `$.face`。分支失败时由 Catch 写入 `$.ocr.ocr_error` 或 `$.face.face_error`，**不中断整个流程**。

### 5.6 `vericloud-notify` 发出的 SNS 消息（F）

触发条件：DynamoDB Stream 中 `review_status` 新增或发生变化。

```json
{
  "application_id": "3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b",
  "review_status": "PASS",
  "reason": "auto_approved",
  "processed_at": "2026-11-20T08:30:41Z"
}
```

邮件主题：`[VeriCloud] Application <application_id 前 8 位>: <review_status>`。邮件中**不得**出现姓名、证件号。

---

### 5.7 前端接口 `vericloud-api`（v1.4，A）

浏览器只通过这两个接口和后端打交道，不持有 AWS 密钥，也不直接访问 DynamoDB。

| 请求 | 输入 | 输出 |
|---|---|---|
| `POST /applications` | `{"application_id", "id_card_extension", "selfie_extension"}`（小写 UUID v4；扩展名 `.jpg`/`.jpeg`/`.png`） | `200 {"application_id", "id_card_url", "selfie_url", "expires_in": 300}`；参数错 `400`；编号已用过 `409` |
| `GET /applications/<application_id>` | — | 完成：`200 {"review_status", "reason", "processed_at"}`；处理中：`404 {"status": "PENDING"}` |

只返回这三个字段，**不返回**姓名、证件号。前端先 PUT 证件照，再 PUT 自拍（第 2 节）。部署：`infrastructure/setup_api.sh`（API Gateway HTTP API + S3 CORS）。

---

## 6. 判定规则（D 的 Choice 状态，按顺序匹配，命中即停）

| 顺序 | 条件 | `review_status` | `reason` |
|---|---|---|---|
| 1 | `$.ocr.ocr_error` 存在 | `FAIL` | `ocr_failed` |
| 2 | `$.ocr.id_valid == false` | `FAIL` | `id_expired` |
| 3 | `$.face.face_error` 存在 | `NEEDS_HUMAN_REVIEW` | `face_error` |
| 4 | `$.face.similarity < 80` | `NEEDS_HUMAN_REVIEW` | `similarity_below_80` |
| 5 | 其他 | `PASS` | `auto_approved` |

文件损坏 / 0 字节 / 格式不支持的申请**不会进入状态机**，也不会写入 DynamoDB，只会出现在 DLQ 中。

---

## 7. 异常名汇总

| 异常名 | 抛出方 | 谁接住 | 结果 |
|---|---|---|---|
| `PrecheckFailedError` | starter（D） | SQS 重试机制 | 3 次后进 DLQ |
| `OcrExtractionError` | ocr（B） | 状态机 Catch | `FAIL` / `ocr_failed` |
| `FaceNotDetectedError` | face（C） | 状态机 Catch | `NEEDS_HUMAN_REVIEW` / `face_error` |
| `FaceCompareError` | face（C） | 状态机 Catch | `NEEDS_HUMAN_REVIEW` / `face_error` |

在 Python 中这样定义（类名即 Step Functions 中的 `ErrorEquals`）：

```python
class OcrExtractionError(Exception):
    pass
```

---

## 8. 部署信息（演示账号，由各 owner 部署后填写）

| 资源 | ARN / 名称 | 填写人 | 日期 |
|---|---|---|---|
| S3 桶名 | `vericloud-raw-1009-a`（`1009` 为组长学号 5561009 后 4 位；v1.3.1 加 `-a`） | A 确认 | 2026-11-10 |
| SQS 入口队列 URL |`https://sqs.us-east-1.amazonaws.com/493114794251/vericloud-ingest-queue`| D | 2026-11-08 |
| SQS DLQ ARN | `arn:aws:sqs:us-east-1:493114794251:vericloud-ingest-dlq`| D | 2026-11-08 |
| `vericloud-starter` ARN |`arn:aws:lambda:us-east-1:493114794251:function:vericloud-starter` | D | 2026-11-08 |
| `vericloud-ocr` ARN | `arn:aws:lambda:us-east-1:494345913252:function:vericloud-ocr`（**个人 Lab ARN**，统一演示账号部署后更新） | B | 2026-11-08 |
| `vericloud-face` ARN | `arn:aws:lambda:us-east-1:350325240468:function:vericloud-face` | C | 2026-11-06 |
| `vericloud-notify` ARN | `arn:aws:lambda:us-east-1:099702382348:function:vericloud-notify` | F | 2026-11-10 |
| `vericloud-kyc-workflow` ARN | `arn:aws:states:us-east-1:493114794251:stateMachine:vericloud-kyc-workflow`| D | 2026-11-08 |
| `vericloud-kyc-table` Stream ARN | `arn:aws:dynamodb:us-east-1:099702382348:table/vericloud-kyc-table/stream/2026-11-10T08:44:28.506` | F | 2026-11-10 |
| `vericloud-kyc-topic` ARN | `arn:aws:sns:us-east-1:099702382348:vericloud-kyc-topic` | F | 2026-11-10 |
| `vericloud-ops-alarm` ARN | `arn:aws:sns:us-east-1:099702382348:vericloud-ops-alarm` | F | 2026-11-10 |

### 8.1 统一演示账号（A 的 Learner Lab，账号 `153547984638`）

上表中带个人账号 ID 的 ARN 是各 owner 自测用的；联调（A6，11-12 起）时逐项部署到下面这个账号，并在此表补齐。

| 资源 | ARN / 名称 | 填写人 | 日期 |
|---|---|---|---|
| S3 桶 | `vericloud-raw-1009-a`（正式名，v1.3.1） | A | 2026-11-10 |
| S3 事件通知 | `raw/selfie/` 前缀 `ObjectCreated:*` → `vericloud-ingest-queue`（A5 已验证：上传后队列收到消息） | A | 2026-11-09 |
| SQS 入口队列 URL | `https://sqs.us-east-1.amazonaws.com/153547984638/vericloud-ingest-queue` | A | 2026-11-09 |
| SQS DLQ ARN | `arn:aws:sqs:us-east-1:153547984638:vericloud-ingest-dlq` | A | 2026-11-09 |
| `vericloud-starter` / `-ocr` / `-face` / `-notify`、状态机、DynamoDB、SNS | 待 A6 部署 | | |

**注意**：这里只填 ARN 和名称，**不要**填 Access Key、Secret Key、Session Token 或任何密码。

---

## 9. 测试素材约定（E）

| 项 | 约定 |
|---|---|
| 位置 | 清单与生成脚本在 `tests/fixtures/`；**图片不进 git**，放在 A 指定的共享盘目录（11-11 M1 会上定），以 `SHA256SUMS` 校验 |
| 清单 | `tests/fixtures/manifest.csv`，列：`case_id, id_card_file, selfie_file, category, expected_status, expected_reason`（v1.3 加最后一列） |
| `category` 取值 | `normal`、`different_person`、`zero_byte`、`wrong_format`、`blurry`、`no_face`、`expired`、`missing_field`（v1.3 加后两类，共 27 例） |
| `expected_reason` | 取第 6 节的 `reason`；DLQ 用例填 `-`；可接受多个时用 `\|` 分隔（`blurry` 写 `face_error\|similarity_below_80`，模糊自拍可能检不到脸，也可能只是相似度不足） |
| 覆盖 | `PASS`（normal）、`NEEDS_HUMAN_REVIEW`（different_person / blurry / no_face）、`FAIL`（expired → `id_expired`，missing_field → `ocr_failed`）、`DLQ`（zero_byte / wrong_format） |
| 隐私 | 只用组员本人或自制样例证件，**禁止使用他人真实证件** |

---

## 10. 变更记录

| 版本 | 日期 | 修改人 | 内容 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A | 首次发布 |
| v1.1 | 2026-11-06 | A | S3 桶名后缀定为 `1009`（桶名 `vericloud-raw-1009`）；注明 Learner Lab 只允许 `us-east-1`（悉尼等其他区建资源会被拒绝） |
| v1.2 | 2026-11-08 | A | 5.3：有效期「长期」统一输出 `expiry_date = "9999-12-31"`、`id_valid = true`，不再抛 `OcrExtractionError`（应 B 提问确认） |
| v1.3 | 2026-11-10 | A | 采纳 E 的变更申请（评审见 `docs/review_A_on_E_proposal_v1.3.md`）：§1 时间格式兼容 `Z`/`+00:00`/小数秒；§4、§5.1 加 `received_at`；§5.2 预检改为完整解码 `load()`；§5.3 `issuing_authority` 不得含 8 位以上连续数字；§9 加 `expired`/`missing_field` 两类与 `expected_reason` 列，图片不进 git。D 的 starter 与 E 的脚本已按此实现；B 的 §5.3 和 D 状态机写入 `received_at` 在 A6 联调时完成 |
| v1.3.1 | 2026-11-10 | A | §3 正式桶名改为 `vericloud-raw-1009-a`（原名留在 C 的个人账号作人脸测试素材，不再要求删除）；同步 §2、§5.1、§5.5、§8 的桶名。各模块代码从 S3 事件或命令行参数读桶名，不用改；只有 C 的 `security/presign.py` 写死了默认桶名，已由 A 代改 |
| v1.4 | 2026-11-13 | A | 新增 §5.7 前端接口 `vericloud-api`（申请上传地址、查询结果），接入组内前端 `frontend/`；只新增，不改已有字段 |

---

## 11. 确认签名

读完后，在群里回复“已读接口约定 v1.0”，再由 A 在下表打勾（或本人提 PR 打勾）。

| 角色 | 成员 | 负责的接口 | 已确认 |
|---|---|---|---|
| A | Zuo Yuhong | 全文、S3 事件通知 | ☑ |
| B | 李东翰 | 5.3、7 | ☑（v1.2） |
| C | 胡同学 | 3（S3）、5.4、7 | ☑ |
| D | 苏昶玮 | 3（SQS/状态机）、5.1、5.2、5.5、6、7 | ☑ |
| E | Li Hengchen | 2（上传顺序）、9 | ☐ |
| F | 杨雪俪 | 4、5.6 | ☑ |
