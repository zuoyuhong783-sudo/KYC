# VeriCloud 前端

打开 dist/index.html 可直接试用；默认是交互演示，不会上传照片，也不会进行真实识别。照片只在当前页面的内存中预览，不写入浏览器持久存储。

## 当前功能

- 身份证、自拍选择与拖拽，格式/大小/可解码检查及预览。
- 使用授权确认、处理中状态、结果页、复制申请编号、重新申请。
- 响应式中文页面，无安装依赖。

## 接入 AWS

现有仓库没有可供浏览器调用的申请创建、结果查询接口。下面是前端适配器约定，**不是声称现有后端已经提供这些接口**。请与组长、C/D/F 确认后实现。

在 dist/config.js 中把 mode 改为 live，并提供 adapter：

```js
window.VERICLOUD = {
  mode: 'live',
  adapter: {
    async createApplication({application_id, id_card_extension, selfie_extension}) {
      // 调用团队实际提供的、已鉴权的后端接口。
      // 返回 {id_card_url, selfie_url}，两个地址分别对应两个文件的扩展名。
      // 后端须校验 UUID、扩展名、上传权限并签发短时 HTTPS PUT URL。
    },
    async getResult({application_id}) {
      // 调用团队实际提供的、已鉴权的结果查询接口。
      // 未完成返回 null；完成返回现有接口字段：
      // {review_status, reason, processed_at}
      // review_status 为 PASS / FAIL / NEEDS_HUMAN_REVIEW。
    }
  }
};
```

前端严格先完成证件 PUT，再 PUT 自拍；不签发 AWS 凭证，不直接访问 DynamoDB。每次申请生成小写 UUID v4。浏览器 PUT 不额外添加 Content-Type，保持现有预签名方式兼容。结果最多等待两分钟，每 2.5 秒查询一次；查询接口自身应实现请求超时。上传超时为 60 秒。

团队还需配置 S3 CORS 允许前端来源 PUT，以及后端 CORS/鉴权。不要把 AWS Access Key、Secret Key 或 Session Token 放入 config.js。尚未连接 AWS；端到端上传、识别与邮件需要团队部署后验证。真实模式未配置适配器时会显示错误，不会伪造通过结果。

超时页面显示申请编号以便人工查询。当前页面不提供刷新恢复、历史申请查询或人工审核操作。识别两步在真实模式下仅表示等待后端处理，不推测后端的精确阶段。

## 已接好的后端（A，2026-11-13）

上面约定的两个接口已由 `lambda/api/handler.py`（`vericloud-api`）实现，`dist/config.js` 里的适配器也已写好：

| 前端调用 | 后端 | 返回 |
|---|---|---|
| `createApplication` | `POST /applications` | 两个 5 分钟有效的 PUT 地址；同一编号已用过返回 409 |
| `getResult` | `GET /applications/<id>` | 处理中 404（前端继续等）；完成后只返回 `review_status`、`reason`、`processed_at` |

切到真实模式只要在 Learner Lab 终端跑一次（会建函数和 API Gateway 地址、给桶加 CORS、把地址写进 `dist/config.js`）：

```bash
cd ~/KYC && bash infrastructure/setup_api.sh
```

然后把 `frontend/dist` 整个文件夹拷到演示电脑，双击 `index.html` 即可。`VERICLOUD_API` 为空时自动回到演示模式。

注意：接口没有登录鉴权，只适合课堂演示；接口地址不要发到群外。端到端能出结果，前提是 A6 已把 OCR、人脸、状态机、表部署到演示账号。
