"""Domain / web surface intelligence: whois, reverse-IP, TLS, headers, tech, robots, favicon, wayback."""
from __future__ import annotations
import hashlib
import socket
import ssl
import concurrent.futures as cf
from urllib.parse import urljoin

from .http import get_json, get_text, probe

SEC_HEADERS = [
    "strict-transport-security", "content-security-policy", "x-frame-options",
    "x-content-type-options", "referrer-policy", "permissions-policy",
    "cross-origin-opener-policy", "cross-origin-embedder-policy",
]

TECH_SIGNS = {
    "wordpress": ["wp-content", "wp-includes", "/wp-json"],
    "drupal": ["drupal-settings-json", "sites/default/files", "drupal.js"],
    "joomla": ["/media/jui/", "joomla", "com_content"],
    "react": ["react.production", "_next/static", "data-reactroot"],
    "nextjs": ["_next/static", "__NEXT_DATA__"],
    "vue": ["vue.runtime", "__vue__", "data-v-"],
    "angular": ["ng-version", "angular.min.js"],
    "jquery": ["jquery.min.js", "jquery-"],
    "nginx": ["server: nginx"], "apache": ["server: apache"],
    "cloudflare": ["cf-ray", "cloudflare"], "litespeed": ["litespeed"],
    "php": ["x-powered-by: php", ".php"],
    "aspnet": ["x-powered-by: asp.net", "x-aspnet-version"],
    "cloudfront": ["x-amz-cf-id", "cloudfront"],
    "varnish": ["x-varnish", "via: varnish"],
}


def whois_data(domain: str) -> dict:
    """Registration data via RDAP over HTTPS (whois/43 is often blocked). Falls back to python-whois."""
    d = get_json(f"https://rdap.org/domain/{domain}", tries=3, timeout=25)
    if isinstance(d, dict) and d.get("ldhName"):
        events = {e.get("eventAction"): e.get("eventDate") for e in d.get("events", [])}
        out = {
            "handle": d.get("handle"),
            "ldhName": d.get("ldhName"),
            "status": d.get("status"),
            "registrar": next((e.get("vcardArray", [None, []])[1] for e in d.get("entities", [])
                               if "registrar" in (e.get("roles") or [])), None),
            "nameservers": [n.get("ldhName") for n in d.get("nameservers", [])],
            "events": events,
            "secure_dns": d.get("secureDNS", {}).get("delegationSigned"),
        }
        if out["registrar"]:
            vc = out["registrar"]
            out["registrar"] = next((f[3] for f in vc if f and f[0] == "fn"), vc)
        return out
    try:
        import whois as whoislib
        w = whoislib.whois(domain, timeout=15, ignore_socket_errors=True)
        out = {}
        for k in ("domain_name", "registrar", "creation_date", "expiration_date",
                  "updated_date", "name_servers", "emails", "org", "country", "status"):
            v = w.get(k) if hasattr(w, "get") else getattr(w, k, None)
            if v:
                out[k] = str(v)[:300]
        return out or {"error": "no-data"}
    except Exception as e:
        return {"error": str(e)[:120]}


def tls_cert(host: str, port: int = 443) -> dict:
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=10) as s:
            with ctx.wrap_socket(s, server_hostname=host) as ss:
                c = ss.getpeercert()
                return {
                    "subject": dict(x[0] for x in c.get("subject", [])),
                    "issuer": dict(x[0] for x in c.get("issuer", [])),
                    "serial": c.get("serialNumber"),
                    "not_before": c.get("notBefore"),
                    "not_after": c.get("notAfter"),
                    "san": [v for k, v in c.get("subjectAltName", []) if k == "DNS"],
                    "tls_version": ss.version(),
                }
    except Exception as e:
        return {"error": str(e)[:160]}


def http_fingerprint(host: str) -> dict:
    status, final, headers, body = probe(f"https://{host}/")
    if status is None:
        status, final, headers, body = probe(f"http://{host}/")
    out = {"status": status, "final_url": final, "server": headers.get("Server"),
           "powered_by": headers.get("X-Powered-By"), "security_headers": {},
           "technologies": [], "title": None}
    for h in SEC_HEADERS:
        out["security_headers"][h] = headers.get(h)
    low = {k.lower(): (v or "") for k, v in headers.items()}
    hay = (" ".join(f"{k}: {v}" for k, v in low.items()) + " " + (body or "")).lower()
    for tech, signs in TECH_SIGNS.items():
        if any(s in hay for s in signs):
            out["technologies"].append(tech)
    if body:
        import re
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        if m:
            out["title"] = m.group(1).strip()[:200]
    return out


def robots_and_sitemap(host: str) -> dict:
    out = {"robots.txt": [], "sitemaps": [], "disallowed": []}
    txt = get_text(f"https://{host}/robots.txt", tries=2)
    if txt and "<html" not in txt[:200].lower():
        out["robots.txt"] = txt.splitlines()[:400]
        for line in txt.splitlines():
            l = line.strip()
            if l.lower().startswith("sitemap:"):
                out["sitemaps"].append(l.split(":", 1)[1].strip())
            if l.lower().startswith("disallow:"):
                p = l.split(":", 1)[1].strip()
                if p and p != "/":
                    out["disallowed"].append(p)
    for cand in ("/sitemap.xml", "/sitemap_index.xml"):
        sm = get_text(f"https://{host}{cand}", tries=1, timeout=10)
        if sm and ("<urlset" in sm or "<sitemapindex" in sm):
            out["sitemaps"].append(f"https://{host}{cand}")
    return out


def favicon_hash(host: str) -> dict:
    """mmh3-style favicon hash (Shodan-compatible needs mmh3 pkg; here shodan-compatible base64 hash)."""
    raw = None
    from .http import session
    s = session()
    for path in ("/favicon.ico", "/favicon.png"):
        try:
            r = s.get(f"https://{host}{path}", timeout=10)
            if r.status_code == 200 and r.content:
                raw = r.content
                break
        except Exception:
            continue
    if not raw:
        return {"favicon": None}
    import base64
    b64 = base64.encodebytes(raw)
    # Shodan uses mmh3.hash(base64-mime). Fall back to sha256 if mmh3 absent.
    try:
        import mmh3
        return {"favicon": f"https://{host}/favicon.ico", "mmh3": mmh3.hash(b64),
                "shodan_query": None}
    except Exception:
        return {"favicon": f"https://{host}/favicon.ico",
                "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def wayback_urls(host: str, limit: int = 200) -> list[str]:
    data = get_json("https://web.archive.org/cdx/search/cdx",
                    params={"url": f"{host}/*", "output": "json", "fl": "original",
                            "collapse": "urlkey", "limit": limit}, tries=3, timeout=40)
    if isinstance(data, list) and len(data) > 1:
        return sorted({row[0] for row in data[1:] if row and row[0].startswith("http")})
    return []


def js_endpoints(host: str) -> dict:
    """Fetch HTML, pull JS files, extract absolute/relative endpoints."""
    import re
    status, final, headers, body = probe(f"https://{host}/")
    if not body:
        return {"js_files": [], "endpoints": []}
    js_files = sorted({urljoin(final or f"https://{host}/", m)
                       for m in re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', body, re.I)})[:25]
    endpoints: set[str] = set()
    pat = re.compile(r'["\'](/(?:api|v[0-9]|graphql|rest|oauth|admin|internal|_next)[^"\'\s<>]{0,80})["\']')
    for u in [body] + [get_text(j, tries=1, timeout=10) or "" for j in js_files[:10]]:
        endpoints.update(pat.findall(u or ""))
    return {"js_files": js_files, "endpoints": sorted(endpoints)[:120]}


def reverse_ip(ip: str) -> dict:
    """Reverse-IP neighbourhood via hackertarget (free)."""
    txt = get_text(f"https://api.hackertarget.com/reverseiplookup/?q={ip}", tries=2)
    hosts = []
    if txt and "error" not in txt.lower() and "API count" not in txt:
        hosts = sorted({h.strip() for h in txt.splitlines() if h.strip()})
    return {"ip": ip, "domains": hosts[:200], "count": len(hosts)}


def correlate(host: str) -> dict:
    """Bundle the cheap local probes concurrently."""
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        f_tls = ex.submit(tls_cert, host)
        f_http = ex.submit(http_fingerprint, host)
        f_robots = ex.submit(robots_and_sitemap, host)
        f_who = ex.submit(whois_data, host)
        f_fav = ex.submit(favicon_hash, host)
        res = {k: f.result() for k, f in
               [("tls", f_tls), ("http", f_http), ("robots", f_robots),
                ("whois", f_who), ("favicon", f_fav)]}
    return res
