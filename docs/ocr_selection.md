# B 的 OCR 选型与验证记录

日期：2026-11-06。负责人：Li Donghan。依据：新版分工 V1.1 和仓库 `docs/interface.md` v1.0。

当前暂选 RapidOCR。已完成同图本地对比，但尚未取得 E 的正式测试素材，B1 的最终素材验收仍待补齐。下列数字只描述本次合成集，不能写成真实证件识别准确率。

## 方案与取舍

| 方案 | 实际实现 | 部署考虑 |
|---|---|---|
| RapidOCR | `rapidocr-onnxruntime==1.4.4`，CPU ONNX Runtime | wheel 包含中英文识别模型；复用模型实例；已提供 Lambda Python 3.12 容器定义 |
| Tesseract | `tesserocr==2.12.0`，`chi_sim+eng`，PSM 6 | 用 C++ API 封装运行同一 Tesseract 引擎，未另装系统级可执行程序；仅用于本地比较 |

使用 `tesserocr` 而非示例中的 `pytesseract`，是为了把依赖完整放在本地虚拟环境中；这是封装方式的选择，不是另换了比较对象。Tesseract 模型来自官方 `tessdata_fast`，版本固定为 `87416418657359cb625c412a48b6e1d6d41c29bd`，校验值见 setup 脚本和实测元数据。

## 实测方法和结果

样本由 `lambda/ocr/generate_fixtures.py` 生成，图片醒目标注 `SYNTHETIC OCR TEST - NOT AN ID DOCUMENT`。包含5张正常图（中文、英文、日期区间、JPEG、标签和值分行）、1张过期图、3个坏文件。号码以虚构的 `000000` 开头；无真人证件或人脸。

评测日期固定为 2026-11-06。两种引擎使用相同预处理、相同字段提取和相同标准答案。5字段含4个提取字段及派生的 `id_valid`；整张正确要求五字段全部匹配。

| 本地合成集指标 | RapidOCR | Tesseract |
|---|---:|---:|
| 5 张正常图片全字段匹配 | 5/5 | 3/5 |
| 5 张正常图片四个提取字段匹配 | 20/20 | 18/20 |
| 过期图片全字段匹配 | 1/1 | 0/1（姓名错误；有效期判断正确） |
| 3 个坏文件被拒绝 | 3/3 | 3/3 |

坏文件在共同预处理层被拒绝，这一项不能证明某个 OCR 引擎的识别能力。逐张耗时、首张标志及逐字段正确性保存在 [原始 CSV](../lambda/ocr/validation/synthetic_comparison.csv)，运行版本、图片和模型 SHA-256 保存在相邻的 `.metadata.json`。

本次 Tesseract 推理更快，但在中文姓名上出现错误；因此当前优先采用字段匹配更好的 RapidOCR。这不是统计上充分的结论，不能推断整体生产表现。时间包含本机读图、推理与提取，第一张包括初始化；没有测得 AWS 冷启动、端到端 p99 或并发能力。

## 已验证与待验证

- 本地字段、异常和调用契约测试覆盖缺字段、过期边界、全角/空格、歧义号码、非法日期、S3 失败、流关闭、坏文件和内存边界。
- 真 OCR 已读取合成图片，非固定返回值；另外通过模拟 S3 可测完整 Lambda 入口。
- 已锁定生产/开发依赖，且生产依赖可解析到 Python 3.12 / Linux glibc 2.34；尚无容器运行或云端调用成功证据。
- 下一步使用 E 的至少5组正常图和3个坏文件复测，保留每项标准答案与失败原因；必要时调整预处理和字段规则，再交 D 真 ARN。

## 新时间线

| 项目 | 截止 | 当前状态 |
|---|---|---|
| B1 两种方案实测选择 | 11-07 | 合成集比较完成；待 E 素材复测 |
| B2 云端初版可调用 | 11-09 | 容器/部署代码已备；Docker 及 Learner Lab 验收未完成 |
| B3/B4 字段提取与接口 | 11-10 | 本地实现完成 |
| B5 单测与交接样例 | 11-11 | 本地合成测试和两组 JSON 已备；待正式素材与云端测试 |
| B6 与 A/D 联调 | 11-15 | 等云端资源和流水线 |
| 系统冻结 | 11-18 | 此后只修问题、补证据 |
| B9 PPT 与讲稿 | 11-19 | 后续用真实运行证据制作；11-24 展示 |
| B7 报告 / B8 复核 C | 11-29 / 11-30 | 集中写作在展示后进行 |

技术参考：[RapidOCR 包与 Python 支持](https://pypi.org/project/rapidocr-onnxruntime/1.4.4/)、[Tesserocr 的打包与 API](https://pypi.org/project/tesserocr/)、[官方 Tesseract 模型](https://github.com/tesseract-ocr/tessdata_fast)、[AWS Lambda Python 容器部署](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html)。
