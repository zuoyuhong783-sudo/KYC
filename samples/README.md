# samples/ —— 生成测试素材用的"人脸底图"

## 这个文件夹是什么

`faces/` 里放 7 张用于 `tests/gen_fixtures.py` 的人脸底图，用来合成测试用的证件照与自拍。
**这些不是真人照片**，是 AI 生成的人脸（StyleGAN），没有任何真实人物对应。

## 为什么不用网上的真人照片

- 项目契约 `docs/interface.md` §9 写明：只能用**组员本人**或**自制/合成**样例，禁止他人真实证件与人脸；
- 网图真人没有为"被做成身份证样本"给过同意，用于 KYC 测试不合适；
- AI 人脸没有肖像权与隐私问题，且能稳定复现"同一人"（同一张脸同时用于证件照和自拍）。

## 来源与筛选

- 来源：`https://thispersondoesnotexist.com`（每刷新一次生成一张新脸，1024×1024）；
- 共取 19 张，**人工逐张查看**后保留 7 张成年人脸（`person_2/09/11/13/14/15/16`），
  已剔除看起来未成年的样本——用未成年人面孔做证件样本不合适。

## 怎么用

```bash
# 用这些人脸生成完整 27 例素材（图片写到 tests/fixtures，已被 .gitignore 排除）
python tests/gen_fixtures.py --selfie-dir samples/faces --out tests/fixtures

# 交付前自检（相似度 / 坏文件；比脸需要 AWS 凭证）
python tests/gen_fixtures.py --selfie-dir samples/faces --check

# 校验分发出去的素材与这里生成的是同一套
cd tests/fixtures && shasum -a 256 -c SHA256SUMS
```

## 为什么不进 git

图片体积大、且属于"可再生资产"；仓库只保留 `manifest.csv` 与 `SHA256SUMS`，
素材通过共享盘分发并用 SHA-256 校验一致性。`.gitignore` 已排除 `samples/`。

## 注意

- 这些脸是合成的，**不要**用它们去申请任何真实服务；
- 如果课程/评审明确要求"组员本人照片"，11-11 会上确认后，把真人自拍放进 `samples/faces/`
  重跑一次生成即可，其余流程不变。
