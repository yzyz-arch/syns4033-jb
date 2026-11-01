"""DNS layer over DoH (JSON API) with cache, bulk resolve, CNAME chains.

DoH is used first because plain UDP/53 is frequently filtered on cloud hosts and
because it gives us SOA/CAA/TXT without depending on the local resolver config.
dnspython is only a fallback.
"""
from __future__ import annotations

import concurrent.futures as cf
import re
import time

DOH_ENDPOINTS = [
    ("https://dns.google/resolve", None),
    ("https://cloudflare-dns.com/dns-query", {"accept": "application/dns-json"}),
]

TYPE_NUM = {
    "A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "PTR": 12, "MX": 15, "TXT": 16,
    "AAAA": 28, "SRV": 33, "CAA": 257, "DS": 43, "DNSKEY": 48,
}

_CACHE: dict[tuple[str, str], tuple[float, dict | None]] = {}
_TTL = 600.0
_HOST_RE = re.compile(r"^[a-z0-9_]([a-z0-9_-]*[a-z0-9_])?(\.[a-z0-9_]([a-z0-9_-]*[a-z0-9_])?)+$")


def _doh(name: str, rtype: str, timeout: int = 8) -> dict | None:
    key = (name.lower().rstrip("."), rtype)
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    from . import http as http_mod
    s = http_mod.session()
    out = None
    for ep, hdrs in DOH_ENDPOINTS:
        try:
            r = s.get(ep, params={"name": key[0], "type": rtype},
                      headers=hdrs or {}, timeout=timeout)
            if r.status_code == 200:
                j = r.json()
                # Status 0 = NOERROR, 3 = NXDOMAIN (both are definitive answers)
                if isinstance(j, dict) and j.get("Status") in (0, 3):
                    out = j
                    break
        except Exception:
            continue
    _CACHE[key] = (now, out)
    return out


def query(name: str, rtype: str = "A") -> list[dict]:
    j = _doh(name, rtype)
    if not j:
        return []
    want = TYPE_NUM.get(rtype)
    return [a for a in (j.get("Answer") or []) if a.get("type") == want]


def _clean(data: str) -> str:
    return data.rstrip(".").strip()


def a(name: str) -> list[str]:
    return sorted({_clean(x.get("data", "")) for x in query(name, "A")})


def aaaa(name: str) -> list[str]:
    return sorted({_clean(x.get("data", "")) for x in query(name, "AAAA")})


def cname(name: str) -> list[str]:
    return sorted({_clean(x.get("data", "")) for x in query(name, "CNAME")})


def ns(name: str) -> list[str]:
    return sorted({_clean(x.get("data", "")) for x in query(name, "NS")})


def mx(name: str) -> list[dict]:
    out = []
    for x in query(name, "MX"):
        parts = str(x.get("data", "")).split()
        if len(parts) == 2:
            out.append({"priority": int(parts[0]), "host": _clean(parts[1])})
    return sorted(out, key=lambda d: d["priority"])


def txt(name: str) -> list[str]:
    out = []
    for x in query(name, "TXT"):
        raw = str(x.get("data", ""))
        raw = raw.replace('" "', "").strip('"')
        out.append(raw)
    return out


def soa(name: str) -> dict | None:
    rows = query(name, "SOA")
    if not rows:
        return None
    p = str(rows[0].get("data", "")).split()
    if len(p) >= 7:
        return {"mname": _clean(p[0]), "rname": _clean(p[1]), "serial": p[2],
                "refresh": p[3], "retry": p[4], "expire": p[5], "minimum": p[6]}
    return {"raw": rows[0].get("data")}


def caa(name: str) -> list[dict]:
    out = []
    for x in query(name, "CAA"):
        d = str(x.get("data", ""))
        m = re.match(r'(\d+)\s+(\w+)\s+"?([^"]+)"?', d)
        if m:
            out.append({"flags": int(m.group(1)), "tag": m.group(2), "value": m.group(3)})
    return out


def resolve(name: str) -> str | None:
    ips = a(name)
    return ips[0] if ips else None


def resolve_any(name: str) -> dict:
    """A + AAAA + CNAME in one shot (three cached DoH calls)."""
    return {"a": a(name), "aaaa": aaaa(name), "cname": cname(name)}


def cname_chain(name: str, maxdepth: int = 8) -> list[str]:
    """Follow the CNAME chain; returns every hop including the origin."""
    chain = [name]
    cur = name
    for _ in range(maxdepth):
        nxt = cname(cur)
        if not nxt:
            break
        cur = nxt[0]
        if cur in chain:
            break
        chain.append(cur)
    return chain


def bulk_resolve(names: list[str], workers: int = 60) -> dict[str, str]:
    """Resolve many hostnames concurrently -> {host: ip} for those that exist."""
    out: dict[str, str] = {}
    names = sorted(set(names))

    def one(h: str):
        try:
            ips = a(h)
            return h, (ips[0] if ips else None)
        except Exception:
            return h, None

    with cf.ThreadPoolExecutor(max_workers=min(workers, max(1, len(names)))) as ex:
        for h, ip in ex.map(one, names):
            if ip:
                out[h] = ip
    return out


def wildcard_probe(domain: str) -> dict:
    """Detect a wildcard DNS record by resolving a random label."""
    import secrets as _s
    label = "osintkit-wc-" + _s.token_hex(6)
    probe = f"{label}.{domain}"
    ips = a(probe)
    return {"wildcard": bool(ips), "probe": probe, "ips": ips}


def dedupe_hosts(hosts: list[str], domain: str | None = None) -> list[str]:
    """Lowercase, strip wildcards/trailing dots, keep only sane hostnames."""
    out = set()
    for h in hosts:
        h = str(h).strip().lower().lstrip("*.").rstrip(".")
        if not h or "@" in h or len(h) > 253:
            continue
        if not _HOST_RE.match(h):
            continue
        if domain and h != domain and not h.endswith("." + domain):
            continue
        out.add(h)
    return sorted(out)
