# AWS console steps — F1, F3, F4 (Yang Xueli)

Everything in this file has to be clicked by you, in your Learner Lab account,
region **us-east-1**. The code and the report text are already in the repo; these
are the console operations that turn them into evidence.

Do them in this order — F4 needs the table from F1 and the topic from F3.

> Before you start: open the Learner Lab, click **Start Lab**, wait for the green
> dot, then click **AWS** to open the console. Check the region selector in the
> top-right says **N. Virginia (us-east-1)**.

---

## F1 — DynamoDB table `vericloud-kyc-table`

1. Console → search **DynamoDB** → **Create table**
2. **Table name**: `vericloud-kyc-table`
3. **Partition key**: `application_id`, type **String**
4. Leave the **sort key** empty
5. **Table settings**: choose **Customize settings**
6. **Capacity mode**: **On-demand**
7. **Create table**, and wait until the status is *Active*

Then turn on the stream:

8. Open the table → **Exports and streams** tab
9. **Stream details** → **Turn on**
10. View type: **New and old images**
11. **Turn on stream**

**Screenshots** → `screenshots/`:
- `1_dynamodb_table_F.png` — the table overview showing `application_id` as partition key and *On-demand*
- `1_dynamodb_stream_F.png` — the stream panel showing *New and old images*

---

## F3 — SNS topics and email subscription

### Topic 1: applicant notifications

1. Console → search **Simple Notification Service** → **Topics** → **Create topic**
2. Type: **Standard**; **Name**: `vericloud-kyc-topic`
3. **Create topic**
4. On the topic page → **Subscriptions** → **Create subscription**
5. **Protocol**: **Email**; **Endpoint**: your own email address
6. **Create subscription**
7. **Open your inbox** and click **Confirm subscription**. Until you do, publish
   succeeds but no mail arrives — this is the single most common way this step
   appears to "work" while silently failing.
8. Copy the topic **ARN** (top of the topic page) — F4 needs it

### Topic 2: operational alarms (used by E)

9. Repeat 1–3 with **Name**: `vericloud-ops-alarm`
10. Subscribe your email and confirm as above
11. Copy the **ARN** and send it to E (they configure the CloudWatch alarm)

**Screenshots** → `screenshots/`:
- `3_sns_topics_F.png` — both topics in the list
- `3_sns_subscription_F.png` — the **Confirmed** status next to your email

**Also:** fill the two ARNs into `docs/interface.md` §8 (rows
`vericloud-kyc-topic` and `vericloud-ops-alarm`).

---

## F4 — Lambda `vericloud-notify`

1. Console → **Lambda** → **Create function** → **Author from scratch**
2. **Function name**: `vericloud-notify`
3. **Runtime**: **Python 3.12**
4. **Permissions**: *Use an existing role* → **`LabRole`**
5. **Create function**
6. In the **Code** tab, delete the placeholder and paste the contents of
   `lambda/notify/handler.py` (in the repo). Click **Deploy**.
7. **Configuration → Environment variables → Edit → Add**:
   key `SNS_TOPIC_ARN`, value = the ARN of `vericloud-kyc-topic` from F3
8. **Configuration → General configuration → Edit**: timeout **30 s** (default 3 s is fine for a demo, 30 s is safer)
9. **Configuration → Triggers → Add trigger → DynamoDB**:
   - Table: `vericloud-kyc-table`
   - **Batch size: 1** ← keep this at 1
   - Starting position: **Latest**
10. **Test** the function before wiring it up:
    - **Test** tab → *Create new event* → paste `lambda/notify/samples/stream_insert.json`
    - Run it. Expect `{"published": 1}` in the response **and an email in your inbox**

**Screenshots** → `screenshots/`:
- `4_notify_trigger_F.png` — the trigger showing the stream and batch size 1
- `4_notify_env_F.png` — the `SNS_TOPIC_ARN` environment variable
- `figures/fig_f_email.png` — **the received email**, with your address blurred.
  It must show the subject `[VeriCloud] Application 3f2b7c1e: PASS` and a body
  containing only the four JSON fields — no name, no ID number.

**Also:** fill the `vericloud-notify` ARN into `docs/interface.md` §8.

---

## After the console work

```bash
git add docs/interface.md          # if you filled in the ARNs
git add screenshots/               # only if you keep them in the repo
git commit -m "[F] aws: record SNS/DynamoDB/notify deployment info"
git push
```

If the screenshots are kept on the shared drive instead of the repo, skip that
line — the plan puts them on the shared drive and only uploads the ones used in
the report to Overleaf's `figures/`.

---

## Checklist

- [ ] F1 table created, on-demand, stream = new and old images
- [ ] F3 both topics created, **both subscriptions confirmed by email**
- [ ] F4 function created, code deployed, `SNS_TOPIC_ARN` set, trigger batch size 1
- [ ] F4 test event produces `{"published": 1}`
- [ ] A real email arrived (this is the F4 evidence)
- [ ] Screenshots taken and named per `docs/interface.md` §12.5
- [ ] ARNs written into `docs/interface.md` §8
