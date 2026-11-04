#!/usr/bin/env python3
"""
otp_lab.py — OTP request-path abuse lab for YOUR OWN service.

Fires controlled bursts of OTP-request traffic at an endpoint you own and
reports whether the rate limiter actually holds. Two axes are tested:

  same-phone     one identifier, N requests   -> tests per-number throttle
                 (this is the axis that matters when someone floods a single
                  victim: if this leaks, the endpoint can be used as a weapon)
  unique-phones  N identifiers, one source     -> tests per-IP / per-device throttle

Refuses to run without --confirm-owned. Hard cap on request volume.

Usage:
    python3 otp_lab.py \
        --url https://api.mysite.com/auth/otp/request \
        --body '{"phone":"{phone}"}' \
        --header 'Content-Type: application/json' \
        --header 'Authorization: Bearer $TOKEN' \
        --mode same-phone --phone +6281100000001 \
        --requests 30 --concurrency 10 \
        --confirm-owned

Exit codes: 0 = limiter held, 1 = limiter ineffective, 2 = bad usage.
"""

import argparse
import json
import math
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    sys.exit("need requests: pip install requests")

MAX_REQUESTS = 2000
DEFAULT_TIMEOUT = 15

# Digits under a suggestive JSON key. Strong signal: the server handed the code
# back to the caller. Bare digits are deliberately not matched — timestamps,
# ids and counters drown the signal, and a noisy check gets ignored.
OTP_RE = re.compile(r'"(?:otp|code|token|pin|passcode)"\s*:\s*"?(\d{3,8})"?', re.I)


class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.rows = []

    def add(self, row):
        with self.lock:
            self.rows.append(row)


_local = threading.local()


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": "otp-ratelimit-lab/1.0 (own-service test)"})
        _local.s = s
    return s


def build_phone(args, i):
    if args.phone:
        return args.phone
    return f"{args.phone_prefix}{args.phone_start + i:04d}"


def fire(args, i, rec):
    phone = build_phone(args, i)
    body = args.body.replace("{phone}", phone).replace("{i}", str(i)).replace(
        "{nonce}", f"{int(time.time() * 1000)}-{i}"
    )
    headers = dict(args.parsed_headers)
    t0 = time.perf_counter()
    err = None
    status = None
    text = ""
    rl_header = None
    try:
        r = session().request(
            args.method,
            args.url,
            data=body.encode() if body else None,
            headers=headers,
            timeout=args.timeout,
            allow_redirects=False,
        )
        status = r.status_code
        text = r.text[:4000]
        rl_header = r.headers.get("Retry-After") or r.headers.get("X-RateLimit-Remaining")
    except requests.RequestException as e:
        err = f"{type(e).__name__}: {e}"[:200]
    dt = (time.perf_counter() - t0) * 1000.0
    rec.add(
        {
            "i": i,
            "phone": phone,
            "status": status,
            "ms": round(dt, 1),
            "len": len(text),
            "retry_after": rl_header,
            "err": err,
            "otp_leak": detect_otp_leak(text) if status and status < 400 else None,
            "body_head": text[:120] if status and status >= 400 else None,
        }
    )


def detect_otp_leak(text):
    """Flag OTP-shaped material in a response body.

    'json-key' = digits sitting under a key named otp/code/token/pin/passcode.
    That is unambiguous: the server is handing the code back to the caller.
    Bare digits are NOT flagged here — too noisy (timestamps, ids, counters).
    """
    if not text:
        return None
    m = OTP_RE.search(text)
    if m:
        return {"value": m.group(1), "how": "json-key"}
    return None


def pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    k = max(0, min(len(vals) - 1, int(math.ceil(p / 100.0 * len(vals))) - 1))
    return vals[k]


def analyse(args, rows, elapsed):
    ok = [r for r in rows if r["status"] is not None and r["status"] < 400]
    limited = [r for r in rows if r["status"] in (429, 403, 401)]
    errs = [r for r in rows if r["status"] is None]
    server_err = [r for r in rows if r["status"] and r["status"] >= 500]
    lat = [r["ms"] for r in rows if r["status"] is not None]

    # Lowest submission index that got blocked. Arrival order differs under
    # concurrency, so this answers "did a limiter exist", not "how fast".
    first_429 = min((r["i"] for r in rows if r["status"] in (429, 403)), default=None)

    leaks = [r for r in rows if r.get("otp_leak")]
    leak_strong = [r for r in leaks if r["otp_leak"]["how"] == "json-key"]

    # Per-phone repeats: in same-phone mode, how many 2xx did one number get?
    per_phone = {}
    for r in ok:
        per_phone[r["phone"]] = per_phone.get(r["phone"], 0) + 1
    worst_phone = max(per_phone.items(), key=lambda kv: kv[1]) if per_phone else (None, 0)

    if errs and len(errs) == len(rows):
        verdict = "INCONCLUSIVE"
        reason = "every request errored at transport level; endpoint unreachable or blocked"
    elif not limited and len(ok) >= max(5, int(0.5 * len(rows))):
        verdict = "FAIL"
        reason = f"{len(ok)}/{len(rows)} requests accepted, zero throttling observed"
    elif limited:
        verdict = "PASS"
        reason = f"{len(limited)}/{len(rows)} throttled, first block at request #{first_429}"
    else:
        verdict = "WEAK"
        reason = "mixed results, no clean limiter signature"

    return {
        "verdict": verdict,
        "reason": reason,
        "mode": args.mode,
        "url": args.url,
        "requests": len(rows),
        "accepted_2xx": len(ok),
        "throttled_429_403_401": len(limited),
        "server_5xx": len(server_err),
        "transport_errors": len(errs),
        "first_throttle_at_index": first_429,
        "max_accepts_single_identifier": {"phone": worst_phone[0], "count": worst_phone[1]} if worst_phone else None,
        "otp_leaked_in_response": {
            "strong": len(leak_strong),
            "weak": len(leaks) - len(leak_strong),
            "samples": [(r["otp_leak"]["value"], r["otp_leak"]["how"]) for r in leaks[:3]],
        },
        "latency_ms": {
            "p50": pct(lat, 50), "p95": pct(lat, 95), "p99": pct(lat, 99),
            "mean": round(statistics.mean(lat), 1) if lat else None,
            "max": max(lat) if lat else None,
        },
        "throughput_rps": round(len(rows) / elapsed, 2) if elapsed > 0 else None,
        "elapsed_s": round(elapsed, 2),
        "status_histogram": {str(k): sum(1 for r in rows if r["status"] == k)
                             for k in sorted({r["status"] for r in rows if r["status"]})},
    }


def print_report(rep):
    L = []
    L.append("=" * 62)
    L.append(f"VERDICT: {rep['verdict']}  —  {rep['reason']}")
    L.append("=" * 62)
    L.append(f"mode={rep['mode']}   url={rep['url']}")
    L.append(f"sent={rep['requests']}  accepted={rep['accepted_2xx']}  "
             f"throttled={rep['throttled_429_403_401']}  5xx={rep['server_5xx']}  "
             f"transport_err={rep['transport_errors']}")
    L.append(f"status histogram: {rep['status_histogram']}")
    if rep["max_accepts_single_identifier"]:
        m = rep["max_accepts_single_identifier"]
        L.append(f"worst identifier: {m['phone']} -> {m['count']} accepted requests")
    lm = rep["latency_ms"]
    L.append(f"latency ms: p50={lm['p50']} p95={lm['p95']} p99={lm['p99']} max={lm['max']}")
    L.append(f"throughput: {rep['throughput_rps']} req/s over {rep['elapsed_s']}s")
    ol = rep["otp_leaked_in_response"]
    if ol["strong"] or ol["weak"]:
        L.append(f"!! OTP MATERIAL IN RESPONSE BODY: strong={ol['strong']} weak={ol['weak']}")
        for v, how in ol["samples"]:
            masked = v[:-2] + "**"
            L.append(f"   sample ({how}): {masked}")
    else:
        L.append("OTP leak check: clean (no code material in response bodies)")
    L.append("")
    if rep["verdict"] == "FAIL":
        L.append("FIX PRIORITY:")
        if rep["mode"] == "same-phone":
            L.append("  per-identifier throttle missing/absent -> cap requests per phone,")
            L.append("  sliding window (e.g. 3 per 15min), then exponential cooldown.")
            L.append("  Also force OTP invalidation: a new OTP must void the previous one.")
        else:
            L.append("  per-IP throttle missing -> token bucket per IP + per /24,")
            L.append("  plus device attestation (Play Integrity / App Attest) on request.")
    elif rep["verdict"] == "PASS":
        L.append("Limiter responded under burst. Re-run at higher concurrency to find the ceiling.")
    print("\n".join(L))


def main():
    p = argparse.ArgumentParser(description="OTP request-path abuse lab (own service only)")
    p.add_argument("--url", required=True)
    p.add_argument("--method", default="POST")
    p.add_argument("--body", default='{"phone":"{phone}"}')
    p.add_argument("--header", action="append", default=[], metavar="KEY:VALUE")
    p.add_argument("--mode", choices=["same-phone", "unique-phones"], default="same-phone")
    p.add_argument("--phone", help="fixed identifier for same-phone mode")
    p.add_argument("--phone-prefix", default="+6281100000")
    p.add_argument("--phone-start", type=int, default=1)
    p.add_argument("--requests", type=int, default=30)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    p.add_argument("--out", default="otp_lab_report.json")
    p.add_argument("--confirm-owned", action="store_true",
                   help="assert you own/operate the target endpoint")
    args = p.parse_args()

    if not args.confirm_owned:
        sys.exit("refusing to run without --confirm-owned (this tool is for your own endpoint)")
    if args.requests > MAX_REQUESTS:
        sys.exit(f"refusing: --requests {args.requests} exceeds hard cap {MAX_REQUESTS}")
    if args.mode == "same-phone" and not args.phone:
        sys.exit("--mode same-phone needs --phone")
    if args.mode == "unique-phones" and args.phone:
        sys.exit("--mode unique-phones with --phone would repeat one identifier; "
                 "drop --phone or use --mode same-phone")
    if args.concurrency < 1 or args.concurrency > 200:
        sys.exit("--concurrency must be 1..200")

    args.parsed_headers = {}
    for h in args.header:
        if ":" not in h:
            sys.exit(f"bad --header (need KEY:VALUE): {h}")
        k, v = h.split(":", 1)
        args.parsed_headers[k.strip()] = v.strip()

    rec = Recorder()
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(fire, args, i, rec) for i in range(args.requests)]
        for _ in as_completed(futs):
            pass
    elapsed = time.perf_counter() - t0

    rows = sorted(rec.rows, key=lambda r: r["i"])
    rep = analyse(args, rows, elapsed)
    rep["raw"] = rows
    print_report(rep)
    with open(args.out, "w") as f:
        json.dump(rep, f, indent=2)
    print(f"\nfull report -> {args.out}")
    sys.exit(0 if rep["verdict"] in ("PASS", "INCONCLUSIVE") else 1)


if __name__ == "__main__":
    main()
