"""mDNS / DNS-SD discovery, stdlib only.

Two modes:
  * multicast  - classic link-local Bonjour enumeration (224.0.0.251:5353)
  * unicast    - send a QU-bit query straight at one host:5353; catches mDNS
                 responders that answer off-link (the mdns_recon trick)
"""

from __future__ import annotations

import socket
import struct
import time

from . import dnswire
from .services import SERVICE_TYPES

MDNS_GROUP = "224.0.0.251"
MDNS_PORT = 5353


def _collect(sock: socket.socket, seconds: float, handle) -> list[dict]:
    """Read replies until the deadline; feed each packet to `handle`."""
    results: list[dict] = []
    deadline = time.time() + seconds
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        sock.settimeout(max(0.05, remaining))
        try:
            data, addr = sock.recvfrom(4096)
        except (socket.timeout, TimeoutError):
            continue
        except OSError:
            break
        if not data:
            continue
        try:
            msg = dnswire.parse_message(data)
        except dnswire.DNSError:
            continue
        msg["from"] = addr[0]
        results.extend(handle(msg))
    return results


def query(target: str = MDNS_GROUP, port: int = MDNS_PORT, name: str | None = None,
          qtype: int = dnswire.TYPE_ANY, timeout: float = 3.0,
          repeat: int = 1) -> dict:
    """Send one DNS question and gather every reply.

    target may be a multicast group or a single host (unicast QU query).
    """
    name = name or dnswire.SERVICE_ENUM
    rows: list[dict] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 1)
    except OSError:
        pass
    try:
        sock.bind(("0.0.0.0", 0))
        sock.sendto(dnswire.build_query(name, qtype=qtype), (target, port))
        for _ in range(max(0, repeat - 1)):
            time.sleep(0.2)
            sock.sendto(dnswire.build_query(name, qtype=qtype), (target, port))
        rows = _collect(sock, timeout, lambda m: m["records"])
    finally:
        sock.close()
    return {"target": target, "port": port, "qname": name, "records": rows}


def enumerate_multicast(seconds: float = 6.0) -> dict:
    """Full DNS-SD sweep: ask for the service list, then resolve what came back."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", MDNS_PORT))
        mreq = struct.pack("=4sl", socket.inet_aton(MDNS_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    except OSError as exc:
        sock.close()
        return {"error": f"cannot open mDNS socket: {exc}", "service_types": [], "records": []}

    records: list[dict] = []
    try:
        # 1. service type enumeration
        for _ in range(3):
            sock.sendto(dnswire.build_query(dnswire.SERVICE_ENUM, qtype=dnswire.TYPE_PTR),
                        (MDNS_GROUP, MDNS_PORT))
            time.sleep(0.3)
        records = _collect(sock, seconds, lambda m: m["records"])

        # 2. resolve each advertised type + each instance found
        types = sorted({r["value"].rstrip(".") + "." for r in records
                        if r["type"] == "PTR" and r["value"]})
        for stype in types[:60]:
            sock.sendto(dnswire.build_query(stype, qtype=dnswire.TYPE_PTR), (MDNS_GROUP, MDNS_PORT))
        for _ in range(2):
            time.sleep(0.4)
            for stype in types[:60]:
                sock.sendto(dnswire.build_query(stype, qtype=dnswire.TYPE_PTR),
                            (MDNS_GROUP, MDNS_PORT))
        more = _collect(sock, seconds, lambda m: m["records"])
        records.extend(more)
    finally:
        sock.close()

    service_types = sorted({r["value"].rstrip(".") + "." for r in records
                            if r["type"] == "PTR" and r["value"]})
    return {"service_types": service_types, "records": records}


def instance_name_from_ptr(ptr_value: str, stype: str) -> str:
    """A PTR value is 'Instance.<service>.<domain>' -> return just the instance."""
    suffix = "." + stype.rstrip(".")
    ptr = ptr_value.rstrip(".")
    if ptr.lower().endswith(suffix.lower()):
        return ptr[: len(ptr) - len(suffix)]
    return ptr


def build_service_map(records: list[dict]) -> list[dict]:
    """Fold PTR + SRV + TXT + A records into one row per discovered service."""
    srvs: dict[str, dict] = {}
    txts: dict[str, list[str]] = {}
    addrs: dict[str, str] = {}
    for r in records:
        key = r["name"].rstrip(".").lower()
        if r["type"] == "SRV" and isinstance(r["value"], dict):
            srvs[key] = r["value"]
        elif r["type"] == "TXT" and isinstance(r["value"], list):
            txts[key] = r["value"]
        elif r["type"] == "A" and isinstance(r["value"], str):
            addrs[key] = r["value"]

    rows: list[dict] = []
    for r in records:
        if r["type"] != "PTR" or not r["value"]:
            continue
        instance = r["value"].rstrip(".")
        stype = instance.split(".", 1)[1] + "." if "." in instance else ""
        srv = srvs.get(instance.lower(), {})
        target = (srv.get("target") or "").rstrip(".")
        meta = SERVICE_TYPES.get(stype.lower(), {})
        rows.append({
            "instance": instance.split(".")[0] if "." in instance else instance,
            "service_type": stype,
            "label": meta.get("label", "unknown service"),
            "risk": meta.get("risk", "info"),
            "notes": meta.get("notes", ""),
            "hostname": target,
            "port": srv.get("port", meta.get("port", 0)),
            "ip": addrs.get(target.lower(), ""),
            "txt": txts.get(instance.lower(), []),
        })
    # dedupe
    seen = set()
    out = []
    for row in rows:
        key = (row["instance"], row["service_type"], row["hostname"], row["port"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return sorted(out, key=lambda r: (r["hostname"], r["service_type"], r["instance"]))
