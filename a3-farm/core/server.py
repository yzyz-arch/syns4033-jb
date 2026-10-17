"""Minimal OpenAI-compatible HTTP proxy over the Gemini key pool.

POST /v1/chat/completions  with {"model": "...", "messages": [{"role","content"}...]}
GET  /v1/models
GET  /health
"""
from __future__ import annotations
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .balancer import KeyPool
from .db import Store
from .config import FALLBACK_MODELS

_POOL: KeyPool | None = None


def _pool() -> KeyPool:
    global _POOL
    if _POOL is None:
        _POOL = KeyPool(Store().active_keys())
    return _POOL


def _messages_to_prompt(messages: list[dict]) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):  # multimodal parts
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


class Handler(BaseHTTPRequestHandler):
    server_version = "a3farm/1.0"

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quiet
        pass

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send(200, {"ok": True, "pool": _pool().health()})
        if self.path.startswith("/v1/models"):
            return self._send(200, {"object": "list",
                                    "data": [{"id": m, "object": "model"} for m in FALLBACK_MODELS]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError as e:
            return self._send(400, {"error": {"message": f"bad json: {e}"}})
        prompt = _messages_to_prompt(req.get("messages", []))
        model = req.get("model")
        if model in (None, "auto", "gemini"):
            model = None
        t0 = time.time()
        res = _pool().generate(prompt, model=model,
                               max_output_tokens=req.get("max_tokens", 1024))
        if not res["ok"]:
            return self._send(429 if "cooldown" in res.get("error", "") else 502,
                              {"error": {"message": res.get("error", "upstream error")}})
        out = {
            "id": "chatcmpl-" + str(int(t0 * 1000)),
            "object": "chat.completion",
            "created": int(t0),
            "model": res["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": res["text"]}}],
            "usage": {},
            "x_a3": {"key": res["key"], "attempts": res["attempts"], "latency_ms": res["latency_ms"]},
        }
        return self._send(200, out)


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"[+] a3farm proxy on http://{host}:{port}  (POST /v1/chat/completions)")
    srv.serve_forever()
