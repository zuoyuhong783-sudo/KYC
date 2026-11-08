# OCR 仓库接入记录

日期：2026-11-08。对照 `docs/interface.md` v1.1；整合基线为 main 提交 `a993c902d9b66da106b46c33fe8a93b02a1e013e`。

## 本次接入

- B 源码、依赖锁定、Dockerfile、工具、测试和样例已展开到 `lambda/ocr/`。
- 选型记录在 `docs/ocr_selection.md`；根目录 README 提供入口；忽略规则补充项目缓存和私人素材。
- 两组输入样例的桶名更新为演示桶 `vericloud-raw-1009`。个人账号测试须替换实际桶名。
- 修正 starter 的证件前缀：`raw/id_card/` → `raw/id-card/`，与接口、预签名上传及 OCR 输入校验一致。新增跨模块回归测试，在模拟 S3/Step Functions 客户端的情况下验证 starter 的输出可直接被 OCR 接收。
- 根目录 ZIP 保留为历史快照；后续以源码为准。

## D 接入真实 OCR 时

当前 `stepfunctions/stepfunctions/kyc_workflow.asl.json` 明确是 Mock：`Mock_OCR_Worker` 为 Pass，尚无真实 Lambda 调用。仓库整合不等于 AWS 部署完成。

1. B 在实际 Lab 完成容器部署与调用测试，提供 `vericloud-ocr` 的真实 ARN，填入接口文档第8节。
2. D 将 Mock OCR 节点替换为 Lambda Task，原样传递五个输入字段；使用 `arn:aws:states:::lambda:invoke` 时，需要提取返回的 `Payload`，不能把带 SDK 元数据的外层对象当 OCR 结果。
3. Catch 捕获 `OcrExtractionError`。接口规定最终在 `$.ocr.ocr_error` 中记录错误，OCR 正常值在 `$.ocr`。当前 Mock 使用内部 `ocr_result.data`/`has_error` 包装，正式状态机需由 D 统一映射与判定路径。
4. OCR 失败时，当前 Mock 的写库节点仍直接引用姓名等缺失字段。`States.Array(...)` 不是缺失字段的兜底：应为失败结果使用不会引用缺失 OCR 字段的写库路径，否则可能在写库前报错。
5. 当前 starter 根据自拍后缀推导证件后缀；证件和自拍后缀不同的场景，D 仍需按接口约定补全 jpg/jpeg/png 查找。本次回归验证相同 jpg 后缀的跨模块契约。

没有填写虚构 ARN，也没有把 Mock 状态机标记为真实联调成功。以上工作在云端联调时继续完成。

## 本地复核

分别运行 OCR 与 face 的单测，避免同名 `handler.py` 的 Python 导入相互影响。测试均隔离 AWS 客户端；云端函数、权限和真实素材需要另外验收。

原 `validation/` 中2026-11-06的54项单测及9个合成用例数据保留为历史证据。本次另新增 starter→OCR 契约回归，不修改历史报告的测试数量。
