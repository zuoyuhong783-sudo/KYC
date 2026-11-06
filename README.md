# VeriCloud — Serverless KYC Verification Pipeline on AWS

CDS538 Cloud Computing · Team **SkyFin**

VeriCloud is an event-driven, fully serverless KYC (Know Your Customer) document verification pipeline built on AWS Academy Learner Lab. A user uploads an ID-card photo and a selfie; the system runs OCR text extraction and face comparison **in parallel**, writes the decision to DynamoDB, and notifies the applicant by email. Corrupted uploads are quarantined in an SQS dead-letter queue, and low-confidence face matches are routed to human review.

> **Interface contract:** [`docs/interface.md`](docs/interface.md) is the single source of truth for every resource name, S3 key, JSON field, DynamoDB attribute and exception name. Read it before writing any code.

## Architecture

```text
Client ──(presigned URL, 5 min)──▶ S3 vericloud-raw-<suffix>
                                     raw/id-card/<application_id>.jpg
                                     raw/selfie/<application_id>.jpg   ← selfie upload triggers the pipeline
                                         │
                              S3 event ──▶ SQS vericloud-ingest-queue ──(3 failures)──▶ vericloud-ingest-dlq (14 days)
                                         │
                              Lambda vericloud-starter (pre-check) ──▶ Step Functions vericloud-kyc-workflow
                                                                          ├─ Lambda vericloud-ocr   (open-source OCR)
                                                                          └─ Lambda vericloud-face  (Amazon Rekognition)
                                                                          ▼
                                                              Choice → DynamoDB vericloud-kyc-table
                                                                          ▼
                                     DynamoDB Streams ──▶ Lambda vericloud-notify ──▶ SNS vericloud-kyc-topic ──▶ email
Monitoring: CloudWatch dashboard vericloud-dashboard · alarms ──▶ SNS vericloud-ops-alarm
```

Decision rules: ID valid and face similarity ≥ 80 → `PASS`; similarity < 80 or face error → `NEEDS_HUMAN_REVIEW`; OCR failure or expired ID → `FAIL`.

## Team

| Role | Member | Owns |
|---|---|---|
| A | Zuo Yuhong | Project lead, architecture, S3 event wiring, integration, report & slides |
| B | Li Donghan | `lambda/ocr` — OCR Lambda |
| C | Hu Zhongyuan | S3 bucket, presigned URLs, IAM design, `lambda/face` — face comparison |
| D | Su Changwei | SQS + DLQ, `lambda/starter`, `stepfunctions/` |
| E | Li Hengchen | `tests/` — test fixtures, load test, CloudWatch dashboard & alarms |
| F | Yang Xueli | DynamoDB table, `lambda/notify` + SNS, cost (TCO) analysis |

## Repository layout

```text
KYC/
├── README.md            ← this file (A)
├── docs/                ← interface.md, integration_log.md (A); ocr_selection.md (B); kyc_rules.md (F)
├── lambda/
│   ├── starter/         ← D: file pre-check + StartExecution
│   ├── ocr/             ← B: OCR (container image: Dockerfile, samples/)
│   ├── face/            ← C: Rekognition CompareFaces (samples/)
│   └── notify/          ← F: DynamoDB Streams → SNS
├── stepfunctions/       ← D: *.asl.json
├── security/            ← C: presign.py, iam/*.json
├── tests/               ← E: fixtures/, load_test.py, collect_results.py
├── results/             ← E, F: raw CSV results (load test, cost)
├── figures/             ← report figures: fig_<role>_<content>.pdf/png
└── report/              ← LaTeX source mirror of the Overleaf project (A)
```

Every folder has its own `README.md` saying who owns it and what goes in it.

## Deployment order (AWS Academy Learner Lab, `us-east-1`)

Each step lists its owner. Fill the resulting ARNs into section 8 of [`docs/interface.md`](docs/interface.md).

1. **C** — S3 bucket `vericloud-raw-<suffix>` (block public access, SSE-S3, lifecycle rule on `raw/`)
2. **F** — DynamoDB table `vericloud-kyc-table` (on-demand, Streams `NEW_AND_OLD_IMAGES`); SNS topics `vericloud-kyc-topic`, `vericloud-ops-alarm`
3. **D** — SQS `vericloud-ingest-dlq`, then `vericloud-ingest-queue` with redrive (`maxReceiveCount = 3`)
4. **B / C** — Lambdas `vericloud-ocr`, `vericloud-face` (role: `LabRole`)
5. **D** — Lambda `vericloud-starter` (SQS trigger) and state machine `vericloud-kyc-workflow`
6. **A** — S3 event notification on `raw/selfie/` → `vericloud-ingest-queue`
7. **F** — Lambda `vericloud-notify` (DynamoDB Streams trigger)
8. **E** — CloudWatch dashboard `vericloud-dashboard` and alarms

Detailed step-by-step instructions are added by each owner in their folder's README as the work is done.

## Contributing rules

- Only edit the folders you own. Need a change elsewhere? Ask the owner in the group chat first.
- Commit message format: `[B] ocr: add field extraction` (role letter + area + what changed).
- **Never commit credentials**: no AWS access keys, session tokens, `.pem` files or `.env` files (they are in `.gitignore`).
- **Never commit real third-party ID documents.** Test fixtures use team members' own or synthetic samples only.
- Use the Learner Lab `LabRole`; do not create EC2 or RDS resources.

## Report

The final report is written in Overleaf (LaTeX). `report/` holds the same skeleton so it can be uploaded to Overleaf as a new project: zip the contents of `report/` and use **New Project → Upload Project**.
