# `lambda/starter/`

**Owner:** D · Su Changwei

`vericloud-starter`: reads the SQS message, pre-checks both uploaded images, then starts the state machine.

**Tasks** (see the team plan, section 4): D3

**Expected files:**

- `handler.py` — `lambda_handler(event, context)`
- `requirements.txt` (Pillow is needed for the image check)

**Contract:** Sections 5.1, 5.2 and 7 of `docs/interface.md`. Do not invent new names or fields.
