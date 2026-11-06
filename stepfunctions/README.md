# `stepfunctions/`

**Owner:** D · Su Changwei

Amazon States Language definitions for `vericloud-kyc-workflow`.

**Tasks** (see the team plan, section 4): D2, D4, D5

**Expected files:**

- `kyc_workflow.mock.asl.json` — mock version using Pass states
- `kyc_workflow.asl.json` — real version (Parallel, Retry/Catch, Choice, DynamoDB PutItem)

**Contract:** Sections 5.5 and 6 of `docs/interface.md`. Do not invent new names or fields.
