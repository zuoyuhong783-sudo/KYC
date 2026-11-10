# A5：S3 上传 → SQS 队列（操作步骤）

> 负责人：A（Zuo Yuhong）｜计划时间：11-09 ~ 11-10｜依据：`docs/interface.md` v1.3.1 第 2、3、5.2 节
> 状态：✅ 11-10 在演示账号完成并验证，桶名 `vericloud-raw-1009-a`（v1.3.1 起为正式名，原名留给 C 作人脸测试素材）
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
2. 在终端运行 `aws sts get-caller-identity`，`Arn` 里要有 **`voclabs`**。如果是 `runserver`，说明终端没拿到你账号的密钥：Lab 右上角 **AWS Details → AWS CLI: Show**，复制 `[default]` 那几行；终端输入 `cat > ~/lab_creds` 回车，粘贴，回车，按 Ctrl+D；再 `export AWS_SHARED_CREDENTIALS_FILE=~/lab_creds`（`~/.aws/credentials` 是只读的，别用 nano 改它）。每次 Start Lab 密钥都会换，每开新终端都要重新 export。密钥约 4 小时过期，不要发群里或提交到仓库。
3. 这一步**不要**先在你的账号里接 starter 的 SQS 触发器，否则测试消息会被 starter 先拿走，检查会失败。starter 留到 A6 再接。

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
| 2 | 建桶 `vericloud-raw-1009-a`，并打开：禁止公开访问、默认 SSE-S3 加密、`raw/` 7 天后自动删除 |
| 3 | 给队列加权限：**只允许这个桶**往队列发消息 |
| 4 | 配置事件通知：`raw/selfie/` 下有新文件就通知队列 |
| 5 | （`--verify` 时）传一个测试文件，确认队列收到消息，然后把测试文件和消息都删掉 |

在**自己的个人账号**里测试时，桶名会和演示账号冲突（桶名全球唯一），加个后缀即可：

```bash
BUCKET=vericloud-raw-1009-yourname bash setup_s3_event.sh --verify
```

> ⚠️ Lab 页面的 **Reset** 会清空整个账号（桶、队列、函数全删，终端里的文件也没了）。结束用 **End Lab**；看到 “account is still in cleanup” 只要等几分钟再 Start Lab。

## 方法二：控制台手动点（脚本跑不了时）

**① SQS 队列**（如果还没有）
SQS → Create queue：
- `vericloud-ingest-dlq`：Standard，Message retention period = 14 days
- `vericloud-ingest-queue`：Standard，Visibility timeout = 6 min；Dead-letter queue 选 `vericloud-ingest-dlq`，Maximum receives = 3

**② S3 桶**
S3 → Create bucket：名字 `vericloud-raw-1009-a`，Region `us-east-1`，Block all public access 勾上，Encryption 选 SSE-S3。
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
    "ArnLike": { "aws:SourceArn": "arn:aws:s3:::vericloud-raw-1009-a" },
    "StringEquals": { "aws:SourceAccount": "<账号ID>" }
  }
}
```

**④ 事件通知**
S3 → `vericloud-raw-1009-a` → Properties → Event notifications → Create：
- Name：`selfie-upload-to-ingest-queue`
- Prefix：`raw/selfie/`
- Event types：All object create events
- Destination：SQS queue → `vericloud-ingest-queue`

保存时若报 “Unable to validate destination”，就是第③步权限没加对。

**⑤ 检查**
S3 里往 `raw/selfie/` 传任意一个文件 → SQS → `vericloud-ingest-queue` → Send and receive messages → Poll for messages。
应该看到 2 条：一条 `s3:TestEvent`（第④步保存时 AWS 自动发的），一条 `ObjectCreated:Put`，里面有你上传的 key。看完把两条都删掉，再删掉测试文件。

## 做完以后

- [x] 截图：S3 事件通知配置页、终端 `OK` 输出（报告 A 部分可用；终端截图前先 `clear`，别带密钥）
- [x] interface.md §8.1：演示账号的桶名、队列 URL、DLQ ARN
- [x] 苏的 `setup_sqs.sh` 写死了他的账号 ID，演示账号改用本脚本建队列，苏不用改
- [ ] A6（11-12 起）：在本账号部署 starter，并加 SQS 触发器（Batch size = 1）
