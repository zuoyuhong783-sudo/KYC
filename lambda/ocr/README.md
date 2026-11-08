# B 的 OCR 模块使用说明

负责人：Li Donghan。按 2026-11-05 的 V1.1 分工和仓库 `docs/interface.md` v1.1 实现。课堂展示为 2026-11-24。

当前已有可在本地运行的识别、字段提取、Lambda 入口、容器定义和部署工具。云端 Lambda 尚未部署；E 的正式素材尚未收到。下面的测试成绩仅来自自制样例。

## 做什么

`handler.lambda_handler(event, context)` 接收状态机输入，读取 `bucket` 和 `id_card_key` 指定的图片，通过 RapidOCR 识别文字，再返回且只返回：

```json
{
  "name": "测试甲",
  "id_number_masked": "**************1234",
  "expiry_date": "2035-05-01",
  "issuing_authority": "测试市公安局",
  "id_valid": true
}
```

`id_valid` 按处理当天的 UTC 日期计算，有效期等于当天仍有效。过期证件返回 `false`，由 D 决定 `FAIL`；本模块不写数据库、不比人脸、不发送邮件。

缺字段、日期无效、多组冲突值、无法读取或识别图片时，抛 `OcrExtractionError`。错误只说明字段或故障类别，不包含原始 OCR、姓名和完整证件号。

## 文件位置

| 文件 | 用途 |
|---|---|
| `handler.py` | S3 读取、输入校验、Lambda 入口 |
| `ocr_engine.py` | 图片预处理、RapidOCR；本地对比用 Tesseract |
| `extraction.py` | 中英文标签识别、字段提取、证件号脱敏、有效期判断 |
| `local.py` | 不需要 AWS 的图片识别命令 |
| `benchmark.py` | 同一套有标准答案的图片对比两种引擎 |
| `generate_fixtures.py` | 生成明确标为测试用途的虚构图片 |
| `integration_smoke.py` | 真 Lambda 入口＋真 OCR，只有 S3 读取是模拟的 |
| `samples/` | 正常、过期两组输入/输出 JSON，供 D 对接 |
| `tests/` | 本模块单测，不占用 E 的测试目录 |
| `validation/` | 合成样例的实测 CSV、版本、文件校验值 |
| `Dockerfile`、`deploy.py` | 容器定义和使用现有 LabRole 的部署工具 |

## 在 Windows 本地运行

所有命令从 `D:\clouding project` 执行。环境、模型、缓存、临时文件、生成的图片均留在项目下；不需要修改系统 PATH。`uv` 已在本机可用。

```powershell
& .\lambda\ocr\setup.ps1 -WithComparison
& .\lambda\ocr\verify.ps1
```

`setup.ps1` 使用项目内的 Python 3.12 和 `.venv`，不注册全局 Python；`-WithComparison` 另下载固定版本的 Tesseract 中文/英文模型到 `.downloads/tessdata` 并核对 SHA-256。RapidOCR 模型随其 wheel 安装，推理时不下载模型。

`verify.ps1` 执行单测、生成 `build/ocr-fixtures`、运行真实 OCR 和入口集成测试。Windows 默认使用已有的微软雅黑字体；其他系统运行 Python 脚本时通过 `--font` 指定支持中文的字体。

识别单张图：

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPYCACHEPREFIX = 'D:\clouding project\.cache\pycache'
& .\.venv\Scripts\python.exe .\lambda\ocr\local.py .\build\ocr-fixtures\normal_cn.png
```

真实素材建议放 `lambda/ocr/private-fixtures/`，该目录已被忽略。`--raw` 只供本地合成样例调试，会打印原始文字；云端入口始终返回脱敏后的五字段。

## 复测两种方案和 E 的素材

```powershell
& .\lambda\ocr\verify.ps1 -Compare
```

比较文件在 `build/ocr-validation/comparison.csv`。候选引擎识别错误会返回非零状态并保留逐字段结果，不应将失败改成成功。运行时间是本机“读图＋OCR＋字段提取”，首张包含模型加载，不能当成云端 p99。

接到 E 的素材后，参考 `build/ocr-fixtures/manifest.json` 建立 B 自己的评测清单：每项有图片路径、五字段标准答案，或者预期 `OcrExtractionError`。标准答案由人工核对，`today` 固定评测日。E 的 `manifest.csv` 只有整条流水线的预期结论，不能直接用来计算 OCR 字段准确率。

```powershell
$env:TESSDATA_PREFIX = 'D:\clouding project\.downloads\tessdata'
& .\.venv\Scripts\python.exe .\lambda\ocr\benchmark.py .\lambda\ocr\private-fixtures\manifest.json --engines rapidocr tesseract --output .\build\ocr-validation\e_comparison.csv
```

评测 CSV 不保存识别出的姓名/完整证件号；文件只包含正确性、耗时和经过清理的错误消息。保留原始结果，不使用指南中的示例数字代替实测。

## 打包及本地容器验收

**前置条件：Docker Desktop 的 Linux 引擎已运行，且镜像、构建缓存和虚拟磁盘存储已配置在本项目目录下。** 本次未启动或修改 Docker 的全局设置；单独设置 `DOCKER_CONFIG` 只改变客户端配置位置，不改变引擎存储位置。

```powershell
$env:DOCKER_CONFIG = 'D:\clouding project\.cache\docker'
New-Item -ItemType Directory -Force -Path $env:DOCKER_CONFIG | Out-Null
docker buildx build --platform linux/amd64 --provenance=false --load -t vericloud-ocr:local .\lambda\ocr
```

镜像基于 AWS Python 3.12 / AL2023，安装锁定依赖和 OpenCV 系统库；构建期间初始化模型，缺模型或共享库会直接使构建失败。部署架构固定 x86_64。依赖已针对 Python 3.12 / Linux glibc 2.34 做解析检查，这不等于镜像已构建成功。

无需 AWS 的容器实测，可把本地合成图片以只读方式挂载：

```powershell
docker run --rm --platform linux/amd64 --entrypoint python --mount 'type=bind,source=D:\clouding project\build\ocr-fixtures,target=/fixtures,readonly' vericloud-ocr:local -c "from pathlib import Path; from ocr_engine import recognize; from extraction import extract_fields; print(extract_fields(recognize(Path('/fixtures/normal_cn.png').read_bytes())))"
```

## 部署到 Learner Lab

1. 获取当次 Lab 会话的临时凭据，在当前终端配置标准 AWS 环境变量，包含 Session Token；不要把凭据写进文件或发进聊天。使用 `us-east-1` 和既有 `LabRole`，由 C 保证其有实际桶的读取权限。
2. 将本地验证通过的镜像推送至本账号 `us-east-1` 的私有 ECR 仓库。推送需要可用的 ECR 登录方式；本项目没有把账号、仓库或 ARN 写死，也不自动创建 IAM 资源。
3. 执行下面命令；将占位符替换为自己的镜像 URI 和 LabRole ARN。此命令会创建/更新 `vericloud-ocr`，1536 MB 内存、60 秒超时。

```powershell
& .\.venv\Scripts\python.exe .\lambda\ocr\deploy.py --image-uri '<ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/<REPOSITORY>:<TAG>' --lab-role-arn 'arn:aws:iam::<ACCOUNT>:role/LabRole'
```

已有同名 ZIP 或 ARM 函数会被保留并报错，不会被删除重建。部署结果存 `build/ocr-deployment.json`，只记录配置和 ARN。上传合成图片后，将 `samples/*.input.json` 的桶名改为实际值，在 Lambda 控制台测试；再交 D 真正的函数 ARN、样例和成功/失败截图。创建成功不代表已验收：必须实际调用并检查结果。

依据：[AWS Python 容器部署文档](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html)。

## 当前能力边界

- 支持有中/英文标签、字段完整的样例证件；证件号支持 15 位数字或 18 位（末位允许 X）的大陆证件号形式。这里只做形式提取，不校验证件真实性或号码校验位。
- 单张输入图必须包含姓名、号码、签发机关和有效期。缺一面所需字段时会报错；如需支持两张图，应先由 A 修改接口。
- 具体日期支持 `YYYY-MM-DD`、点号、斜杠和中文年月日；有效期区间取结束日。`长期` 没有约定的日期表示方式，明确报错，不填虚构的未来日期。
- 透明背景 PNG 合成到白底，按 EXIF 校正方向；倾斜、反光、模糊、复杂版面仍需 E 的真实素材验证。当前清晰合成样例不能代表这些场景的准确率。
- 图片上限为 10 MiB / 2000 万像素，超大图拒绝处理；长边缩至最多 2400 像素。该限制属于 OCR 实现限制，联调时需让 A/C/E 知悉。
- 原始文字不在 Lambda 返回值或自有日志中输出。D 的 Catch 应保持 `ErrorEquals: ["OcrExtractionError"]`，将错误路由到约定的 `FAIL / ocr_failed`。

## 仓库集成状态 2026-11-08

源码已经按仓库目录展开；根目录旧 ZIP 仅是历史交接快照，后续请使用本目录。样例使用演示桶 `vericloud-raw-1009`，各人 Lab 测试需换成自己的实际桶名。启动入口的证件前缀已按接口修正为 `raw/id-card/`。当前状态机仍为 Mock，不会实际调用 OCR；云端部署成功后由 D 将模拟节点换为 Lambda Task 并填入真实 ARN。详细接线事项见 `INTEGRATION.md`。
