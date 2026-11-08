# B 的首版交接说明

交付人：Li Donghan（B）。交付日期：2026-11-06。当前状态：本地可运行，尚未完成云端验收。

## 本次提交的范围

- `lambda/ocr/`：完整 OCR 模块、依赖清单、Dockerfile、部署工具、测试、两组 JSON 样例、合成评测数据和说明。
- `docs/ocr_selection.md`：选型依据、真实测量记录的位置和新版时间线。

保留上述仓库相对路径，将文件加入现有 KYC 仓库。GitHub 中应能直接看到源码，而不只是一个 ZIP；ZIP 用于传递或附在 Release 中供下载。不要把解压目录名再套到 `lambda/ocr` 外层。

本次包不包含 A 的 `README.md`、`docs/interface.md` 或报告主文件，避免覆盖其他成员工作；仍以仓库现有 `docs/interface.md` 为接口依据。也不包含虚拟环境、模型缓存、临时文件、构建产物、凭据或私人证件图片。

如果仓库还没有忽略规则，请 A 将以下规则合并到现有 `.gitignore`，不要覆盖原文件：

```gitignore
.venv/
.cache/
.downloads/
.tmp/
build/
__pycache__/
*.py[cod]
.pytest_cache/
.env
.env.*
*.pem
credentials
lambda/ocr/private-fixtures/
```

## 每个人现在可以开始什么

| 成员 | 可以立即开展 | 后续交接 |
|---|---|---|
| D | 用 `samples/valid.output.json` 和 `expired.output.json` 搭模拟 OCR 分支；按输入样例传完整状态机对象；配置 `OcrExtractionError` 捕获，并按 `$.ocr` 路径合并 | B 部署成功后提供真 ARN，再把模拟节点换成实际 Lambda；现在不能进行真实云端调用 |
| E | 提供至少5组正常证件素材与3个坏文件，附各字段标准答案；先核对现有用例和评测数据格式 | B 负责 OCR 模块复测；E 负责系统级压测，不要混用两种结果 |
| C | 提供实际桶名、对象路径约定，协助核对 LabRole 对证件对象的读取权限；按分工交叉复核 OCR | 不需 C 代写或代部署 B 的代码 |
| A | 协调演示账号与接口问题，确认单张图包含四字段的素材方案及“长期有效”的表示方式 | B 先在自己的 Lab 验证，再配合迁入 A 的演示账号 |
| B | 继续构建及运行容器、在自己的 Learner Lab 部署、用正式素材复测，补云端截图与 ARN | 11-09 云端初版、11-11 模块测试与交接、11-15 联调、11-19 幻灯与讲稿 |
| F | 可按现有脱敏字段准备存储和后续成本统计 | OCR 尚无真实云端调用量，不能据此生成实测云端成本 |

## 如何展示这次成果

1. 看 `README.md` 的运行步骤；已有项目环境可以执行 `verify.ps1`。
2. 展示合成图片，再运行 `local.py`，对照五字段 JSON；正常与过期各演示一次。
3. 展示 `validation/synthetic_comparison.csv` 和测试说明，解释为何暂选 RapidOCR。
4. 明确说明：54项单测通过；真 OCR 和入口联测已通过，S3 仍为模拟读取；5正常＋1过期＋3坏文件是合成集，不是生产准确率或云端性能结论。

## 接口与验收要点

- 正常输出仅含 `name`、`id_number_masked`、`expiry_date`、`issuing_authority`、`id_valid`。
- 过期证件返回 `id_valid: false`；D 再决定审核结论。本模块不返回 `review_status`。
- 缺字段、歧义、坏图等抛 `OcrExtractionError`；由 D 的 Catch 产生约定的 `$.ocr.ocr_error`。
- 样例桶名是占位符，上传图片和实际调用前必须替换。正常样例的 `id_valid: true` 以实际执行日不晚于其有效期为前提。
- 证件图须同时提供四字段；当前不接受无确定结束日期的“长期有效”。相关接口变更由 A 统一确认。
- 模块负责提取，不判断证件真实性；完整证件号不出现在正式返回值中。

请先读取 `README.md`；完整实现细节和限制均已记录，正式素材/云端失败必须如实补进验证记录。
