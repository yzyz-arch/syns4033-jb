#!/usr/bin/env python3
"""Client buat endpoint streamflow /playground/api/ask.

Dipakai dari host yang SUDAH join tailnet (MagicDNS *.ts.net cuma resolve
di dalam tailnet). Kalau host belum join -> DNS fail (Errno -2), bukan bug client.

Usage:
    python3 streamflow_client.py "balas satu kata: siap"
    python3 streamflow_client.py --model fayoz-ds41 --json '{"model":"x","prompt":"y"}'
    python3 streamflow_client.py --selftest

Env:
    STREAMFLOW_URL    override base url (default di bawah)
    STREAMFLOW_MODEL  override model default
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_URL = "https://streamflow-vps.tail12a93b.ts.net/playground/api/ask"
DEFAULT_MODEL = "fayoz-ds41"


class AskError(RuntimeError):
    """Error yang sudah dipetakan, biar gampang dibaca."""


def _preflight(url: str) -> None:
    """Cek DNS dulu: ts.net tanpa tailnet = Errno -2 yang bikin bingung."""
    host = urlparse(url).hostname
    if not host:
        raise AskError(f"URL tidak valid: {url!r}")
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise AskError(
            f"DNS gagal resolve {host!r} ({e}).\n"
            "  Host ini kelihatannya BELUM join tailnet. MagicDNS (*.ts.net)\n"
            "  memang tidak ada di DNS publik — harus lewat Tailscale.\n"
            "  Fix: sudo tailscale up --authkey=<key>  (atau pakai Funnel URL publik)."
        ) from e


def ask(
    prompt: str,
    model: str = DEFAULT_MODEL,
    url: str = DEFAULT_URL,
    timeout: float = 60.0,
    retries: int = 3,
    backoff: float = 1.5,
) -> dict:
    """Kirim prompt, balikin dict hasil ternormalisasi.

    Return: {"ok": bool, "text": str, "ms": int|None, "model": str, "raw": dict}
    """
    _preflight(url)
    payload = json.dumps({"model": model, "prompt": prompt}).encode()
    last: Exception | None = None

    for attempt in range(1, retries + 1):
        t0 = time.time()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "streamflow-client/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
                elapsed = int((time.time() - t0) * 1000)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            last = AskError(f"HTTP {e.code} dari server: {detail}")
            if e.code in (400, 401, 403, 404, 422):
                raise last from None  # 4xx = salah request, jangan retry
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            last = AskError(f"koneksi gagal (attempt {attempt}/{retries}): {e}")
        else:
            try:
                j = json.loads(body)
            except json.JSONDecodeError as e:
                raise AskError(f"response bukan JSON: {body[:300]!r}") from e

            results = j.get("results") or []
            if not results:
                raise AskError(f"response tidak punya 'results': {json.dumps(j)[:300]}")

            first = results[0]
            if not isinstance(first, dict):
                raise AskError(f"results[0] bukan object: {first!r}")

            return {
                "ok": bool(first.get("ok")),
                "text": first.get("text", ""),
                "ms": first.get("ms", elapsed),
                "wall_ms": elapsed,
                "model": j.get("model", model),
                "raw": j,
            }

        if attempt < retries:
            time.sleep(backoff ** attempt)

    raise last or AskError("gagal tanpa error spesifik")


def selftest() -> int:
    """Print diagnosa: DNS, TCP, HTTP. Nol crash walau semuanya mati."""
    url = os.environ.get("STREAMFLOW_URL", DEFAULT_URL)
    p = urlparse(url)
    host, port = p.hostname, p.port or 443
    print(f"url      : {url}")
    print(f"host     : {host}:{port}")

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        ips = sorted({i[4][0] for i in infos})
        print(f"dns      : OK {ips}")
    except socket.gaierror as e:
        print(f"dns      : FAIL {e}  -> host belum join tailnet?")
        return 2

    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=10):
            print(f"tcp      : OK {int((time.time()-t0)*1000)}ms")
    except OSError as e:
        print(f"tcp      : FAIL {e}")
        return 3

    try:
        res = ask("balas satu kata: siap", url=url)
    except AskError as e:
        print(f"http     : FAIL {e}")
        return 4

    print(f"http     : OK ok={res['ok']} text={res['text']!r} ms={res['ms']}")
    return 0 if res["ok"] else 5


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Client /playground/api/ask")
    ap.add_argument("prompt", nargs="?", help="prompt teks")
    ap.add_argument("--model", default=os.environ.get("STREAMFLOW_MODEL", DEFAULT_MODEL))
    ap.add_argument("--url", default=os.environ.get("STREAMFLOW_URL", DEFAULT_URL))
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--json", help="kirim body JSON mentah (override prompt/model)")
    ap.add_argument("--selftest", action="store_true", help="diagnosa DNS/TCP/HTTP")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.json:
        prompt = json.loads(args.json).get("prompt", "")
    elif args.prompt:
        prompt = args.prompt
    else:
        ap.error("butuh prompt atau --selftest")

    try:
        res = ask(prompt, model=args.model, url=args.url, timeout=args.timeout)
    except AskError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"ok={res['ok']} ms={res['ms']} model={res['model']}")
    print(res["text"])
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
