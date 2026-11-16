"""Load test through the public vericloud-api: no AWS credentials needed.

Written by A on behalf of E, so anyone in the team can run the load test without
holding the demo account's keys. Same idea as tests/load_test.py (E2), but the
upload links come from POST /applications and the results from
GET /applications/<id>/trace (interface v1.5 §5.7).

    python tests/load_test_api.py --api https://xxxx.execute-api.us-east-1.amazonaws.com \
        --count 100 --duration 60 --bad-ratio 0.2 --out results/load_test_api_r1

Images: by default synthetic ones are generated (ID front with name/number, ID
back with authority/validity, a selfie without a real face, so valid cases end as
NEEDS_HUMAN_REVIEW / face_error). Pass --front/--back/--selfie to use your own.
Bad applications upload a selfie truncated to 35 % (pre-check must reject it).

Output: <out>.csv (one row per application) and <out>_summary.json.
Latencies use AWS-side clocks only: created_at (S3 eventTime), received_at
(starter), processed_at (state machine), so the tester's clock does not matter.
"""

import argparse
import io
import json
import random
import statistics
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------- images
def _font(size):
    for name in ("msyh.ttc", "simhei.ttf", "NotoSansCJK-Regular.ttc", "wqy-microhei.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _card(lines, banner):
    img = Image.new("RGB", (1000, 630), (236, 240, 244))
    d = ImageDraw.Draw(img)
    d.text((40, 20), banner, fill=(180, 40, 40), font=_font(26))
    for i, line in enumerate(lines):
        d.text((60, 110 + i * 78), line, fill=(20, 20, 20), font=_font(38))
    out = io.BytesIO(); img.save(out, "JPEG", quality=92); return out.getvalue()


def synthetic_images():
    front = _card(["姓名 测试甲", "性别 男  民族 汉", "出生 2000年1月1日", "住址 测试市测试区测试路1号",
                   "公民身份号码 000000200001011234"], "SYNTHETIC TEST - NOT AN ID DOCUMENT")
    back = _card(["中华人民共和国", "居民身份证", "签发机关 测试市公安局", "有效期限 2020.01.01-2040.01.01"],
                 "SYNTHETIC TEST - NOT AN ID DOCUMENT")
    selfie_img = Image.new("RGB", (600, 800), (210, 200, 190))
    ImageDraw.Draw(selfie_img).text((40, 380), "SYNTHETIC SELFIE", fill=(60, 60, 60), font=_font(40))
    out = io.BytesIO(); selfie_img.save(out, "JPEG", quality=90)
    return front, back, out.getvalue()


# ---------------------------------------------------------------- HTTP
def _req(method, url, body=None, headers=None, timeout=30):
    r = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def submit(api, front, back, selfie, bad):
    app_id = str(uuid.uuid4())
    row = {"application_id": app_id, "kind": "bad" if bad else "valid", "t_start": time.time()}
    st, body = _req("POST", api + "/applications", json.dumps({
        "application_id": app_id, "id_card_extension": ".jpg",
        "id_card_back_extension": ".jpg", "selfie_extension": ".jpg"}).encode(),
        {"Content-Type": "application/json"})
    if st != 200:
        row["error"] = f"create {st}"; return row
    urls = json.loads(body)
    selfie_body = selfie[: int(len(selfie) * 0.35)] if bad else selfie
    for key, data in (("id_card_url", front), ("id_card_back_url", back), ("selfie_url", selfie_body)):
        st, _ = _req("PUT", urls[key], data, timeout=60)
        if st != 200:
            row["error"] = f"put {key} {st}"; return row
    row["t_uploaded"] = time.time()
    return row


def finish(api, row, wait_s):
    """Poll until the application has a result (valid) or wait_s has passed."""
    if "error" in row:
        return row
    deadline = row["t_uploaded"] + wait_s
    while time.time() < deadline:
        st, body = _req("GET", f"{api}/applications/{row['application_id']}/trace")
        if st == 200:
            tr = json.loads(body)
            res, ex = tr.get("result"), tr.get("execution")
            row["execution"] = ex["status"] if ex else None
            if res:
                c, r, p = _iso(res.get("created_at")), _iso(res.get("received_at")), _iso(res.get("processed_at"))
                row.update(status=res["review_status"], reason=res["reason"],
                           queue_start_s=round((r - c).total_seconds(), 3) if c and r else None,
                           workflow_s=round((p - r).total_seconds(), 3) if r and p else None,
                           end_to_end_s=round((p - c).total_seconds(), 3) if c and p else None)
                return row
            if row["kind"] == "bad" and time.time() > row["t_uploaded"] + 45 and not ex:
                return row     # rejected at the pre-check: no workflow, as expected
        time.sleep(3)
    row["timeout"] = True
    return row


def pct(values, q):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = max(0, min(len(v) - 1, round(q / 100 * (len(v) - 1))))
    return round(v[k], 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--duration", type=float, default=60, help="seconds over which submissions are spread")
    ap.add_argument("--bad-ratio", type=float, default=0.2)
    ap.add_argument("--burst", action="store_true", help="submit everything at once instead of spreading")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--wait", type=float, default=240, help="max seconds to wait for each result")
    ap.add_argument("--front"); ap.add_argument("--back"); ap.add_argument("--selfie")
    ap.add_argument("--out", default=f"results/load_test_api_{int(time.time())}")
    a = ap.parse_args()
    api = a.api.rstrip("/")

    front, back, selfie = synthetic_images()
    if a.front: front = open(a.front, "rb").read()
    if a.back: back = open(a.back, "rb").read()
    if a.selfie: selfie = open(a.selfie, "rb").read()

    n_bad = round(a.count * a.bad_ratio)
    kinds = [True] * n_bad + [False] * (a.count - n_bad)
    random.shuffle(kinds)
    gap = 0 if a.burst else a.duration / max(1, a.count)
    print(f"{a.count} applications ({n_bad} bad), {'burst' if a.burst else f'one every {gap:.2f} s'}, api {api}")

    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as pool:
        futures = []
        for i, bad in enumerate(kinds):
            delay = t0 + i * gap - time.time()
            if delay > 0: time.sleep(delay)
            futures.append(pool.submit(submit, api, front, back, selfie, bad))
        rows = [f.result() for f in futures]
    print(f"submitted in {time.time() - t0:.1f} s; waiting for results …")
    with ThreadPoolExecutor(a.workers) as pool:
        rows = list(pool.map(lambda r: finish(api, r, a.wait), rows))

    valid = [r for r in rows if r["kind"] == "valid"]
    bad = [r for r in rows if r["kind"] == "bad"]
    summary = {
        "submitted": len(rows), "valid": len(valid), "bad": len(bad),
        "submit_errors": sum(1 for r in rows if "error" in r),
        "valid_with_result": sum(1 for r in valid if r.get("status")),
        "valid_timeouts": sum(1 for r in valid if r.get("timeout")),
        "bad_rejected_no_workflow": sum(1 for r in bad if not r.get("execution") and not r.get("status") and "error" not in r),
        "bad_wrongly_processed": sum(1 for r in bad if r.get("status")),
        "status_counts": {s: sum(1 for r in valid if r.get("status") == s) for s in ("PASS", "NEEDS_HUMAN_REVIEW", "FAIL")},
        "reason_counts": {},
        "latency_s": {k: {"p50": pct([r.get(k) for r in valid], 50), "p95": pct([r.get(k) for r in valid], 95),
                          "p99": pct([r.get(k) for r in valid], 99), "max": pct([r.get(k) for r in valid], 100)}
                      for k in ("queue_start_s", "workflow_s", "end_to_end_s")},
        "mode": "burst" if a.burst else "uniform", "duration_s": a.duration,
        "run_at": datetime.now().isoformat(timespec="seconds"),
    }
    for r in valid:
        if r.get("reason"): summary["reason_counts"][r["reason"]] = summary["reason_counts"].get(r["reason"], 0) + 1
    _, dash = _req("GET", api + "/dashboard")
    try: summary["queues_after"] = json.loads(dash).get("queues")
    except ValueError: pass

    import csv, os
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    cols = ["application_id", "kind", "status", "reason", "execution", "queue_start_s", "workflow_s", "end_to_end_s", "timeout", "error"]
    with open(a.out + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    with open(a.out + "_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
