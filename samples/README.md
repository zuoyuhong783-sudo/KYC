# samples/ —— 生成测试素材用的"人脸底图"

## 这个文件夹是什么

`faces/` 里放用于 `tests/gen_fixtures.py` 的人脸底图，用来合成测试用的证件照与自拍。

**当前内容：组员本人照片**（WeChat 传输的自拍等），替换了早前的一版 AI 合成人脸。
图片只在本地使用，`samples/faces/` 已被 `.gitignore` 排除，**不进 git、不进公开仓库**。

## 为什么用本人照片 / 合成脸，而不用网图

- 项目契约 `docs/interface.md` §9 写明：只用**组员本人**或**自制/合成**样例，禁止他人真实证件与人脸；
- 网图真人没有为"被做成身份证样本"给过同意；
- 早前为了不等照片，先用过 7 张 AI 合成脸（StyleGAN，非真人）跑通流程；拿到本人照片后已替换。

## 怎么用

```bash
# 用这里的照片生成完整 27 例素材（图片写到 tests/fixtures，已被 .gitignore 排除）
python tests/gen_fixtures.py --selfie-dir samples/faces --out tests/fixtures

# 交付前自检（相似度 / 坏文件；比脸需要 AWS 凭证）
python tests/gen_fixtures.py --selfie-dir samples/faces --check

# 校验分发出去的素材与这里生成的是同一套
cd tests/fixtures && shasum -a 256 -c SHA256SUMS
```

## 注意

- 这些是组员本人照片，**不要**上传到公开仓库或截图进报告（需打码）；
- 合成的证件图带 `SAMPLE / 仅测试` 水印，证件号、姓名均为虚构；
- 若后续再增补组员自拍，直接放进 `samples/faces/` 重跑一次生成即可，其余流程不变。
