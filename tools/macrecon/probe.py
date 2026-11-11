"""TCP / RFB / EPPC probing for macOS remote-access services."""

from __future__ import annotations

import socket
import struct
from concurrent.futures import ThreadPoolExecutor

from .services import PORTS, RFB_SECURITY_TYPES


def tcp_probe(host: str, port: int, timeout: float = 2.0) -> dict:
    """Plain connect probe. No payload, no auth."""
    result = {"host": host, "port": port, "state": "closed", "banner": ""}
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        result["state"] = "open"
        try:
            sock.settimeout(1.0)
            data = sock.recv(512)
            if data:
                result["banner"] = data[:200].decode("utf-8", "replace").strip()
        except (socket.timeout, TimeoutError, OSError):
            pass
    except (ConnectionRefusedError, socket.timeout, TimeoutError):
        result["state"] = "closed"
    except OSError as exc:
        result["state"] = "error"
        result["error"] = str(exc)
    finally:
        sock.close()
    return result


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed early")
        buf += chunk
    return buf


def _parse_minor(version: str) -> int:
    """'RFB 003.889' -> 889 ; 'RFB 003.008' -> 8 ; unknown -> 8 (u8 form)."""
    try:
        _, num = version.split(None, 1)
        _, minor = num.split(".", 1)
        return int(minor)
    except (ValueError, AttributeError):
        return 8


def rfb_fingerprint(host: str, port: int = 5900, timeout: float = 3.0,
                    auth_peek: bool = False) -> dict:
    """Walk the RFB handshake far enough to learn the version and security types.

    Reads the protocol banner, selects the server's advertised type list, and
    (with auth_peek) pulls the first challenge block so you can prove the auth
    step is live without submitting credentials.
    """
    out = {
        "host": host,
        "port": port,
        "state": "closed",
        "version": "",
        "apple_screensharing": False,
        "security_types": [],
        "security_detail": [],
        "auth_peek": "",
        "error": "",
    }
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        out["state"] = "open"

        banner = _recv_exact(sock, 12)
        version = banner.decode("ascii", "replace").strip()
        out["version"] = version
        minor = _parse_minor(version)
        # Apple Screen Sharing speaks RFB 003.889; classic VNC tops out at 003.008
        out["apple_screensharing"] = minor > 8

        reply = version if version.startswith("RFB ") else "RFB 003.008"
        sock.sendall(reply.encode("ascii"))

        # RFC 6143: 3.3 sends a u32 count + u32 per type. 3.7/3.8/3.889 send a
        # u8 count, then one byte per type, then 3 padding bytes.
        types: list[int] = []
        if minor <= 3:
            count = struct.unpack(">I", _recv_exact(sock, 4))[0]
            if 0 < count <= 32:
                types = [struct.unpack(">I", _recv_exact(sock, 4))[0] for _ in range(count)]
        else:
            count = _recv_exact(sock, 1)[0]
            if 0 < count <= 32:
                types = list(struct.unpack(f">{count}B", _recv_exact(sock, count)))
                _recv_exact(sock, 3)  # padding

        out["security_types"] = types
        out["security_detail"] = [
            {"id": t, **RFB_SECURITY_TYPES.get(t, {"name": f"type {t}", "note": "unmapped"})}
            for t in types
        ]

        if auth_peek and types:
            sock.sendall(struct.pack(">B", types[0]))
            if types[0] == 2:
                challenge = _recv_exact(sock, 16)
                out["auth_peek"] = f"VNC DES challenge received ({len(challenge)} bytes): {challenge.hex()}"
            elif types[0] in (30, 36):
                srp = _recv_exact(sock, 16)
                out["auth_peek"] = f"Apple auth first block ({len(srp)} bytes): {srp.hex()}"
            elif types[0] == 1:
                out["auth_peek"] = "SecurityResult bypass candidate: type 1 accepts no credential"
            else:
                out["auth_peek"] = f"selected type {types[0]}; extra data follows"
    except (ConnectionError, socket.timeout, TimeoutError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        if out["state"] == "closed":
            out["state"] = "unreachable"
    except OSError as exc:
        out["error"] = str(exc)
    finally:
        sock.close()
    return out


def eppc_probe(host: str, port: int = 3031, timeout: float = 2.0) -> dict:
    """Remote Apple Events reachability. TCP open + AEServer banner."""
    res = tcp_probe(host, port, timeout)
    res["service"] = "Remote Apple Events / EPPC (com.apple.AEServer)"
    if res["state"] == "open":
        res["note"] = ("Service enabled. With valid credentials: "
                       "osascript -e 'tell application \"Finder\" of machine \"eppc://user:pass@%s\" "
                       "to get name of startup disk'" % host)
    return res


def probe_host(host: str, ports: list[int] | None = None, timeout: float = 2.0,
                concurrency: int = 32) -> dict:
    ports = ports or sorted(PORTS)
    with ThreadPoolExecutor(max_workers=min(concurrency, len(ports))) as pool:
        results = list(pool.map(lambda p: tcp_probe(host, p, timeout), ports))
    open_ports = [r for r in results if r["state"] == "open"]
    rfb = None
    if any(r["port"] == 5900 for r in open_ports):
        rfb = rfb_fingerprint(host, 5900, timeout=timeout, auth_peek=True)
    return {
        "host": host,
        "scanned": ports,
        "open": open_ports,
        "rfb": rfb,
        "services": [PORTS[r["port"]] for r in open_ports if r["port"] in PORTS],
    }
