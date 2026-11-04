"""livegeo — device-reported live location for the identity we already parsed.

WHY THIS EXISTS AND WHAT IT HONESTLY IS
--------------------------------------
`phone_nik` proves, in code and at runtime, that a NIK and a phone number carry
zero positional telemetry: a NIK holds a civil-registration address snapshot, a
phone number holds an issuing carrier prefix. Neither can be turned into a
position by any offline math. Turning them into a position requires the carrier's
HLR/GMLC (lawful intercept), SS7/Diameter abuse, or an implant — i.e. exactly the
things this toolkit does not implement.

So "live location" is built where it actually exists and is legitimately
obtainable: **telemetry the operator's own devices report**. This module is a
self-hosted tracking backend:

    device (phone/handset, lab-owned)
        -> POST /ingest  {device_id, token, lat, lon, acc, ts, battery}
        -> livegeo.pings (SQLite)
        -> GET  /locate?phone=... | ?nik=... | ?device_id=...
        -> latest fix + age + freshness class + haversine from reference

The identity (phone/NIK) is the *join key*, the device is the *position source*.
That is the only version of this feature that produces real coordinates, and the
labeling in every response says so: `position_source: "device-reported"`.

GUARDRAILS (part of the delivery, not a substitute for it)
---------------------------------------------------------
1. `assert_loopback()` — the server refuses to bind, and the client refuses to
   connect, to any address that is not 127.0.0.0/8, ::1 or "localhost".
2. `require_authorization()` — every entry point demands `--i-have-authorization`.
3. Per-device bearer token, stored as sha256(token|device_id); the plaintext is
   printed once at registration and never persisted.
4. Ingest validates plausibility: lat/lon ranges, accuracy ceiling, clock skew
   window, and per-device rate limit — one bad handset cannot poison the map.
"""

from __future__ import annotations

import hashlib
import hmac
import http.server
import ipaddress
import json
import math
import os
import secrets
import socket
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import phone_nik

# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

ALLOWED_BIND = {"127.0.0.1", "::1", "localhost"}
DEFAULT_DB = os.environ.get("OSINTKIT_GEO_DB", ".osintkit/livegeo.db")
MAX_ACCURACY_M = 5000.0          # reject "fixes" worse than 5 km
CLOCK_SKEW_S = 300               # reject pings stamped >5 min in the future
RATE_LIMIT_S = 1.0               # min seconds between accepted pings per device
LIVE_WINDOW_S = 120              # younger than this => "live" (see classify_age)


class GuardrailViolation(RuntimeError):
    pass


def require_authorization(flag: bool, what: str = "livegeo") -> None:
    """Hard gate: no flag, no execution."""
    if not flag:
        raise GuardrailViolation(
            f"{what} refused: pass --i-have-authorization to confirm this runs "
            "against lab-owned devices on loopback only"
        )


def assert_loopback(host: str) -> str:
    """Reject any bind/connect target that is not loopback. Resolution-aware."""
    if not host:
        raise GuardrailViolation("empty host")
    h = host.strip().lower().strip("[]")
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    if h in ALLOWED_BIND:
        return "127.0.0.1" if h == "localhost" else h
    try:
        infos = socket.getaddrinfo(h, None)
    except socket.gaierror:
        raise GuardrailViolation(f"cannot resolve {h!r} — only loopback is permitted")
    ips = {str(i[4][0]) for i in infos}
    for ip in ips:
        if not ipaddress.ip_address(ip.split("%")[0]).is_loopback:
            raise GuardrailViolation(
                f"{h!r} resolves to non-loopback {ip} — livegeo binds loopback only"
            )
    return "::1" if "::1" in ips else sorted(ips)[0]


def assert_loopback_url(url: str) -> str:
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise GuardrailViolation(f"scheme {u.scheme!r} not allowed")
    host = u.hostname or ""
    assert_loopback(host)
    return url


# ---------------------------------------------------------------------------
# geo math
# ---------------------------------------------------------------------------

EARTH_M = 6371008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_M * math.asin(min(1.0, math.sqrt(a)))


def classify_age(age_s: float) -> str:
    if age_s < 0:
        return "future_clock"
    if age_s <= 120:
        return "live"
    if age_s <= 900:
        return "recent"
    if age_s <= 3600:
        return "stale"
    if age_s <= 86400:
        return "cold"
    return "historic"


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id   TEXT PRIMARY KEY,
    label       TEXT,
    phone_e164  TEXT,
    nik         TEXT,
    token_hash  TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dev_phone ON devices(phone_e164);
CREATE INDEX IF NOT EXISTS idx_dev_nik   ON devices(nik);

CREATE TABLE IF NOT EXISTS pings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    ts        REAL NOT NULL,
    lat       REAL NOT NULL,
    lon       REAL NOT NULL,
    acc_m     REAL,
    battery   REAL,
    source    TEXT,
    ip        TEXT
);
CREATE INDEX IF NOT EXISTS idx_ping_dev_ts ON pings(device_id, ts DESC);
"""


def _token_hash(token: str, device_id: str) -> str:
    return hashlib.sha256(f"{token}|{device_id}".encode()).hexdigest()


class Store:
    def __init__(self, path: str = DEFAULT_DB):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- devices -----------------------------------------------------------
    def register(self, device_id: str, *, label: str | None = None,
                 phone: str | None = None, nik: str | None = None) -> dict:
        if not device_id or not device_id.strip():
            raise ValueError("device_id required")
        phone_e164 = None
        nik_norm = None
        if phone:
            norm = phone_nik.normalize_phone(phone)
            if not norm["valid"]:
                raise ValueError(f"bad phone: {norm['errors']}")
            phone_e164 = norm["e164"]
        if nik:
            parsed = phone_nik.parse_nik(nik, authorized=True)
            if not parsed["valid"]:
                raise ValueError(f"bad NIK: {parsed['errors']}")
            nik_norm = nik.strip()

        token = secrets.token_urlsafe(32)
        with self._lock:
            cur = self._db.execute("SELECT token_hash FROM devices WHERE device_id=?", (device_id,))
            row = cur.fetchone()
            if row and not token:
                raise ValueError("exists")
            self._db.execute(
                "INSERT INTO devices(device_id,label,phone_e164,nik,token_hash,created_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET "
                "label=excluded.label, phone_e164=excluded.phone_e164, "
                "nik=excluded.nik, token_hash=excluded.token_hash",
                (device_id, label, phone_e164, nik_norm, _token_hash(token, device_id), time.time()),
            )
            self._db.commit()
        return {"device_id": device_id, "label": label, "phone_e164": phone_e164,
                "nik_masked": phone_nik._mask(nik_norm or ""), "token": token,
                "token_note": "shown once; only sha256(token|device_id) is stored"}

    def auth(self, device_id: str, token: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT token_hash FROM devices WHERE device_id=?", (device_id,)).fetchone()
        return bool(row) and hmac.compare_digest(row["token_hash"], _token_hash(token, device_id))

    def devices_for(self, *, phone: str | None = None, nik: str | None = None) -> list[dict]:
        with self._lock:
            if phone:
                norm = phone_nik.normalize_phone(phone)
                if not norm["valid"]:
                    return []
                rows = self._db.execute(
                    "SELECT device_id,label,phone_e164,nik FROM devices WHERE phone_e164=?",
                    (norm["e164"],)).fetchall()
            elif nik:
                rows = self._db.execute(
                    "SELECT device_id,label,phone_e164,nik FROM devices WHERE nik=?",
                    (nik.strip(),)).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT device_id,label,phone_e164,nik FROM devices").fetchall()
        return [dict(r) for r in rows]

    # -- pings -------------------------------------------------------------
    def last_ping_ts(self, device_id: str) -> float | None:
        with self._lock:
            row = self._db.execute(
                "SELECT MAX(ts) AS t FROM pings WHERE device_id=?", (device_id,)).fetchone()
        return row["t"] if row and row["t"] is not None else None

    def add_ping(self, device_id: str, lat: float, lon: float, *, ts: float | None = None,
                 acc_m: float | None = None, battery: float | None = None,
                 source: str = "device", ip: str | None = None) -> dict:
        now = time.time()
        ts = now if ts is None else float(ts)

        errs = []
        if not (-90.0 <= lat <= 90.0):
            errs.append(f"lat {lat} out of range")
        if not (-180.0 <= lon <= 180.0):
            errs.append(f"lon {lon} out of range")
        if lat == 0.0 and lon == 0.0:
            errs.append("null island (0,0) is a sentinel, not a fix")
        if acc_m is not None and acc_m > MAX_ACCURACY_M:
            errs.append(f"accuracy {acc_m:.0f}m exceeds {MAX_ACCURACY_M:.0f}m ceiling")
        if ts > now + CLOCK_SKEW_S:
            errs.append(f"timestamp {ts:.0f} more than {CLOCK_SKEW_S}s in the future")
        if errs:
            raise ValueError("; ".join(errs))

        last = self.last_ping_ts(device_id)
        if last is not None and ts - last < RATE_LIMIT_S:
            raise ValueError(f"rate limited: {ts - last:.2f}s since last accepted ping")

        with self._lock:
            self._db.execute(
                "INSERT INTO pings(device_id,ts,lat,lon,acc_m,battery,source,ip) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (device_id, ts, lat, lon, acc_m, battery, source, ip))
            self._db.commit()
        return {"accepted": True, "device_id": device_id, "ts": ts, "lat": lat, "lon": lon}

    def track(self, device_id: str, *, hours: float = 24.0, limit: int = 500) -> list[dict]:
        since = time.time() - hours * 3600
        with self._lock:
            rows = self._db.execute(
                "SELECT ts,lat,lon,acc_m,battery,source FROM pings "
                "WHERE device_id=? AND ts>=? ORDER BY ts ASC LIMIT ?",
                (device_id, since, limit)).fetchall()
        return [dict(r) for r in rows]

    def latest_ping(self, device_id: str) -> dict | None:
        """Newest accepted ping for a device.

        Separate from track() on purpose: track() is an oldest-first window
        (for plotting), so `track(..., limit=1)` returns the OLDEST point.
        Using it to answer "where is the device now" silently reported a
        stale position, which is worse than reporting none.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT ts,lat,lon,acc_m,battery,source FROM pings "
                "WHERE device_id=? ORDER BY ts DESC LIMIT 1",
                (device_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# location resolution
# ---------------------------------------------------------------------------

POSITION_SOURCE = "device-reported"


def public_device(row: dict) -> dict:
    """Device row for HTTP egress — join keys masked, never raw PII.

    `Store.devices_for()` returns the raw phone/NIK because it is the internal
    join path for locate(); anything that leaves the process must go through
    here. Masking at the serialisation boundary (not in the store) keeps the
    lookup exact while making the HTTP surface safe to screenshot or log.
    """
    return {
        "device_id": row.get("device_id"),
        "label": row.get("label"),
        "phone_masked": phone_nik._mask(row.get("phone_e164") or "", keep_head=5, keep_tail=2),
        "nik_masked": phone_nik._mask(row.get("nik") or ""),
    }


def locate(store: Store, *, phone: str | None = None, nik: str | None = None,
           device_id: str | None = None, ref_lat: float | None = None,
           ref_lon: float | None = None) -> dict:
    """Resolve identity -> device -> newest fix. Returns an honest capability block."""
    res: dict = {
        "position_source": POSITION_SOURCE,
        "position_source_why": (
            "coordinates come from telemetry the device itself POSTed to the loopback "
            "collector; no carrier/HLR/GMLC data is used or available"
        ),
    }
    if device_id:
        devices = [{"device_id": device_id}]
    elif phone or nik:
        devices = store.devices_for(phone=phone, nik=nik)
    else:
        devices = store.devices_for()

    if not devices:
        res["found"] = False
        res["reason"] = "no registered device matches this identity"
        res["hint"] = "register the handset first: geo register --device ... --phone ..."
        return res

    now = time.time()
    fixes = []
    for d in devices:
        p = store.latest_ping(d["device_id"])
        if not p:
            fixes.append({"device_id": d["device_id"], "fix": None,
                          "reason": "no pings received"})
            continue
        item = {
            "device_id": d["device_id"],
            "label": d.get("label"),
            "fix": {
                "lat": p["lat"], "lon": p["lon"], "acc_m": p["acc_m"],
                "battery": p["battery"], "source": p["source"],
                "ts": p["ts"],
                "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(p["ts"])),
                "age_s": round(now - p["ts"], 1),
                "freshness": classify_age(now - p["ts"]),
            },
        }
        if ref_lat is not None and ref_lon is not None:
            item["fix"]["distance_m"] = round(
                haversine_m(ref_lat, ref_lon, p["lat"], p["lon"]), 1)
            item["fix"]["bearing_deg"] = round(
                bearing_deg(ref_lat, ref_lon, p["lat"], p["lon"]), 1)
        fixes.append(item)

    res["found"] = any(f["fix"] for f in fixes)
    res["devices_checked"] = len(fixes)
    res["fixes"] = fixes
    present = [f["fix"] for f in fixes if f["fix"]]
    live = [f for f in present if f["freshness"] == "live"]
    res["live_count"] = len(live)
    # `best` is the newest fix we actually have, NOT only the live ones.
    # Previously it was `live or None`, so a 10-minute-old fix produced
    # found:true together with best:null — a self-contradicting payload that
    # forced every caller to special-case it. Freshness is reported next to
    # the fix so the consumer can judge staleness itself.
    res["best"] = max(present, key=lambda x: x["ts"]) if present else None
    res["best_is_live"] = bool(live)
    if present and not live:
        res["staleness_note"] = (
            f"newest fix is {res['best']['age_s']}s old "
            f"({res['best']['freshness']}); no device has reported in the last "
            f"{LIVE_WINDOW_S}s"
        )
    return res


def track_report(store: Store, device_id: str, *, hours: float = 24.0) -> dict:
    pts = store.track(device_id, hours=hours)
    if not pts:
        return {"device_id": device_id, "points": 0, "hours": hours}
    dist = sum(haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
               for a, b in zip(pts, pts[1:]))
    dur = max(0.0, pts[-1]["ts"] - pts[0]["ts"])
    return {
        "device_id": device_id,
        "hours": hours,
        "points": len(pts),
        "first_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(pts[0]["ts"])),
        "last_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(pts[-1]["ts"])),
        "duration_s": round(dur, 1),
        "distance_m": round(dist, 1),
        "avg_speed_kmh": round((dist / dur) * 3.6, 2) if dur > 0 else None,
        "points_detail": pts,
        "position_source": POSITION_SOURCE,
    }


# ---------------------------------------------------------------------------
# HTTP collector (loopback only)
# ---------------------------------------------------------------------------

class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "livegeo/1.0"
    store: Store = None  # type: ignore[assignment]

    def log_message(self, format, *args):  # noqa: A002 — base-class param name
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self) -> str:
        ip = self.client_address[0]
        try:
            if not ipaddress.ip_address(ip.split("%")[0]).is_loopback:
                raise GuardrailViolation("non-loopback client")
        except ValueError:
            raise GuardrailViolation("unparsable client address")
        return ip

    def do_GET(self):
        try:
            ip = self._client_ip()
        except GuardrailViolation as e:
            return self._send(403, {"error": str(e)})
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}

        if u.path == "/health":
            return self._send(200, {"ok": True, "db": self.store.path,
                                    "position_source": POSITION_SOURCE})

        if u.path == "/locate":
            return self._send(200, locate(
                self.store, phone=q.get("phone"), nik=q.get("nik"),
                device_id=q.get("device_id"),
                ref_lat=float(q["ref_lat"]) if "ref_lat" in q else None,
                ref_lon=float(q["ref_lon"]) if "ref_lon" in q else None))

        if u.path == "/track":
            dev = q.get("device_id")
            if not dev:
                return self._send(400, {"error": "device_id required"})
            return self._send(200, track_report(
                self.store, dev, hours=float(q.get("hours", 24))))

        if u.path == "/devices":
            return self._send(200, {"devices": [public_device(d)
                                                for d in self.store.devices_for()]})

        return self._send(404, {"error": f"no route {u.path}"})

    def do_POST(self):
        try:
            ip = self._client_ip()
        except GuardrailViolation as e:
            return self._send(403, {"error": str(e)})
        u = urlparse(self.path)
        if u.path != "/ingest":
            return self._send(404, {"error": f"no route {u.path}"})

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 65536:
            return self._send(400, {"error": "bad Content-Length"})
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return self._send(400, {"error": "invalid JSON"})

        dev, token = payload.get("device_id"), payload.get("token")
        if not dev or not token:
            return self._send(400, {"error": "device_id and token required"})
        if not self.store.auth(dev, token):
            return self._send(401, {"error": "bad device token"})

        try:
            out = self.store.add_ping(
                dev,
                float(payload.get("lat")),
                float(payload.get("lon")),
                ts=float(payload["ts"]) if payload.get("ts") is not None else None,
                acc_m=float(payload["acc"]) if payload.get("acc") is not None else None,
                battery=float(payload["battery"]) if payload.get("battery") is not None else None,
                source=str(payload.get("source") or "device"),
                ip=ip,
            )
        except (TypeError, ValueError) as e:
            return self._send(400, {"error": str(e)})
        out["position_source"] = POSITION_SOURCE
        return self._send(202, out)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(store: Store, host: str = "127.0.0.1", port: int = 8099) -> _Server:
    bind = assert_loopback(host)
    handler = type("BoundHandler", (_Handler,), {"store": store})
    srv = _Server((bind, port), handler)
    return srv


def serve(store: Store, host: str = "127.0.0.1", port: int = 8099,
          *, authorized: bool = False) -> None:
    require_authorization(authorized)
    srv = make_server(store, host, port)
    try:
        print(json.dumps({"listening": f"http://{host}:{port}",
                          "routes": ["POST /ingest", "GET /locate", "GET /track",
                                     "GET /devices", "GET /health"],
                          "position_source": POSITION_SOURCE,
                          "bind_guard": "loopback-only enforced by assert_loopback()"}))
        srv.serve_forever()
    finally:
        srv.server_close()


# ---------------------------------------------------------------------------
# lab producer: synthetic loopback device (for validation, not for real people)
# ---------------------------------------------------------------------------

def simulate(store: Store, device_id: str, *, points: int = 6, interval: float = 1.0,
             lat: float = -6.2088, lon: float = 106.8456,
             step_m: float = 120.0, bearing: float = 45.0,
             acc_m: float = 12.0) -> dict:
    """Walk a straight line from (lat,lon) so the tracker has a real track to plot."""
    if not store.devices_for():
        raise ValueError("register a device first")
    # Pings are rate-limited per device, so the synthetic timestamps must be
    # spaced at least RATE_LIMIT_S apart even when the caller asks for an
    # instant run (interval=0). Spacing the *timestamps* rather than the
    # wall-clock sleeps keeps the produced track internally consistent: the
    # speed computed from it is the speed a real device would have shown.
    spacing = max(float(interval), RATE_LIMIT_S + 0.01)
    dlat = (step_m * math.cos(math.radians(bearing))) / 111320.0
    dlon = (step_m * math.sin(math.radians(bearing))) / (111320.0 * math.cos(math.radians(lat)))
    sent = []
    for i in range(points):
        ts = time.time() - (points - i - 1) * spacing
        p = store.add_ping(device_id, lat + dlat * i, lon + dlon * i,
                           ts=ts, acc_m=acc_m, battery=90.0 - i,
                           source="simulated", ip="127.0.0.1")
        sent.append(p)
        if interval > 0:
            time.sleep(min(interval, 0.05) if interval < 1.0 else RATE_LIMIT_S + 0.05)
    return {"device_id": device_id, "points_sent": len(sent),
            "from": {"lat": lat, "lon": lon},
            "to": {"lat": lat + dlat * (points - 1), "lon": lon + dlon * (points - 1)},
            "step_m": step_m, "bearing_deg": bearing,
            "spacing_s": spacing,
            "position_source": "simulated"}
