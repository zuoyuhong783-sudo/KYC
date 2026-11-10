#!/usr/bin/env python3
"""F7 — derive the *measured* cost per application from a load-test summary.

Reads the summary CSV produced by ``tests/collect_results.py`` (see
``results/README.md`` section 3 for its columns), multiplies the observed
volumes by the same verified unit prices used in the TCO model, and writes
``results/cost_actual.csv``.

The interesting quantity is the **cost per application**, not the total spend of
one test run: a hundred applications cost well under a dollar, so an absolute
figure is dominated by rounding. We therefore report the per-application cost and
then extrapolate it to the 10,000 applications/month baseline.

Usage
-----
    python results/compute_cost.py --summary results/load_test_r1_summary.csv
    python results/compute_cost.py --summary results/load_test_r1_summary.csv \
        --out results/cost_actual.csv --baseline 10000

Only clearly-identified estimates are used; every price below is the value
verified against the AWS Pricing Calculator on 2026-11-10 (see
``results/tco_estimate.csv``).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

# ---- unit prices, us-east-1, on-demand, USD (verified 2026-11-10) ----
PRICE = {
    "s3_put": 0.000005,            # per PUT request
    "lambda_request": 0.0000002,   # per invocation
    "lambda_gbs": 0.0000166667,    # per GB-second
    "sfn_transition": 0.000025,    # per state transition
    "dynamodb_wru": 0.00000125,    # per write request unit
    "rekognition_image": 0.001,    # per CompareFaces call
    "sns_email": 0.00002,          # per notification
}

# ---- per-application assumptions measured on one execution ----
OCR_GBS = 1.0 * 3.0      # 1024 MB x 3 s
FACE_GBS = 0.5 * 1.5     # 512 MB x 1.5 s
STARTER_GBS = 0.128 * 0.3
NOTIFY_GBS = 0.128 * 0.1
TRANSITIONS_PER_EXECUTION = 12


def _num(row: dict, key: str, default: float = 0.0) -> float:
    """Read a numeric field from the summary row, tolerating blanks and '12/20'."""
    raw = (row.get(key) or "").strip()
    if not raw:
        return default
    if "/" in raw:                       # e.g. dlq_corrupted = "20/20"
        raw = raw.split("/")[0]
    try:
        return float(raw)
    except ValueError:
        return default


def compute(submitted: float, in_table: float) -> list[tuple[str, float, float, float]]:
    """Return (item, quantity, unit_price, cost_usd) rows for the observed run."""
    s3_puts = submitted * 2                      # id card + selfie
    lambda_requests = submitted * 4              # starter + ocr + face + notify
    lambda_gbs = submitted * (OCR_GBS + FACE_GBS + STARTER_GBS + NOTIFY_GBS)
    transitions = in_table * TRANSITIONS_PER_EXECUTION
    writes = in_table * 2                        # ~2 WRU per item
    comparisons = in_table
    emails = in_table

    return [
        ("S3 PUT requests", s3_puts, PRICE["s3_put"]),
        ("Lambda invocations", lambda_requests, PRICE["lambda_request"]),
        ("Lambda compute (GB-s)", lambda_gbs, PRICE["lambda_gbs"]),
        ("Step Functions transitions", transitions, PRICE["sfn_transition"]),
        ("DynamoDB writes (WRU)", writes, PRICE["dynamodb_wru"]),
        ("Rekognition CompareFaces", comparisons, PRICE["rekognition_image"]),
        ("SNS notifications", emails, PRICE["sns_email"]),
    ]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summary", required=True, help="load_test_*_summary.csv from E")
    ap.add_argument("--out", default="results/cost_actual.csv")
    ap.add_argument("--baseline", type=float, default=10000.0,
                    help="applications/month to extrapolate to (default 10000)")
    args = ap.parse_args(argv[1:])

    if not os.path.exists(args.summary):
        print(f"error: {args.summary} not found. F7 depends on E's load test (task E6).",
              file=sys.stderr)
        return 2

    with open(args.summary, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print(f"error: {args.summary} has no data rows", file=sys.stderr)
        return 2
    row = rows[0]

    submitted = _num(row, "submitted")
    in_table = _num(row, "in_table")
    if submitted <= 0:
        print("error: 'submitted' is zero or missing in the summary", file=sys.stderr)
        return 2

    items = compute(submitted, in_table)
    total = sum(qty * price for _, qty, price in items)
    per_app = total / submitted
    projected = per_app * args.baseline

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "quantity", "unit", "unit_price_usd", "cost_usd", "note"])
        for name, qty, price in items:
            w.writerow([name, round(qty, 2), "", price, round(qty * price, 6),
                        "observed run"])
        w.writerow(["TOTAL", "", "", "", round(total, 6),
                    f"{submitted:.0f} applications"])
        w.writerow(["cost_per_application_usd", "", "", "", round(per_app, 6), ""])
        w.writerow([f"projected_monthly_usd_at_{int(args.baseline)}", "", "", "",
                    round(projected, 2), "extrapolated"])

    print(f"applications in run : {submitted:.0f}")
    print(f"applications in table: {in_table:.0f}")
    print(f"total cost of run   : ${total:.6f}")
    print(f"cost per application: ${per_app:.6f}")
    print(f"projected / month   : ${projected:.2f}  (at {args.baseline:.0f} applications)")
    print(f"written -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
