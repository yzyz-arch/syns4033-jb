#!/usr/bin/env python3
"""
mock_otp_server.py — three OTP endpoints with different limiter behaviour,
so the lab has a known-good baseline to measure against.

  POST /otp/request?mode=none          no limiter at all      (expect FAIL)
  POST /otp/request?mode=ipwindow      per-IP fixed window    (expect PASS)
  POST /otp/request?mode=leaky         per-IP limit but echoes the OTP (expect leak)

  POST /otp/reset                      clear counters

stdlib only.  python3 mock_otp_server.py --port 8899
"""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
IP_HITS = {}          # ip -> [timestamps]
PHONE_HITS = {}       # phone -> [timestamps]
WINDOW_S = 60
IP_MAX = 5
PHONE_MAX = 3


def sliding(bucket, key, limit, now):
    ts = [t for t in bucket.get(key, []) if now - t < WINDOW_S]
    allowed = len(ts) < limit
    if allowed:
        ts.append(now)
    bucket[key] = ts
    retry = int(WINDOW_S - (now - ts[0])) if (not allowed and ts) else 0
    return allowed, retry


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def _send(self, code, obj, extra=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {}
        phone = str(payload.get("phone", ""))
        now = time.time()

        if self.path.startswith("/otp/reset"):
            with LOCK:
                IP_HITS.clear()
                PHONE_HITS.clear()
            return self._send(200, {"reset": True})

        if not self.path.startswith("/otp/request"):
            return self._send(404, {"error": "not_found"})

        mode = "ipwindow"
        if "mode=" in self.path:
            mode = self.path.split("mode=", 1)[1].split("&", 1)[0]

        if mode == "none":
            return self._send(200, {"ok": True, "sent": True, "mode": mode})

        with LOCK:
            ok_ip, retry_ip = sliding(IP_HITS, self.client_address[0], IP_MAX, now)
            ok_phone, retry_phone = sliding(PHONE_HITS, phone, PHONE_MAX, now)

        if not ok_phone:
            return self._send(429, {"error": "too_many_requests", "scope": "phone"},
                              {"Retry-After": str(max(1, retry_phone))})
        if not ok_ip:
            return self._send(429, {"error": "too_many_requests", "scope": "ip"},
                              {"Retry-After": str(max(1, retry_ip))})

        if mode == "leaky":
            code = f"{int(now * 1000) % 1000000:06d}"
            return self._send(200, {"ok": True, "sent": True, "otp": code})

        return self._send(200, {"ok": True, "sent": True, "mode": mode})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print(f"mock OTP server on http://{a.host}:{a.port}  "
          f"(ip_max={IP_MAX}/{WINDOW_S}s, phone_max={PHONE_MAX}/{WINDOW_S}s)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
