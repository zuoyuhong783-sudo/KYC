# `stepfunctions/`

**Owner:** D · Su Changwei

Amazon States Language definitions for `vericloud-kyc-workflow`.

**Tasks** (see the team plan, section 4): D2, D4, D5

**Expected files:**

- `kyc_workflow.mock.asl.json` — mock version using Pass states
- `kyc_workflow.asl.json` — real version (Parallel, Retry/Catch, Choice, DynamoDB PutItem)

**Contract:** Sections 5.5 and 6 of `docs/interface.md`. Do not invent new names or fields.

## Status (2026-11-13)

`kyc_workflow.asl.json` is now the **real** workflow, written by A for D from the
batched A6 list (the old Pass-state version is kept as `kyc_workflow.mock.asl.json`):

- Parallel branches invoke `vericloud-ocr` and `vericloud-face` in the demo account
  `153547984638` (interface 8.1). Transient Lambda errors are retried twice.
- Each branch has its own Catch (contract errors from section 7, then `States.ALL`),
  so a failed branch becomes `{"ocr_error": ...}` / `{"face_error": ...}` (section 5.5)
  and the other result is kept.
- The Choice follows section 6 in order; `IsPresent` is used for the error fields.
- Four PutItem states write only the fields that exist (section 4), so a FAIL or
  NEEDS_HUMAN_REVIEW record is always written. `received_at` is carried through.

Checked with a local simulator on 8 cases (normal, different person, no face,
unexpected face error, expired, OCR failed, both failed, similarity exactly 80):
every case writes one row with the expected `review_status` / `reason`.
Not yet run in AWS.

## Deploy (A6, demo account)

```bash
cd ~/KYC/stepfunctions/stepfunctions
aws stepfunctions validate-state-machine-definition --definition file://kyc_workflow.asl.json
ROLE=$(aws iam get-role --role-name LabRole --query Role.Arn --output text)
# first time
aws stepfunctions create-state-machine --name vericloud-kyc-workflow \
  --definition file://kyc_workflow.asl.json --role-arn "$ROLE" --type STANDARD
# later changes
aws stepfunctions update-state-machine \
  --state-machine-arn arn:aws:states:us-east-1:153547984638:stateMachine:vericloud-kyc-workflow \
  --definition file://kyc_workflow.asl.json
```

Deploy `vericloud-ocr`, `vericloud-face` and the table first; the starter needs
`STATE_MACHINE_ARN` set to the ARN above.
