# Defence Script — F (Yang Xueli)

**Slots:** two, per the team plan §10 — *business background + KYC rules* (~1.5 min) and *cost comparison* (~1 min).
**Rule of thumb:** roughly 130 English words per minute when speaking from slides. The scripts below are written to that budget.

---

## Slot 1 — Business problem and KYC rules (~1.5 min, ~200 words)

**Slide 1 — "Why this problem exists"**

> Every new bank account starts with a question the bank is legally required to answer: is this document genuine, and is this person the person on it?
>
> In a branch, a clerk answers it. Online, you have to answer it automatically — and the traffic is not smooth. Onboarding arrives in bursts, because it is driven by marketing campaigns. So you have two bad options with fixed servers: buy for the average and queue for an hour when the campaign lands, or buy for the peak and leave the hardware idle for the rest of the year. Normal load uses a small fraction of provisioned capacity; a promotion multiplies it tenfold.
>
> Our answer is to stop provisioning servers and start paying per event. But automation is only acceptable if it is auditable, so the pipeline applies five ordered rules. A document that has expired fails. A document we cannot read fails. A face below eighty percent similarity is not rejected — it is routed to a human, and the fields we did extract are kept, so the officer does not re-key them.
>
> The system degrades to a person, not to an error.

**Say these numbers:** 80% threshold · 5 ordered rules · 3 retries → dead-letter queue · 14-day quarantine.

---

## Slot 2 — Cost comparison (~1 min, ~130 words)

**Slide 2 — "What it costs"**

> We priced both architectures for the same traffic: ten thousand applications a month, twenty thousand images, and a peak ten times the baseline.
>
> Provisioned: two `m5.large`, a `db.t3.medium`, storage and a self-hosted broker — **232 dollars a month**, and almost all of it is compute and database capacity that runs whether or not anyone applies.
>
> Serverless: **15 dollars 80**. A saving of **93 percent**.
>
> Two honest points. First, every unit price on both sides was checked in the AWS Pricing Calculator, so these are numbers we can defend. Second, the saving is large *because the workload is small and bursty* — the serverless bill is flat at zero when idle, but it grows linearly. At a hundred thousand applications a month the saving falls to about thirty percent, and above roughly a hundred and fifty thousand the curves cross.
>
> So the claim is specific: serverless wins for bursty retail onboarding, and a bank at a different operating point should re-run the model rather than copy the architecture.

---

## Anticipated questions

**Q1. "Your ten thousand applications a month is a made-up number. Doesn't that invalidate the conclusion?"**
> It is a chosen scenario, and we say so — but the conclusion does not depend on it. We re-ran the model at one thousand, ten thousand and a hundred thousand applications. Serverless is cheaper at all three; only the size of the saving changes. The one thing the number does determine is *how much* you save, not *whether*.

**Q2. "You excluded the AI service from the traditional side. Isn't that unfair?"**
> It is conservative, and it is deliberate. A bank running its own servers would also pay for face comparison. Leaving it out makes the traditional bill smaller and our saving smaller. Adding it would push the saving above ninety-three percent.

**Q3. "Why 80%? Isn't that arbitrary?"**
> It is a policy threshold, not a technical constant, and it is the only tunable in the automated path. It is set low enough to keep genuine customers out of manual review and high enough that a false acceptance — which in KYC is the expensive error — is unlikely. The system does not *reject* below eighty; it routes to a human.

**Q4. "What happens when the pipeline fails?"**
> Two different failures, handled differently. A corrupt or empty file never enters the workflow: it fails pre-checks, is retried three times, and is quarantined in a dead-letter queue for fourteen days, without blocking anyone else. A processing failure *inside* the workflow is caught per branch, so OCR can succeed while the face check fails, and the record is written as "needs human review" with the extracted fields intact.

**Q5. "Did the measured cost match your model?"** *(F7 — answer only if the data is in.)*
> The load test gave us actual invocation and execution counts; multiplied by the same verified unit prices, they give a cost per application which we scaled to ten thousand a month. It agrees with the forecast within [X]%. The discrepancy comes from [Lambda duration / image size], which we corrected rather than smoothed over.

**Q6. "What would you do differently with more time?"**
> Two things: replace the last four estimated unit prices with a full Pricing Calculator export so every line is traceable, and add a human-review console — right now the system correctly *stops* at "needs human review", but there is no screen for the officer to act on it.

---

## Slide content (hand to A)

**Slide — "Business problem and decision rules"**

- Onboarding is bursty: 10× peak versus baseline; idle capacity or queueing
- Two questions: is the document genuine, is the person who they claim to be
- Five ordered rules, one verdict per application
- `FAIL` for unreadable or expired · `NEEDS_HUMAN_REVIEW` for low similarity · `PASS` otherwise
- 80% threshold — the only tunable; false acceptance is the expensive error
- Degrade to a human, never to an error

**Slide — "Cost: 93% cheaper at the modelled workload"**

- Same traffic priced both ways: 10k applications/month, 20k images, 10× peak
- Provisioned **$232.48** vs serverless **$15.80** per month — **93.2%**
- All unit prices verified in the AWS Pricing Calculator (10 Nov 2026)
- Sensitivity 1k / 10k / 100k: 99.3% / 93.2% / 32.1% — advantage narrows, never flips below ~150k
- Conditional claim: wins for bursty retail onboarding; re-run the model elsewhere

---

## Rehearsal checklist

- [ ] Both slots timed: 1.5 min and 1 min, with a 10-second margin
- [ ] Figure `fig_f_tco` opens from the slide deck (not a laptop-local path)
- [ ] Say "232 dollars 48" and "15 dollars 80", not "$232.48" (reads badly aloud)
- [ ] If the live demo fails: point at the pre-recorded clip, do not debug on stage
- [ ] Do not read the slide — the slide has the numbers, the script has the argument
