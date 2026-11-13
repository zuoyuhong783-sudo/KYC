# `security/iam/` — 最小权限设计（C6）

**Owner:** C · Hu Zhongyuan · 2026-11-13

每份文件对应一个执行角色的设计文档：**只授予该角色在数据流中实际调用的
API，资源钉到具体桶 / 前缀 / 队列 / 主题 / 函数 ARN**。取值对准
`docs/interface.md` v1.3.1 **§8.1 统一演示账号 `153547984638`**（正式桶
`vericloud-raw-1009-a`）；§8 上表各人个人 Lab 账号的 ARN 仅自测用，不入策略。

## 权限矩阵

| 策略文件 | 角色 | 关键权限 | 资源 |
|---|---|---|---|
| `vericloud-starter-policy.json` | starter 函数 | `s3:GetObject/HeadObject`（预检）、`sqs:Receive/Delete/GetAttributes`（消费队列）、`states:StartExecution`（启状态机） | 桶 raw/ 两前缀、ingest-queue、kyc-workflow |
| `vericloud-ocr-policy.json` | ocr 函数 | `s3:GetObject` | 桶 raw/ 两前缀 |
| `vericloud-face-policy.json` | face 函数 | `rekognition:CompareFaces`、`s3:GetObject` | 见下「例外 A」、桶 raw/ 两前缀 |
| `vericloud-notify-policy.json` | notify 函数 | `dynamodb:DescribeStream/GetRecords/GetShardIterator`、`sns:Publish` | 表 stream、kyc-topic |
| `vericloud-workflow-policy.json` | 状态机 | `lambda:InvokeFunction` ×2 | 仅 ocr + face 两个函数 ARN |

设计要点（报告 5.1 素材）：

- **读写分离**：管道前段（starter/ocr/face）对桶只有 GetObject——没有任何
  角色能写或删用户上传的原图，写入只经预签名 URL 由用户侧发生；
- **横向隔离**：face 的策略里没有 SQS/DynamoDB/SNS，notify 的策略里没有
  S3/Rekognition——某个函数凭证泄露，影响面被锁死在它自己的那格；
- **状态机只能调两个分支函数**，不能调 notify 或 starter（防绕过管道顺序）；
- **无 KMS 权限**：桶用 SSE-S3（AWS 托管密钥），函数无需任何 kms:Decrypt。

## 通配符使用论证（原则：零裸 `*`，作用域通配逐条登记）

| 例外 | 位置 | 理由 |
|---|---|---|
| A | Rekognition `Resource: "*"` | 该服务不支持资源级权限（AWS 文档：authorization 不基于资源 ARN）；用 IAM 条件也无法收窄，属服务硬限制。已把 Action 收窄到唯一动作 `CompareFaces` 补偿 |
| B | S3 `raw/id-card/*`、`raw/selfie/*` | 键名含动态 application_id，无法枚举；通配被钉死在单一桶的两个前缀内，不跨前缀 |
| C | 日志 `log-group:/aws/lambda/<name>:*` | 日志流名由 Lambda 运行时自动生成；通配被钉死在该函数自己的日志组内 |
| D | DynamoDB `table/…/stream/*` | 流 token 是开启 Streams 时分配的时间戳，创建前不可知（F 部署后可回填具体 token 收窄为字面量） |

## 与 Learner Lab 现实的关系

Learner Lab 会话内实际执行角色为 `LabRole`（Lab 策略固定，无法替换为自建
最小权限角色）——本目录的策略 JSON 是**目标态设计文档**，进报告并注明此为
实验环境限制；生产部署时逐份挂到对应函数 / 状态机的执行角色上即可生效。

**交叉验证**：D/F 部署各自资源后，请对照本矩阵核对 ARN（尤其 §8 回填的
队列/主题/流 ARN 与此处是否一致），有出入提 PR 改这里，不要各改各的。
