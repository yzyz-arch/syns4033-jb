"""Prove the balancer rotates, backs off on 429 and fails over — against a mock
endpoint spun up by this test (no real keys, no manual setup).

Runnable two ways:
  pytest a3-farm/tests/test_balancer.py
  python a3-farm/tests/test_balancer.py
"""
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --- mock Gemini endpoint (429 on odd hit per key, 200 on even) ---
SEEN: dict[str, int] = defaultdict(int)


class _Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_POST(self):
        from urllib.parse import parse_qs, urlparse
        key = (parse_qs(urlparse(self.path).query).get("key") or [""])[0]
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        SEEN[key] += 1
        if SEEN[key] % 2 == 1:
            code, body = 429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}
        else:
            code, body = 200, {"candidates": [{"content": {"parts": [{"text": "pong:" + key[-4:]}]}}],
                               "usageMetadata": {"totalTokenCount": 3}}
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_rotation_backoff_failover():
    import core.config as cfg
    port = _free_port()
    base = f"http://127.0.0.1:{port}/v1beta/models"
    cfg.GENERATE_URL = base + "/{model}:generateContent"

    import core.balancer as bal
    bal.GENERATE_URL = cfg.GENERATE_URL
    from core.balancer import KeyPool

    srv = ThreadingHTTPServer(("127.0.0.1", port), _Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # let the listener come up
    for _ in range(40):
        try:
            urllib.request.urlopen(f"{base}?key=probe", timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)

    events: list[dict] = []
    raw: list[str | None] = []
    pool = KeyPool(["KEYAAAA1", "KEYBBBB2", "KEYCCCC3"], models=["mock-model"],
                   cooldown_quota=2.0, on_event=events.append)
    _orig = pool._next_key
    pool._next_key = lambda now: (raw.append(_orig(now)) or raw[-1])  # spy raw key

    try:
        oks = sum(1 for _ in range(6) if pool.generate("ping")["ok"])
        health = pool.health()
    finally:
        srv.shutdown()

    quota = [e for e in events if e.get("event") == "quota"]
    distinct = {k for k in raw if k}

    assert oks >= 3, f"expected >=3 successful calls, got {oks}"
    assert len(quota) >= 2, f"expected 429s observed/penalized, got {len(quota)}"
    assert len(distinct) >= 2, f"expected rotation across >=2 keys, saw {distinct}"
    assert health["in_cooldown"] >= 1, "expected at least one key in cooldown"
    print(f"PASS: oks={oks} quota_events={len(quota)} keys={sorted(distinct)} "
          f"in_cooldown={health['in_cooldown']}")


def test_proxy_over_pool():
    """POST /v1/chat/completions through the pool against the mock."""
    import core.config as cfg
    port = _free_port()
    srv_port = _free_port()
    base = f"http://127.0.0.1:{port}/v1beta/models"

    import core.balancer as bal
    import core.server as srv
    bal.GENERATE_URL = base + "/{model}:generateContent"
    srv._POOL = bal.KeyPool(["PK1", "PK2", "PK3"], models=["mock-model"], cooldown_quota=2.0)

    gemini = ThreadingHTTPServer(("127.0.0.1", port), _Mock)
    threading.Thread(target=gemini.serve_forever, daemon=True).start()
    threading.Thread(target=srv.run_server, kwargs={"host": "127.0.0.1", "port": srv_port},
                     daemon=True).start()
    time.sleep(0.8)

    ok = 0
    try:
        for i in range(6):
            req = urllib.request.Request(
                f"http://127.0.0.1:{srv_port}/v1/chat/completions",
                data=json.dumps({"model": "auto",
                                 "messages": [{"role": "user", "content": f"hi {i}"}]}).encode(),
                headers={"Content-Type": "application/json"})
            try:
                body = json.loads(urllib.request.urlopen(req, timeout=10).read())
                assert body["choices"][0]["message"]["content"].startswith("pong:")
                ok += 1
            except urllib.error.HTTPError:
                pass
    finally:
        gemini.shutdown()
    assert ok >= 4, f"expected >=4 proxy successes, got {ok}"
    print(f"PASS: proxy {ok}/6 ok")
