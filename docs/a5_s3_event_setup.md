# A5：S3 上传 → SQS 队列（操作步骤）

> 负责人：A（Zuo Yuhong）｜计划时间：11-09 ~ 11-10｜依据：`docs/interface.md` v1.2 第 2、3、5.2 节
> 脚本：`infrastructure/setup_s3_event.sh`

## 这一步要做成什么

用户把**自拍**传到 `raw/selfie/` 后，S3 自动往 `vericloud-ingest-queue` 发一条消息，之后由 starter 接手。证件照上传（`raw/id-card/`）**不会**触发。

```
上传证件照 → raw/id-card/<id>.jpg      （不触发）
上传自拍   → raw/selfie/<id>.jpg  ──▶  S3 事件通知 ──▶ SQS vericloud-ingest-queue ──▶ starter
                                                          └─ 失败 3 次 ─▶ vericloud-ingest-dlq
```

## 开始前

1. 打开 AWS Academy → Learner Lab → **Start Lab**，等左上角变绿。
2. 确认胡同学已删掉他账号里的 `vericloud-raw-1009`（桶名全球唯一）。没删也能先做：用临时名字，见下面「桶名被占」。
3. 在终端运行 `aws sts get-caller-identity`，`Arn` 里要有 **`voclabs`**。如果是 `runserver`，说明终端没拿到你账号的密钥：Lab 右上角 **AWS Details → AWS CLI: Show**，把 `[default]` 那几行粘进 `~/.aws/credentials`（`nano ~/.aws/credentials`）。密钥约 4 小时过期，不要发群里或提交到仓库。
4. 这一步**不要**先在你的账号里接 starter 的 SQS 触发器，否则测试消息会被 starter 先拿走，检查会失败。starter 留到 A6 再接。

## 方法一：一键脚本（推荐，约 2 分钟）

在 Learner Lab 页面下方的终端里：

```bash
git clone https://github.com/zuoyuhong783-sudo/KYC.git
cd KYC/infrastructure
bash setup_s3_event.sh --verify
```

最后看到 `OK: upload to raw/selfie/... produced an SQS message.` 就成功了。把最后打印的 3 行（桶名、队列 URL、DLQ ARN）发给我 / 填进 interface.md 第 8 节。

脚本做了什么（5 步，重复运行不会出问题）：

| 步骤 | 内容 |
|---|---|
| 1 | 建 DLQ（保留 14 天）和入口队列（可见性超时 360 秒，失败 3 次进 DLQ）。**自动读取你的账号 ID**，不会像 `setup_sqs.sh` 那样写死苏的账号 |
| 2 | 建桶 `vericloud-raw-1009`，并打开：禁止公开访问、默认 SSE-S3 加密、`raw/` 7 天后自动删除 |
| 3 | 给队列加权限：**只允许这个桶**往队列发消息 |
| 4 | 配置事件通知：`raw/selfie/` 下有新文件就通知队列 |
| 5 | （`--verify` 时）传一个测试文件，确认队列收到消息，然后把测试文件和消息都删掉 |

**桶名被占**（胡还没删）时，先用临时名：

```bash
BUCKET=vericloud-raw-1009-a bash setup_s3_event.sh --verify
```

等他删了再用正式名字跑一次即可。演示账号最后必须是 `vericloud-raw-1009`。

## 方法二：控制台手动点（脚本跑不了时）

**① SQS 队列**（如果还没有）
SQS → Create queue：
- `vericloud-ingest-dlq`：Standard，Message retention period = 14 days
- `vericloud-ingest-queue`：Standard，Visibility timeout = 6 min；Dead-letter queue 选 `vericloud-ingest-dlq`，Maximum receives = 3

**② S3 桶**
S3 → Create bucket：名字 `vericloud-raw-1009`，Region `us-east-1`，Block all public access 勾上，Encryption 选 SSE-S3。
建好后 Management → Lifecycle rule：前缀 `raw/`，7 天后 Expire。

**③ 队列权限**
SQS → `vericloud-ingest-queue` → Access policy → Edit，在 `Statement` 里加入（把 `<账号ID>` 换成你的 12 位账号）：

```json
{
  "Sid": "AllowS3SendMessage",
  "Effect": "Allow",
  "Principal": { "Service": "s3.amazonaws.com" },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:us-east-1:<账号ID>:vericloud-ingest-queue",
  "Condition": {
    "ArnLike": { "aws:SourceArn": "arn:aws:s3:::vericloud-raw-1009" },
    "StringEquals": { "aws:SourceAccount": "<账号ID>" }
  }
}
```

**④ 事件通知**
S3 → `vericloud-raw-1009` → Properties → Event notifications → Create：
- Name：`selfie-upload-to-ingest-queue`
- Prefix：`raw/selfie/`
- Event types：All object create events
- Destination：SQS queue → `vericloud-ingest-queue`

保存时若报 “Unable to validate destination”，就是第③步权限没加对。

**⑤ 检查**
S3 里往 `raw/selfie/` 传任意一个文件 → SQS → `vericloud-ingest-queue` → Send and receive messages → Poll for messages。
应该看到 2 条：一条 `s3:TestEvent`（第④步保存时 AWS 自动发的），一条 `ObjectCreated:Put`，里面有你上传的 key。看完把两条都删掉，再删掉测试文件。

## 做完以后

- [ ] 截图：S3 事件通知配置页、SQS 收到的消息（报告 A 部分可用）
- [ ] interface.md 第 8 节：演示账号的桶名、队列 URL、DLQ ARN（目前那几行是苏个人账号的）
- [ ] 告诉苏：`setup_sqs.sh` 里写死了他的账号 ID `493114794251`，在别人账号跑会把 DLQ 绑错。可改成 `ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)`
- [ ] A6（11-12 起）：在本账号部署 starter，并加 SQS 触发器（Batch size = 1）
