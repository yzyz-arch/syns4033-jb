"""Host / network intelligence: Shodan InternetDB (keyless), port scan, service
banners, TLS certificate grab, HTTP surface per open port.
"""
from __future__ import annotations

import concurrent.futures as cf
import socket
import ssl

from .http import get_json, probe

TOP_100 = [
    21, 22, 23, 25, 53, 80, 81, 110, 111, 135, 139, 143, 161, 389, 443, 445, 465,
    512, 513, 514, 587, 631, 636, 873, 990, 993, 995, 1025, 1080, 1433, 1434, 1521,
    1723, 1883, 2049, 2082, 2083, 2086, 2087, 2095, 2096, 2181, 2222, 2375, 2376,
    3000, 3306, 3389, 3690, 4000, 4243, 4369, 4443, 4505, 4506, 5000, 5432, 5555,
    5601, 5672, 5900, 5901, 5984, 5985, 5986, 6000, 6379, 6443, 7001, 7002, 7077,
    8000, 8001, 8008, 8009, 8010, 8042, 8069, 8080, 8081, 8088, 8090, 8161, 8180,
    8443, 8500, 8834, 8880, 8888, 8983, 9000, 9001, 9042, 9060, 9090, 9092, 9100,
    9200, 9300, 9418, 9443, 10000, 10250, 11211, 15672, 27017, 27018, 50000, 50070,
]

HIGH_RISK_PORTS = {
    21: "ftp", 23: "telnet", 135: "msrpc", 139: "netbios", 445: "smb", 1433: "mssql",
    2375: "docker-api", 2376: "docker-tls", 3306: "mysql", 3389: "rdp", 5432: "postgres",
    5601: "kibana", 5900: "vnc", 6379: "redis", 8080: "http-alt", 9000: "app",
    9200: "elasticsearch", 11211: "memcached", 27017: "mongodb", 10250: "kubelet",
    15672: "rabbitmq-mgmt", 50070: "hdfs",
}


def internetdb(ip: str) -> dict:
    """Shodan InternetDB — keyless, returns ports/hostnames/cpes/vulns/tags."""
    d = get_json(f"https://internetdb.shodan.io/{ip}", tries=2, timeout=15)
    if isinstance(d, dict) and not d.get("detail"):
        return {
            "ports": d.get("ports") or [],
            "hostnames": d.get("hostnames") or [],
            "cpes": d.get("cpes") or [],
            "vulns": d.get("vulns") or [],
            "tags": d.get("tags") or [],
        }
    return {"ports": [], "hostnames": [], "cpes": [], "vulns": [], "tags": [],
            "detail": (d or {}).get("detail") if isinstance(d, dict) else "unreachable"}


def scan_ports(ip: str, ports: list[int] | None = None, timeout: float = 1.0,
               workers: int = 120) -> list[int]:
    ports = ports or TOP_100
    open_ports: list[int] = []

    def chk(p: int) -> int | None:
        try:
            with socket.create_connection((ip, p), timeout=timeout):
                return p
        except Exception:
            return None

    with cf.ThreadPoolExecutor(max_workers=min(workers, len(ports))) as ex:
        for p in ex.map(chk, ports):
            if p:
                open_ports.append(p)
    return sorted(open_ports)


def banner(ip: str, port: int, timeout: float = 3.0) -> str:
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.settimeout(timeout)
            try:
                if port in (80, 8080, 8000, 8888, 8008):
                    s.sendall(b"HEAD / HTTP/1.0\r\nHost: " + ip.encode() + b"\r\n\r\n")
                else:
                    s.sendall(b"\r\n")
            except Exception:
                pass
            data = s.recv(512)
            return data.decode("latin-1", "replace").strip()[:400]
    except Exception as e:
        return f"err:{type(e).__name__}"


def tls_peer(ip: str, port: int = 443, server_hostname: str | None = None,
             timeout: float = 8.0) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((ip, port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=server_hostname or ip) as ss:
                der = ss.getpeercert(binary_form=True)
                cert = ss.getpeercert()
                import hashlib
                out = {
                    "port": port,
                    "tls_version": ss.version(),
                    "cipher": (ss.cipher() or [None])[0],
                    "sha256": hashlib.sha256(der or b"").hexdigest() if der else None,
                    "subject": dict(x[0] for x in (cert or {}).get("subject", [])),
                    "issuer": dict(x[0] for x in (cert or {}).get("issuer", [])),
                    "san": [v for k, v in (cert or {}).get("subjectAltName", []) if k == "DNS"],
                    "not_after": (cert or {}).get("notAfter"),
                }
                return out
    except Exception as e:
        return {"port": port, "error": str(e)[:120]}


def http_surface(ip: str, ports: list[int], limit: int = 8) -> list[dict]:
    out = []
    http_like = [p for p in ports if p in (80, 81, 443, 8000, 8008, 8080, 8081, 8088,
                                           8443, 8888, 9000, 9090, 9443, 3000, 5000,
                                           5601, 9200, 15672, 2375, 10250)]
    for p in http_like[:limit]:
        scheme = "https" if p in (443, 8443, 9443) else "http"
        status, final, headers, body = probe(f"{scheme}://{ip}:{p}/", timeout=8)
        title = None
        import re
        if body:
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
            if m:
                title = m.group(1).strip()[:160]
        out.append({"port": p, "scheme": scheme, "status": status,
                    "server": headers.get("Server"), "title": title,
                    "final_url": final, "body_len": len(body or "")})
    return out


def host_report(ip: str, deep: bool = True) -> dict:
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        f_idb = ex.submit(internetdb, ip)
        idb = f_idb.result()
    out = {"ip": ip, "internetdb": idb}

    ports = idb.get("ports") or []
    if deep:
        scanned = scan_ports(ip)
        ports = sorted(set(ports) | set(scanned))
        out["scanned_ports"] = scanned
    out["open_ports"] = ports
    out["high_risk"] = [{"port": p, "service": HIGH_RISK_PORTS[p]} for p in ports if p in HIGH_RISK_PORTS]

    if deep and ports:
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            f_b = {p: ex.submit(banner, ip, p) for p in ports[:20]}
            out["banners"] = {str(p): f.result() for p, f in f_b.items()}
        out["http"] = http_surface(ip, ports)
        if 443 in ports:
            out["tls"] = tls_peer(ip, 443, (idb.get("hostnames") or [None])[0])
    return out
