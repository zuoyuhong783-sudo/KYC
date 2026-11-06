# `security/`

**Owner:** C · Hu Zhongyuan

Upload security and least-privilege design.

**Tasks** (see the team plan, section 4): C2, C3, C6, C7

**Expected files:**

- `presign.py` — generates two presigned PUT URLs (300 s) for an `application_id`
- `iam/*.json` — one least-privilege policy per Lambda / state machine (no `*` wildcards)

**Contract:** Sections 1 and 3 of `docs/interface.md`. Do not invent new names or fields.
