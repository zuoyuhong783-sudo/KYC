# `lambda/notify/`

**Owner:** F · Yang Xueli · Task **F4**

`vericloud-notify` is triggered by the `vericloud-kyc-table` DynamoDB Stream and
publishes an Amazon SNS email whenever `review_status` is **created** or
**changed**. It never includes the applicant's name or ID number.

**Contract:** `docs/interface.md` v1.2 §4 (table + stream) and §5.6 (SNS message).
Do not invent new field names.

---

## Files

| File | Purpose |
|---|---|
| `handler.py` | The Lambda. Entry point `lambda_handler(event, context)` |
| `test_handler.py` | Unit tests with a fake SNS client (no AWS needed) |
| `samples/stream_insert.json` | A real-shaped DynamoDB Stream `INSERT` event |
| `samples/expected_sns.json` | The SNS `publish` call the handler should make |

## Configuration

| Setting | Value |
|---|---|
| Runtime | Python 3.12 |
| Handler | `handler.lambda_handler` |
| Timeout | 30 s |
| Environment variable | `SNS_TOPIC_ARN` = ARN of `vericloud-kyc-topic` |
| Execution role | `LabRole` (Learner Lab) |
| Trigger | DynamoDB stream of `vericloud-kyc-table` |
| **Batch size** | **1** — keep it at 1, otherwise one bad record blocks the whole shard |
| Starting position | `LATEST` |
| Retry attempts | 3 (default), then fail — the stream is the source of truth, so a missed email is recoverable from the table |

### Why batch size 1

With the default batch of 100, a single malformed record makes Lambda fail the
entire batch, which is retried as a whole and blocks the shard. For a
notification worker the per-record cost is negligible, so 1 is both safer and
easier to explain in the report.

## Deploy (manual, Learner Lab)

1. Create the function `vericloud-notify`, runtime Python 3.12, role `LabRole`.
2. Paste `handler.py` into the console editor (there are no third-party
   dependencies — `boto3` ships with the runtime).
3. Set `SNS_TOPIC_ARN` in *Configuration → Environment variables*.
4. *Configuration → Triggers → Add trigger → DynamoDB*: pick
   `vericloud-kyc-table`, batch size **1**, starting position `LATEST`.
5. Write one item to the table by hand and confirm an email arrives.

## Test locally

```bash
python -m pytest lambda/notify/test_handler.py -v
```

The tests do not touch AWS: `handler._sns_client` is replaced with a fake, and
`SNS_TOPIC_ARN` is set with `monkeypatch`.

## What to screenshot for the report (F4 deliverable)

1. The Lambda trigger configuration showing the DynamoDB stream and batch size 1.
2. The environment variable `SNS_TOPIC_ARN`.
3. **A received email** — save as `figures/fig_f_email.png`, with the mailbox
   address blurred out. It must show the `[VeriCloud] Application xxxxxxxx: PASS`
   subject and the four-field JSON body, and no name/ID.
