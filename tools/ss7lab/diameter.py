"""Diameter SLh / SLg location interface — loopback lab implementation.

Real interface shapes (3GPP TS 29.172):
  SLh : LCS-Routing-Info-Request / Answer  (LIR / LIA)
  SLg : Provide-Location-Request / Answer  (PLR / PLA)

Both carry the same location payload: a routing/location container holding
either a cell-global-id (2G/3G CGI or 4G ECGI) or a tracking-area-id (5G TAI),
plus an age-of-location.

AVP codes: the base Diameter ones (263/264/268/277/283/293/296) are fixed by
RFC 6733. The 3GPP location AVPs are declared once in the table below; the
decoder prints any AVP it does not recognise as `avp_<code>` rather than
guessing, so a mismatched constant is visible instead of silently wrong.
Verify the 3GPP codes against the TS 29.172 AVP table before matching a real
capture — they are lab defaults here, not asserted from a carrier trace.
"""
from __future__ import annotations

import json
import socket
import struct
import threading
import time

from . import guard

VERSION = 1
FLAG_REQUEST = 0x80
FLAG_PROXYABLE = 0x40
FLAG_ERROR = 0x20

APP_SLH = 16777291
APP_SLG = 16777255
CMD_LIR_LIA = 8388622
CMD_PLR_PLA = 8388620

# --- AVP codes -------------------------------------------------------------
AVP_SESSION_ID = 263
AVP_ORIGIN_HOST = 264
AVP_ORIGIN_REALM = 296
AVP_DEST_REALM = 283
AVP_DEST_HOST = 293
AVP_RESULT_CODE = 268
AVP_AUTH_SESSION_STATE = 277
AVP_USER_NAME = 1
AVP_MSISDN = 701                      # 3GPP TS 29.061
AVP_VENDOR_3GPP = 10415

# 3GPP location AVPs — lab defaults, see module docstring.
AVP_IMSI = 1                          # vendor 10415
AVP_LCS_ROUTING_INFO = 2500           # grouped: LCS-Routing-Info
AVP_ROUTING_INFO = 2501               # grouped: Routing-Info
AVP_LOCATION_AREA_ID = 2502           # octets, LAI
AVP_CELL_GLOBAL_ID = 2503             # octets, CGI/ECGI
AVP_TRACKING_AREA_ID = 2504           # octets, TAI
AVP_AGE_OF_LOCATION = 2505            # unsigned32, seconds
AVP_VLR_NUMBER = 2506                 # UTF8String
AVP_GMLC_NUMBER = 2507               # UTF8String

RESULT_SUCCESS = 2001
RESULT_USER_UNKNOWN = 5001
RESULT_UNABLE_TO_COMPLY = 5012

VENDORED = {AVP_IMSI, AVP_LCS_ROUTING_INFO, AVP_ROUTING_INFO, AVP_LOCATION_AREA_ID,
           AVP_CELL_GLOBAL_ID, AVP_TRACKING_AREA_ID, AVP_AGE_OF_LOCATION,
           AVP_VLR_NUMBER, AVP_GMLC_NUMBER}

AVP_NAMES = {
    AVP_SESSION_ID: "Session-Id", AVP_ORIGIN_HOST: "Origin-Host",
    AVP_ORIGIN_REALM: "Origin-Realm", AVP_DEST_REALM: "Destination-Realm",
    AVP_DEST_HOST: "Destination-Host", AVP_RESULT_CODE: "Result-Code",
    AVP_AUTH_SESSION_STATE: "Auth-Session-State", AVP_USER_NAME: "User-Name",
    AVP_MSISDN: "MSISDN", AVP_IMSI: "IMSI",
    AVP_LCS_ROUTING_INFO: "LCS-Routing-Info", AVP_ROUTING_INFO: "Routing-Info",
    AVP_LOCATION_AREA_ID: "Location-Area-Id", AVP_CELL_GLOBAL_ID: "Cell-Global-Id",
    AVP_TRACKING_AREA_ID: "Tracking-Area-Id",
    AVP_AGE_OF_LOCATION: "Age-Of-Location", AVP_VLR_NUMBER: "VLR-Number",
    AVP_GMLC_NUMBER: "GMLC-Number",
}


# --- AVP codec -------------------------------------------------------------
def avp(code: int, data: bytes, *, vendor: int | None = None,
        mandatory: bool = True, grouped: bool = False) -> bytes:
    flags = 0
    if vendor is not None:
        flags |= 0x80
    if mandatory:
        flags |= 0x40
    if grouped:
        flags |= 0x20
    body = data
    if vendor is not None:
        body = struct.pack(">I", vendor) + body
    length = 8 + len(body)
    pad = (-length) % 4
    return struct.pack(">IB3s", code, flags, length.to_bytes(3, "big")) + body + b"\x00" * pad


def avp_u32(code: int, value: int, **kw) -> bytes:
    return avp(code, struct.pack(">I", value), **kw)


def avp_str(code: int, value: str, **kw) -> bytes:
    return avp(code, value.encode(), **kw)


def parse_avps(buf: bytes) -> list[dict]:
    out, off = [], 0
    while off + 8 <= len(buf):
        code, flags, ln = struct.unpack(">IB3s", buf[off:off + 8])
        length = int.from_bytes(ln, "big")
        if length < 8 or off + length > len(buf):
            break
        body = buf[off + 8:off + length]
        vendor = None
        if flags & 0x80 and len(body) >= 4:
            vendor = struct.unpack(">I", body[:4])[0]
            body = body[4:]
        out.append({"code": code, "flags": flags, "vendor": vendor, "data": body})
        off += length + ((-length) % 4)
    return out


def avp_decode_list(avps: list[dict]) -> list[dict]:
    rendered = []
    for a in avps:
        name = AVP_NAMES.get(a["code"], f"avp_{a['code']}")
        val: object
        if a["flags"] & 0x20:                     # grouped
            val = avp_decode_list(parse_avps(a["data"]))
        elif a["code"] in (AVP_AGE_OF_LOCATION, AVP_RESULT_CODE, AVP_AUTH_SESSION_STATE):
            val = struct.unpack(">I", a["data"][:4])[0] if len(a["data"]) >= 4 else None
        else:
            try:
                text = a["data"].decode()
                val = text if text.isprintable() else a["data"].hex()
            except UnicodeDecodeError:
                val = a["data"].hex()
        rendered.append({"avp": name, "code": a["code"],
                         "vendor": a["vendor"], "value": val})
    return rendered


# --- message codec ---------------------------------------------------------
def diameter(command: int, app_id: int, avps: bytes, *, request: bool,
             hop: int = 1, end: int = 1, error: bool = False) -> bytes:
    flags = FLAG_PROXYABLE
    if request:
        flags |= FLAG_REQUEST
    if error:
        flags |= FLAG_ERROR
    return (struct.pack(">B", VERSION) + (20 + len(avps)).to_bytes(3, "big") +
            bytes([flags]) + command.to_bytes(3, "big") +
            struct.pack(">III", app_id, hop, end) + avps)


def parse_diameter(buf: bytes) -> dict:
    if len(buf) < 20:
        raise ValueError(f"short Diameter message ({len(buf)} bytes)")
    version = buf[0]
    if version != VERSION:
        raise ValueError(f"bad Diameter version {version}")
    length = int.from_bytes(buf[1:4], "big")
    if length < 20 or length > len(buf):
        raise ValueError(f"bad Diameter length {length} (buffer {len(buf)})")
    flags = buf[4]
    command = int.from_bytes(buf[5:8], "big")
    app_id, hop, end = struct.unpack(">III", buf[8:20])
    return {"version": version, "length": length, "flags": flags,
            "is_request": bool(flags & FLAG_REQUEST),
            "is_error": bool(flags & FLAG_ERROR),
            "command": command, "app_id": app_id,
            "hop_by_hop": hop, "end_to_end": end,
            "avps": avp_decode_list(parse_avps(buf[20:length]))}


# --- transport -------------------------------------------------------------
def open_diameter(host: str, port: int, timeout: float = 5.0) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((guard.assert_loopback(host), int(port)))
    return s


def listen_diameter(host: str, port: int, backlog: int = 8) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((guard.assert_loopback(host), int(port)))
    s.listen(backlog)
    return s


def recv_msg(sock: socket.socket) -> bytes:
    head = _recv_exact(sock, 4)
    if not head:
        return b""
    need = int.from_bytes(head[1:4], "big")
    rest = _recv_exact(sock, need - len(head))
    return head + rest


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


# --- synthetic GMLC --------------------------------------------------------
class DiameterGmlc:
    """Answers LIR -> LIA and PLR -> PLA from a synthetic subscriber table."""

    def __init__(self, hlr, host: str = "127.0.0.1", port: int = 3868, *,
                 realm: str = "lab.local", verbose: bool = True):
        self.hlr = hlr
        self.host = guard.assert_loopback(host)
        self.port = int(port)
        self.realm = realm
        self.verbose = verbose
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.stats = {"connections": 0, "lir": 0, "plr": 0, "unknown": 0,
                      "errors": 0}
        self.log: list[dict] = []

    def start(self, *, background: bool = True) -> "DiameterGmlc":
        self._sock = listen_diameter(self.host, self.port)
        # port 0 means "pick any" — publish the bound port so clients can connect
        self.port = self._sock.getsockname()[1]
        if background:
            self._thread = threading.Thread(target=self._accept_loop, daemon=True,
                                            name="ss7lab-gmlc")
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _accept_loop(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.stats["connections"] += 1
            self._log({"tcp": "accept", "peer": f"{addr[0]}:{addr[1]}"})
            threading.Thread(target=self._serve_conn, args=(conn,),
                             daemon=True).start()

    def _serve_conn(self, conn: socket.socket) -> None:
        conn.settimeout(10.0)
        try:
            while not self._stop.is_set():
                raw = recv_msg(conn)
                if not raw:
                    break
                msg = parse_diameter(raw)
                reply = self.handle(msg)
                if reply:
                    conn.sendall(reply)
        except (OSError, ValueError) as e:
            self.stats["errors"] += 1
            self._log({"error": f"{type(e).__name__}: {e}"})
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def handle(self, msg: dict) -> bytes | None:
        avps = {a["avp"]: a["value"] for a in msg["avps"]}
        session = avps.get("Session-Id") or "lab;0"
        msisdn = avps.get("MSISDN")
        imsi = avps.get("IMSI")

        if msg["command"] == CMD_LIR_LIA:
            self.stats["lir"] += 1
            return self._answer(msg, session, msisdn, imsi, "LIR")
        if msg["command"] == CMD_PLR_PLA:
            self.stats["plr"] += 1
            return self._answer(msg, session, msisdn, imsi, "PLR")
        self.stats["unknown"] += 1
        self._log({"unknown_command": msg["command"]})
        return None

    def _answer(self, msg: dict, session: str, msisdn, imsi, kind: str) -> bytes:
        sub = self.hlr.by_msisdn(msisdn) if msisdn else self.hlr.by_imsi(imsi or "")
        app_id = msg["app_id"] or (APP_SLH if kind == "LIR" else APP_SLG)
        header = [
            avp_str(AVP_SESSION_ID, session),
            avp_u32(AVP_AUTH_SESSION_STATE, 1),
            avp_str(AVP_ORIGIN_HOST, f"gmlc.{self.realm}"),
            avp_str(AVP_ORIGIN_REALM, self.realm),
            avp_str(AVP_DEST_REALM, avps_get(msg, "Origin-Realm") or self.realm),
        ]
        if sub is None:
            body = b"".join(header + [avp_u32(AVP_RESULT_CODE, RESULT_USER_UNKNOWN)])
            self._log({"cmd": kind, "msisdn": _mask(msisdn), "result": "USER_UNKNOWN"})
            return diameter(msg["command"], app_id, body, request=False,
                            hop=msg["hop_by_hop"], end=msg["end_to_end"],
                            error=True)

        sub.touch()
        age = sub.describe()["age_s"]
        routing = b"".join([
            avp(AVP_LOCATION_AREA_ID, sub.lai_raw, vendor=AVP_VENDOR_3GPP),
            avp(AVP_CELL_GLOBAL_ID, sub.lai_raw + struct.pack(">H", sub.ci),
                vendor=AVP_VENDOR_3GPP),
            avp_u32(AVP_AGE_OF_LOCATION, age, vendor=AVP_VENDOR_3GPP),
            avp_str(AVP_VLR_NUMBER, sub.vlr, vendor=AVP_VENDOR_3GPP),
        ])
        container = avp(AVP_LCS_ROUTING_INFO,
                        avp(AVP_ROUTING_INFO, routing, vendor=AVP_VENDOR_3GPP,
                            grouped=True),
                        vendor=AVP_VENDOR_3GPP, grouped=True)
        body = b"".join(header + [
            avp_u32(AVP_RESULT_CODE, RESULT_SUCCESS),
            container,
        ])
        self._log({"cmd": kind, "msisdn": _mask(msisdn),
                   "imsi": _mask(sub.imsi), "lai": f"{sub.mcc}-{sub.mnc}-{sub.lac}",
                   "ci": sub.ci, "age_s": age, "result": "SUCCESS"})
        return diameter(msg["command"], app_id, body, request=False,
                        hop=msg["hop_by_hop"], end=msg["end_to_end"])

    def _log(self, entry: dict) -> None:
        entry = {"t": round(time.time(), 3), **entry}
        self.log.append(entry)
        if self.verbose:
            print("[gmlc] " + json.dumps(entry, default=str), flush=True)


def avps_get(msg: dict, name: str):
    for a in msg["avps"]:
        if a["avp"] == name:
            return a["value"]
    return None


# --- client ----------------------------------------------------------------
class GmlcClient:
    """Sends LIR (SLh) or PLR (SLg) and decodes the answer."""

    def __init__(self, host: str = "127.0.0.1", port: int = 3868, *,
                 realm: str = "lab.local", timeout: float = 5.0,
                 verbose: bool = True):
        self.host = guard.assert_loopback(host)
        self.port = int(port)
        self.realm = realm
        self.timeout = timeout
        self.verbose = verbose
        self.trace: list[str] = []

    def _exchange(self, command: int, app_id: int, avps: bytes, label: str) -> dict:
        hop = int(time.time() * 1000) & 0x7FFFFFFF
        req = diameter(command, app_id, avps, request=True, hop=hop, end=hop)
        with open_diameter(self.host, self.port, self.timeout) as sock:
            sock.sendall(req)
            self._trace(f"TX {label}", req)
            raw = recv_msg(sock)
            self._trace("RX", raw)
        if not raw:
            raise TimeoutError("no Diameter answer")
        return parse_diameter(raw)

    def _common(self, msisdn: str | None, imsi: str | None, kind: str) -> bytes:
        session = f"lab;{int(time.time() * 1000)}"
        parts = [
            avp_str(AVP_SESSION_ID, session),
            avp_u32(AVP_AUTH_SESSION_STATE, 1),
            avp_str(AVP_ORIGIN_HOST, f"gmlc.{self.realm}"),
            avp_str(AVP_ORIGIN_REALM, self.realm),
            avp_str(AVP_DEST_REALM, self.realm),
            avp_str(AVP_DEST_HOST, f"gmlc.{self.realm}"),
            avp_str(AVP_GMLC_NUMBER, "6281100000999", vendor=AVP_VENDOR_3GPP),
        ]
        if msisdn:
            parts.append(avp(AVP_MSISDN, msisdn.encode(), vendor=AVP_VENDOR_3GPP))
        if imsi:
            parts.append(avp(AVP_IMSI, imsi.encode(), vendor=AVP_VENDOR_3GPP))
        return b"".join(parts)

    def lir(self, msisdn: str) -> dict:
        ans = self._exchange(CMD_LIR_LIA, APP_SLH,
                             self._common(msisdn, None, "LIR"), "LIR")
        return _summarize("SLh LIR/LIA", msisdn, ans)

    def plr(self, msisdn: str) -> dict:
        ans = self._exchange(CMD_PLR_PLA, APP_SLG,
                             self._common(msisdn, None, "PLR"), "PLR")
        return _summarize("SLg PLR/PLA", msisdn, ans)

    def _trace(self, label: str, data: bytes) -> None:
        line = f"{label} {len(data)}B {data[:40].hex()}"
        self.trace.append(line)
        if self.verbose:
            print(f"[gmlc-cli] {line}", flush=True)


def _summarize(kind: str, msisdn: str, ans: dict) -> dict:
    flat = {a["avp"]: a["value"] for a in ans["avps"]}
    routing: dict = {}
    for a in ans["avps"]:
        if a["avp"] == "LCS-Routing-Info" and isinstance(a["value"], list):
            for inner in a["value"]:
                if inner["avp"] == "Routing-Info" and isinstance(inner["value"], list):
                    routing = {i["avp"]: i["value"] for i in inner["value"]}
    return {
        "interface": kind,
        "msisdn_masked": _mask(msisdn),
        "result_code": flat.get("Result-Code"),
        "result": "SUCCESS" if flat.get("Result-Code") == RESULT_SUCCESS else "ERROR",
        "location_area_id": routing.get("Location-Area-Id"),
        "cell_global_id": routing.get("Cell-Global-Id"),
        "age_of_location_s": routing.get("Age-Of-Location"),
        "vlr_number": routing.get("VLR-Number"),
        "location_granularity": "cell (LAI+CGI via GMLC)" if routing else None,
        "answer_avps": [a["avp"] for a in ans["avps"]],
    }


def _mask(v: str | None, head: int = 4, tail: int = 2) -> str | None:
    if not v:
        return v
    v = str(v)
    if len(v) <= head + tail:
        return "*" * len(v)
    return v[:head] + "*" * (len(v) - head - tail) + v[-tail:]
