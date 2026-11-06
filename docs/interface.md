# VeriCloud 接口约定 v1.0（Interface Contract）

| 项目 | 内容 |
|---|---|
| 版本 | v1.1 · 2026-11-06 · 发布人：A（Zuo Yuhong）（变更见第 10 节） |
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
| 时间格式 | ISO 8601 UTC，例如 `2026-11-20T08:30:00Z` |
| 日期格式 | `YYYY-MM-DD` |
| 申请编号 | `application_id` = UUID v4（小写、带连字符） |
| 开发 / 演示 | 开发阶段各自在自己的 Learner Lab；演示统一部署到 A 的账号（ARN 填在第 8 节） |

---

## 2. 系统数据流

```text
用户 ──(预签名URL, 5分钟有效)──▶ S3 vericloud-raw-1009
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
| S3 桶 | `vericloud-raw-1009`（v1.1 确认；桶名全球唯一，各人自己账号里测试时如被占用，可临时加个人后缀，演示账号必须用此名） | C |
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
| `created_at` | S | 是 | 提交时间（ISO 8601 UTC） | starter 传入 |
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
  "bucket": "vericloud-raw-xxxx",
  "id_card_key": "raw/id-card/3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b.jpg",
  "selfie_key": "raw/selfie/3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b.jpg",
  "created_at": "2026-11-20T08:30:00Z"
}
```

`vericloud-ocr` 和 `vericloud-face` 的输入都是上面这个对象**原样**。

### 5.2 `vericloud-starter` 预检规则（D）

输入：SQS 消息（body 为 S3 事件通知）。从自拍的 key 中取 `application_id`，然后检查：

1. 证件照和自拍两个对象都存在（证件照可能是 `.jpg` / `.jpeg` / `.png` 任一种）
2. 两个文件都不是 0 字节
3. 扩展名在允许列表中
4. 两张图都能被 `PIL.Image.open()` 打开

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
  "bucket": "vericloud-raw-xxxx",
  "id_card_key": "raw/id-card/3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b.jpg",
  "selfie_key": "raw/selfie/3f2b7c1e-8a4d-4f2e-9b1a-1c2d3e4f5a6b.jpg",
  "created_at": "2026-11-20T08:30:00Z",
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
| S3 桶名后缀 | `vericloud-raw-1009`（组长学号 5561009 后 4 位） | A 确认 | 2026-11-06 |
| SQS 入口队列 URL | | D | |
| SQS DLQ ARN | | D | |
| `vericloud-starter` ARN | | D | |
| `vericloud-ocr` ARN | | B | |
| `vericloud-face` ARN | | C | |
| `vericloud-notify` ARN | | F | |
| `vericloud-kyc-workflow` ARN | | D | |
| `vericloud-kyc-table` Stream ARN | | F | |
| `vericloud-kyc-topic` ARN | | F | |
| `vericloud-ops-alarm` ARN | | F | |

**注意**：这里只填 ARN 和名称，**不要**填 Access Key、Secret Key、Session Token 或任何密码。

---

## 9. 测试素材约定（E）

| 项 | 约定 |
|---|---|
| 位置 | `tests/fixtures/` |
| 清单 | `tests/fixtures/manifest.csv`，列：`case_id, id_card_file, selfie_file, category, expected_status` |
| `category` 取值 | `normal`、`different_person`、`zero_byte`、`wrong_format`、`blurry`、`no_face` |
| 隐私 | 只用组员本人或自制样例证件，**禁止使用他人真实证件** |

---

## 10. 变更记录

| 版本 | 日期 | 修改人 | 内容 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A | 首次发布 |
| v1.1 | 2026-11-06 | A | S3 桶名后缀定为 `1009`（桶名 `vericloud-raw-1009`）；注明 Learner Lab 只允许 `us-east-1`（悉尼等其他区建资源会被拒绝） |

---

## 11. 确认签名

读完后，在群里回复“已读接口约定 v1.0”，再由 A 在下表打勾（或本人提 PR 打勾）。

| 角色 | 成员 | 负责的接口 | 已确认 |
|---|---|---|---|
| A | Zuo Yuhong | 全文、S3 事件通知 | ☑ |
| B | 李东翰 | 5.3、7 | ☐ |
| C | 胡同学 | 3（S3）、5.4、7 | ☐ |
| D | 苏昶玮 | 3（SQS/状态机）、5.1、5.2、5.5、6、7 | ☐ |
| E | Li Hengchen | 2（上传顺序）、9 | ☐ |
| F | 杨雪俪 | 4、5.6 | ☐ |
