# VeriCloud Live (demo frontend, A)

One file, no install: `index.html`. Built for the 11-24 presentation on top of
`vericloud-api` (`lambda/api`). The teammate's simpler page stays in `frontend/dist`.

## What it shows

**Verify an applicant**: upload an ID card and a selfie, then watch the real
pipeline in AWS, refreshed every 1.5 s from `GET /applications/<id>/trace`:

1. upload links issued → 2. ID card in S3 → 3. selfie in S3 (the trigger) →
4. SQS + starter pre-check → 5. OCR → 6. face comparison → 7. decision rule →
8. DynamoDB row → 9. SNS email

with timings, the masked OCR fields, the similarity against the 80 threshold and
a latency bar (queue + start vs. workflow). A row of AWS services lights up as
each one finishes.

The **fault demo** checkbox uploads a truncated selfie: the starter rejects it,
no workflow starts, and the page explains the 3 SQS retries and the DLQ.

**Operations**: PASS / review / FAIL counts, queue and DLQ depth, running
workflows and the latest applications, refreshed every 5 s from `GET /dashboard`.

## Run it

1. In the Learner Lab terminal: `cd ~/KYC && git pull && bash infrastructure/setup_api.sh`
   (deploys the API code with the two new endpoints; prints `API URL`).
2. On any computer open `frontend/live/index.html`, click **API settings**, paste
   the API URL. It is kept in that browser only. Or open `index.html?api=<API URL>`.

Name and ID number are shown masked; the API never returns them in full.
No login: keep the API URL inside the team.
