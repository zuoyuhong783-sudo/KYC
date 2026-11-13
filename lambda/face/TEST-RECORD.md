# vericloud-face 测试记录（C5）

日期：2026-11-08 · 执行：C（胡同学） · 环境：macOS / Python 3.13 / pytest 9.2 / boto3（uv 临时环境）

## 1. 单元测试 `test_handler.py` — 10/10 通过，0.29s

不依赖任何 AWS 账号（botocore Stubber 假响应，D/E 直接跑）。Stub 的期望参数
同时锁死了契约调用方向：`source=自拍、target=证件照、SimilarityThreshold=0`。

| # | 用例 | 类别 | 结果 |
|---|---|---|---|
| 1 | 正常：99.98372 → 四舍五入 99.98 / matched | normal | PASS |
| 2 | 边界：80.0 整 → matched（`>= 80` 含等号） | normal | PASS |
| 3 | 多脸取最高：{81.2, 95.5, 88.8} → 95.5 | normal | PASS |
| 4 | 换人：42.156 → 42.16 / not matched | different_person | PASS |
| 5 | 边界：79.99 → not matched | different_person | PASS |
| 6 | 无脸：空 FaceMatches → FaceNotDetectedError | no_face | PASS |
| 7 | 无脸：InvalidParameterException → FaceNotDetectedError（11-06 实测发现的真实行为） | no_face | PASS |
| 8 | 坏图：InvalidImageFormatException → FaceCompareError | 容错 | PASS |
| 9 | 其他服务错误（Throttling）→ FaceCompareError | 容错 | PASS |
| 10 | 事件缺字段 → FaceCompareError（不裸抛 KeyError） | 容错 | PASS |

## 2. 集成测试 `test_integration.py` — 2026-11-13 复跑 3/3 通过

```bash
VERICLOUD_INTEGRATION=1 uv run --with boto3 --with pytest pytest test_handler.py test_integration.py -v
# 13 passed (10 unit + 3 integration)
```

| 用例 | 桶内素材 | 结果 |
|---|---|---|
| normal | smoke-app.jpg ×2（同一真人图） | `face_matched: true`, similarity 100.0 ≥ 80 ✅ |
| no_face | noface-test.jpg ×2（纯色合法 JPEG） | errorType=`FaceNotDetectedError`（契约异常名精确） ✅ |
| different_person | diff-source（奥巴马）/ diff-target（布什） | `face_matched: false`, similarity 0.78 < 80 ✅ |

注：Python 运行时对自定义异常报 `FunctionError: Unhandled`（而非 Handled），
但 errorType/errorMessage 与契约完全一致；Step Functions 的 Catch 按 errorType
匹配，不受该 header 影响——测试断言已按此放宽（in {"Handled","Unhandled"}）。

## 3. 给 D / E 的说明

- 单元测试随时可跑：`uv run --with boto3 --with pytest pytest lambda/face/test_handler.py -v`
- 样例 JSON 在 `samples/`（input + 三种输出），状态机 Mock 直接引用
- ⚠️ 桶内 fixture 上传于 11-06，`raw/` 生命周期 7 天将在 **~11-13 自动删除**；
  M2 端到端（11-15）前需按正式流程重传（presign → PUT），正好当上传链路演练
- C4 调试教训（给 E）：素材入库前先验文件头（`file`/`sips`），
  Wikimedia 直链失效会返回 HTML 错误页伪装成 .jpg
