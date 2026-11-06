# `lambda/ocr/`

**Owner:** B · Li Donghan

`vericloud-ocr`: extracts name, ID number (masked), expiry date and issuing authority from the ID-card image with an open-source OCR library.

**Tasks** (see the team plan, section 4): B1, B2, B3, B4, B5

**Expected files:**

- `handler.py`
- `Dockerfile` (container image based on `public.ecr.aws/lambda/python:3.12`)
- `requirements.txt`
- `samples/` — sample input/output JSON for D and E

**Contract:** Sections 5.3 and 7 of `docs/interface.md`. Do not invent new names or fields.
