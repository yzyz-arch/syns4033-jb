"""IP / network intel: geolocation, ASN, reverse DNS, socket port probe, TLS SNI cert."""
from __future__ import annotations
import concurrent.futures as cf
import socket

from .http import get_json

TOP_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 465, 587, 993, 995,
             1433, 1521, 3306, 3389, 5432, 5900, 6379, 8000, 8080, 8443, 8888,
             9200, 11211, 27017]


def geo(ip: str) -> dict:
    d = get_json(f"http://ip-api.com/json/{ip}",
                 params={"fields": "status,message,country,regionName,city,zip,lat,lon,"
                                   "timezone,isp,org,as,asname,reverse,mobile,proxy,hosting,query"})
    return d or {"status": "fail", "query": ip}


def reverse_dns(ip: str) -> list[str]:
    try:
        host, aliases, _ = socket.gethostbyaddr(ip)
        return [host] + aliases
    except Exception:
        return []


def scan_ports(ip: str, ports: list[int] | None = None, timeout: float = 1.2,
               workers: int = 100) -> dict:
    ports = ports or TOP_PORTS
    open_ports = []

    def chk(p):
        try:
            with socket.create_connection((ip, p), timeout=timeout):
                return p
        except Exception:
            return None

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for p in ex.map(chk, ports):
            if p:
                open_ports.append(p)
    return {"ip": ip, "open_ports": sorted(open_ports), "scanned": len(ports)}


def banner(ip: str, port: int, timeout: float = 3.0) -> str:
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.settimeout(timeout)
            try:
                s.sendall(b"\r\n")
            except Exception:
                pass
            data = s.recv(256)
            return data.decode("latin-1", "replace").strip()[:200]
    except Exception as e:
        return f"err:{e}"[:120]


def asn_lookup(ip: str) -> dict:
    """Hackertarget ASN lookup (free, no key)."""
    from .http import get_text
    txt = get_text(f"https://api.hackertarget.com/aslookup/?q={ip}", tries=2)
    if txt and "error" not in txt.lower():
        parts = [p.strip().strip('"') for p in txt.split(",")]
        return {"ip": ip, "data": parts}
    return {"ip": ip, "data": None}


def intel(ip: str, ports: bool = False) -> dict:
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        f_geo = ex.submit(geo, ip)
        f_rdns = ex.submit(reverse_dns, ip)
        f_asn = ex.submit(asn_lookup, ip)
        out = {"ip": ip, "geo": f_geo.result(), "reverse_dns": f_rdns.result(),
               "asn": f_asn.result()}
    if ports:
        sc = scan_ports(ip)
        out["ports"] = sc
        out["banners"] = {p: banner(ip, p) for p in sc["open_ports"][:12]}
    return out
