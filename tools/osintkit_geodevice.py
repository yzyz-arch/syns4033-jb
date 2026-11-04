#!/usr/bin/env python3
"""osintkit device agent — push a real fix from a lab handset into the loopback collector.

Runs ON the device (or next to it) and POSTs to `osintkit geo serve`.

Fix sources, in order of honesty:
  --lat/--lon        explicit fix you already have
  termux-location    Android/Termux (GPS or network provider), JSON out
  gpspipe            gpsd JSON stream (GPS receiver on a Linux host)

Guardrails are inside this client too, not just in the server:
  * the collector URL must resolve to loopback or it refuses to send
  * the token comes from a file with mode 0600 (never argv — argv leaks to ps)
  * --i-have-authorization required

Usage:
  python3 osintkit_geodevice.py --device lab-handset-01 \
      --token-file /tmp/geolab/token.txt --url http://127.0.0.1:8099 \
      --provider termux --interval 15 --i-have-authorization
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.request
import ipaddress
from urllib.parse import urlparse


def guard_url(url: str) -> str:
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        sys.exit(f"refused: scheme {u.scheme!r}")
    host = u.hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        return url
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        sys.exit(f"refused: cannot resolve {host!r}")
    for i in infos:
        ip = str(i[4][0]).split("%")[0]
        if not ipaddress.ip_address(ip).is_loopback:
            sys.exit(f"refused: {host!r} -> {ip} is not loopback; collector must be local")
    return url


def read_token(path: str) -> str:
    st = os.stat(path)
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        sys.exit(f"refused: {path} is mode {oct(st.st_mode & 0o777)}; chmod 600 it")
    return open(path).read().strip()


def fix_from_termux() -> dict:
    if not shutil.which("termux-location"):
        raise RuntimeError("termux-location not found (install termux-api)")
    out = subprocess.run(
        ["termux-location", "-p", "gps", "-r", "once"],
        capture_output=True, text=True, timeout=90)
    if out.returncode != 0:
        # fall back to the network provider before giving up on this cycle
        out = subprocess.run(
            ["termux-location", "-p", "network", "-r", "once"],
            capture_output=True, text=True, timeout=90)
    if out.returncode != 0:
        raise RuntimeError(f"termux-location failed: {out.stderr.strip()[:160]}")
    d = json.loads(out.stdout)
    return {"lat": d["latitude"], "lon": d["longitude"],
            "acc": d.get("accuracy"), "source": "termux"}


def fix_from_gpsd(samples: int = 20) -> dict:
    if not shutil.which("gpspipe"):
        raise RuntimeError("gpspipe not found (install gpsd-clients)")
    proc = subprocess.Popen(["gpspipe", "-w", "-n", str(samples)],
                            stdout=subprocess.PIPE, text=True)
    last = None
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("class") == "TPV" and d.get("lat") is not None:
                last = d
    finally:
        proc.terminate()
    if not last:
        raise RuntimeError("gpsd produced no TPV fix (no satellite lock?)")
    return {"lat": last["lat"], "lon": last["lon"], "acc": last.get("eph"),
            "source": "gpsd"}


def post(url: str, payload: dict, timeout: int = 10) -> dict:
    req = urllib.request.Request(
        url.rstrip("/") + "/ingest",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser(description="push device fixes to the loopback livegeo collector")
    ap.add_argument("--device", required=True, help="device_id registered with `geo register`")
    ap.add_argument("--token-file", required=True, help="path to token (must be mode 600)")
    ap.add_argument("--url", default="http://127.0.0.1:8099", help="collector URL (loopback only)")
    ap.add_argument("--provider", choices=["termux", "gpsd", "manual"], default="termux")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--interval", type=float, default=0.0, help="0 = one shot")
    ap.add_argument("--count", type=int, default=1, help="fixes to send (0 = forever)")
    ap.add_argument("--i-have-authorization", action="store_true")
    a = ap.parse_args()

    if not a.i_have_authorization:
        sys.exit("refused: pass --i-have-authorization (lab-owned device, loopback collector)")
    url = guard_url(a.url)
    token = read_token(a.token_file)

    sent = 0
    while True:
        try:
            if a.provider == "manual":
                if a.lat is None or a.lon is None:
                    sys.exit("manual provider needs --lat and --lon")
                fix = {"lat": a.lat, "lon": a.lon, "acc": None, "source": "manual"}
            elif a.provider == "termux":
                fix = fix_from_termux()
            else:
                fix = fix_from_gpsd()
            payload = {"device_id": a.device, "token": token,
                       "lat": fix["lat"], "lon": fix["lon"], "acc": fix.get("acc"),
                       "ts": time.time(), "source": fix.get("source")}
            res = post(url, payload)
            sent += 1
            print(json.dumps({"sent": sent, "response": res}))
        except Exception as e:
            print(json.dumps({"error": f"{type(e).__name__}: {str(e)[:200]}"}),
                  file=sys.stderr)
            if a.count and sent >= a.count:
                return 1

        if a.interval <= 0:
            break
        if a.count and sent >= a.count:
            break
        time.sleep(a.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
