# KYC Decision Rules — Reference for B, C, D, F

**Owner:** F · Yang Xueli
**Version:** v1.0 · 2026-11-10
**Source of truth:** `docs/interface.md` v1.2, sections 5.3, 5.6 and 6. **If this file and `interface.md` ever disagree, `interface.md` wins** — this document is a working summary for implementers, not a new contract.
**Consumers:** D (Step Functions `Choice`), B (OCR), C (Face), F (notify Lambda + report section 3.3.3).

---

## 1. The decision table (evaluated in order, first match wins)

The `Choice` state in `vericloud-kyc-workflow` evaluates the five rules below **in this order** and stops at the first match.

| # | Condition on the merged state | `review_status` | `reason` | Who produces the input |
|---|---|---|---|---|
| 1 | `$.ocr.ocr_error` exists | `FAIL` | `ocr_failed` | OCR Catch handler |
| 2 | `$.ocr.id_valid == false` | `FAIL` | `id_expired` | OCR Lambda |
| 3 | `$.face.face_error` exists | `NEEDS_HUMAN_REVIEW` | `face_error` | Face Catch handler |
| 4 | `$.face.similarity < 80` | `NEEDS_HUMAN_REVIEW` | `similarity_below_80` | Face Lambda |
| 5 | none of the above | `PASS` | `auto_approved` | — |

**Why order matters.** Rule 1 comes before rule 5: a missing OCR result must never fall through to `PASS`. Rule 2 before 3/4: an expired document fails regardless of how well the face matches.

**Files that never reach this table.** Files that are zero-byte, of an unsupported format, or unreadable fail *before* the state machine starts, inside `vericloud-starter`. They are retried three times by SQS and then land in `vericloud-ingest-dlq` (14-day retention). They never enter `vericloud-kyc-table` and never produce a row, a status, or a notification.

---

## 2. Status semantics

| `review_status` | Meaning | Downstream effect |
|---|---|---|
| `PASS` | Document valid and face similarity ≥ 80 | Straight-through approval; email sent |
| `NEEDS_HUMAN_REVIEW` | Cannot be auto-decided (low similarity, no face, blurry) | Routed to a compliance officer; **all successfully extracted OCR fields are still persisted** |
| `FAIL` | Definitively rejected (OCR failed, or document expired) | Email sent; no extraction is trusted |

Partial results are never discarded silently: if OCR succeeds but the face check fails, the `ocr` object stays in the item and only `face_error` is added. This is what makes `NEEDS_HUMAN_REVIEW` useful — the officer still sees the name and (masked) ID number.

---

## 3. Notification wording (used by `vericloud-notify`)

The email is generated from the SNS message in `docs/interface.md` §5.6. Subject line:

```
[VeriCloud] Application <first 8 chars of application_id>: <review_status>
```

Body: the JSON payload only — `application_id`, `review_status`, `reason`, `processed_at`.

**Hard constraint: the email must not contain the applicant's name or ID number.** Only the application id (a UUID), the status, the reason code and the timestamp may appear. `id_number_masked` lives in DynamoDB for the compliance officer, not in email.

Suggested one-line interpretation per `reason` (for the presentation, not the code):

| `reason` | Plain-language meaning |
|---|---|
| `auto_approved` | Document valid, face matched — approved automatically |
| `similarity_below_80` | Face similarity below the 80 threshold — needs a human to compare |
| `face_error` | No usable face / unreadable image — needs a human |
| `id_expired` | Document expired — rejected |
| `ocr_failed` | Could not extract the required fields — rejected |

---

## 4. Edge cases that have already caused bugs

| Case | Required behaviour | Source |
|---|---|---|
| ID card states its validity as “长期 / 長期” (long-term) | OCR returns `expiry_date = "9999-12-31"`, `id_valid = true`; **do not throw**. Report the value as “long-term” in prose. | `interface.md` §5.3 (v1.2) |
| Face looks fine but `similarity` is missing from the payload | Treat as `face_error`, not as `PASS`. Rule 3 must fire on absence too, or add an explicit null check. | this document |
| OCR returns a partial set of fields | Missing *any* of the four required fields ⇒ throw `OcrExtractionError` ⇒ rule 1 ⇒ `FAIL`. | `interface.md` §5.3 |
| Same `application_id` processed twice | `starter` catches `ExecutionAlreadyExists` and treats it as success; the table write is an idempotent `PutItem` on the same key. | `interface.md` §5.2 |
| Notification on a status *change* (e.g. officer approves later) | Stream record must be `MODIFY` with a different `review_status`; `notify` compares `NewImage` with `OldImage`. Requires `NEW_AND_OLD_IMAGES`. | `interface.md` §4 |

---

## 5. Checklist before the demo

- [ ] All five rules are present in `kyc_workflow.asl.json`, in the order above
- [ ] `PASS` row exists in `vericloud-kyc-table` for a normal application
- [ ] `NEEDS_HUMAN_REVIEW` row still contains `name` and `id_number_masked`
- [ ] Zero-byte file appears in `vericloud-ingest-dlq`, and **no** row was written for it
- [ ] Email received for a `PASS` application contains no name and no ID number
