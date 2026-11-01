"""Historical / archive intelligence: Wayback CDX, CommonCrawl index, urlscan.io.

The value here is not "old URLs" — it is parameters, forgotten endpoints, secrets
in archived JS and infrastructure that is no longer linked but still reachable.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlparse

from .http import get_json, get_text

INTERESTING_EXT = (
    ".env", ".git", ".svn", ".bak", ".backup", ".old", ".sql", ".db", ".sqlite",
    ".zip", ".tar", ".tar.gz", ".tgz", ".rar", ".7z", ".log", ".conf", ".config",
    ".ini", ".yml", ".yaml", ".json", ".xml", ".csv", ".xls", ".xlsx", ".pdf",
    ".doc", ".docx", ".pptx", ".key", ".pem", ".p12", ".pfx", ".jks", ".keystore",
    ".map", ".swagger", ".openapi", ".graphql", ".wsdl", ".asmx", ".php~",
)


def wayback_urls(host: str, limit: int = 2000, collapse: bool = True,
                 match_type: str = "domain") -> list[str]:
    params = {
        "url": f"{host}/*" if match_type == "domain" else host,
        "output": "json",
        "fl": "original,timestamp,mimetype,statuscode",
        "limit": limit,
    }
    if collapse:
        params["collapse"] = "urlkey"
    data = get_json("https://web.archive.org/cdx/search/cdx", params=params,
                    tries=3, timeout=60)
    if not isinstance(data, list) or len(data) < 2:
        return []
    return sorted({row[0] for row in data[1:] if row and row[0].startswith("http")})


def wayback_records(host: str, limit: int = 2000) -> list[dict]:
    data = get_json("https://web.archive.org/cdx/search/cdx",
                    params={"url": f"{host}/*", "output": "json",
                            "fl": "original,timestamp,mimetype,statuscode,length",
                            "limit": limit, "collapse": "urlkey"},
                    tries=3, timeout=60)
    if not isinstance(data, list) or len(data) < 2:
        return []
    head = data[0]
    out = []
    for row in data[1:]:
        rec = dict(zip(head, row))
        if rec.get("original", "").startswith("http"):
            out.append(rec)
    return out


def interesting_urls(urls: list[str]) -> dict:
    buckets: dict[str, list[str]] = {}
    for u in urls:
        path = urlparse(u).path.lower()
        for ext in INTERESTING_EXT:
            if path.endswith(ext):
                buckets.setdefault(ext, []).append(u)
                break
    return {k: sorted(set(v))[:200] for k, v in sorted(buckets.items())}


def param_mining(urls: list[str]) -> dict:
    """Unique query parameters + how often each appears -> attack-surface hints."""
    counts: dict[str, int] = {}
    hosts: dict[str, int] = {}
    for u in urls:
        p = urlparse(u)
        for k, _ in parse_qsl(p.query, keep_blank_values=True):
            counts[k] = counts.get(k, 0) + 1
        if p.netloc:
            hosts[p.netloc] = hosts.get(p.netloc, 0) + 1
    hot = sorted(counts.items(), key=lambda kv: -kv[1])
    return {"params": hot[:200], "param_count": len(counts),
            "hosts": sorted(hosts.items(), key=lambda kv: -kv[1])[:100]}


def wayback_js(host: str, limit: int = 2000) -> list[str]:
    urls = wayback_urls(host, limit=limit)
    return [u for u in urls if re.search(r"\.js(\?|$)", u, re.I)][:300]


def commoncrawl(host: str, limit: int = 500) -> dict:
    coll = get_json("https://index.commoncrawl.org/collinfo.json", tries=2, timeout=20)
    if not isinstance(coll, list) or not coll:
        return {"error": "commoncrawl index list unavailable", "urls": []}
    latest = coll[0].get("id") or "CC-MAIN-2024-10"
    txt = get_text(f"https://index.commoncrawl.org/{latest}-index",
                   params={"url": f"{host}/*", "output": "json", "limit": limit},
                   tries=3, timeout=60)
    urls: list[str] = []
    if txt:
        import json as _json
        for line in txt.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                rec = _json.loads(line)
            except Exception:
                continue
            if rec.get("url"):
                urls.append(rec["url"])
    return {"index": latest, "urls": sorted(set(urls))[:limit], "count": len(set(urls))}


def urlscan_search(host: str, size: int = 100) -> dict:
    d = get_json("https://urlscan.io/api/v1/search/",
                 params={"q": f"domain:{host}", "size": size}, tries=2, timeout=30)
    if not isinstance(d, dict):
        return {"error": "urlscan unreachable", "results": []}
    results = []
    for r in d.get("results") or []:
        results.append({
            "scan_id": r.get("_id"),
            "page_url": (r.get("page") or {}).get("url"),
            "page_domain": (r.get("page") or {}).get("domain"),
            "ip": (r.get("page") or {}).get("ip"),
            "asn": (r.get("page") or {}).get("asnname"),
            "country": (r.get("page") or {}).get("country"),
            "server": (r.get("page") or {}).get("server"),
            "status": (r.get("page") or {}).get("status"),
            "task_time": (r.get("task") or {}).get("time"),
            "screenshot": (r.get("task") or {}).get("screenshotURL"),
            "dom": (r.get("task") or {}).get("domURL"),
        })
    return {"total": d.get("total"), "results": results}


def urlscan_requests(scan_id: str, limit: int = 300) -> list[str]:
    """Every URL a scan touched (from the result JSON) -> hidden endpoints + third parties."""
    d = get_json(f"https://urlscan.io/api/v1/result/{scan_id}/", tries=2, timeout=40)
    if not isinstance(d, dict):
        return []
    urls: set[str] = set()
    for req in (d.get("data") or {}).get("requests", [])[:limit]:
        u = ((req.get("request") or {}).get("request") or {}).get("url")
        if u:
            urls.add(u)
    return sorted(urls)


def urlscan_dom(scan_id: str) -> dict:
    txt = get_text(f"https://urlscan.io/dom/{scan_id}/", tries=2, timeout=40)
    if not txt:
        return {"dom": None}
    return {"dom": txt, "size": len(txt)}


def archive_dossier(host: str, limit: int = 2000) -> dict:
    urls = wayback_urls(host, limit=limit)
    return {
        "wayback": {"count": len(urls), "urls": urls[:limit]},
        "interesting": interesting_urls(urls),
        "params": param_mining(urls),
        "commoncrawl": commoncrawl(host, limit=min(limit, 500)),
        "urlscan": urlscan_search(host, size=50),
    }
