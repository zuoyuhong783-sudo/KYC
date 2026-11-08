# `lambda/face/`

**Owner:** C · Hu Zhongyuan

`vericloud-face`: compares the selfie with the ID-card photo using Amazon Rekognition `CompareFaces`.

**Tasks** (see the team plan, section 4): C4, C5

**Expected files:**

- `handler.py`
- `samples/` — sample input/output JSON for D and E
- `test_handler.py` — unit tests (no AWS account needed: `uv run --with boto3 --with pytest pytest test_handler.py -v`)
- `test_integration.py` — invokes the deployed function (opt in with `VERICLOUD_INTEGRATION=1` + a valid `[lab]` profile)
- `TEST-RECORD.md` — C5 test record

**Contract:** Sections 5.4 and 7 of `docs/interface.md`. Do not invent new names or fields.
