#!/usr/bin/env python3
"""
sessions.py — shared in-memory session store untuk webmail.

Dipisah dari webmail.py supaya api.py (JSON API untuk SPA Cloud-Mail style)
dan webmail.py (UI lama /classic) memakai store yang sama.
"""

import threading
import time
import uuid

SESSION_TTL = 8 * 3600

SESSIONS = {}
LOCK = threading.Lock()

COOKIE_NAME = "webmail_session"


def secure_flag(headers):
    """'; Secure' hanya kalau request datang lewat TLS terdepan (Caddy)."""
    proto = (headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return "; Secure" if proto == "https" else ""


def new_session(user, password, display=None):
    tok = uuid.uuid4().hex + uuid.uuid4().hex
    with LOCK:
        SESSIONS[tok] = {
            "user": user,
            "password": password,
            "display": display or user.split("@")[0],
            "ts": time.time(),
            "csrf": uuid.uuid4().hex,
        }
    return tok


def get_session(tok):
    if not tok:
        return None
    with LOCK:
        s = SESSIONS.get(tok)
        if not s:
            return None
        if time.time() - s["ts"] > SESSION_TTL:
            SESSIONS.pop(tok, None)
            return None
        s["ts"] = time.time()
        return s


def drop_session(tok):
    with LOCK:
        SESSIONS.pop(tok, None)
