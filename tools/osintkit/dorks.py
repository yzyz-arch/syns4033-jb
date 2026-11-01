"""Search-engine dork generation + execution (DuckDuckGo lite, Google fallback).

Dorks are generated per target class (domain / org / email / person / username)
so the operator gets copy-paste queries for every engine plus an automatic
harvest of whatever the keyless engines will return.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

EXPOSED = ["env", "git", "sql", "bak", "log", "config", "ini", "yml", "json", "xml",
           "sqlite", "db", "zip", "tar.gz", "backup", "old", "swp", "DS_Store"]
DOC_TYPES = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "txt", "rtf"]
PANELS = ["admin", "login", "dashboard", "phpmyadmin", "wp-admin", "jenkins", "grafana",
          "kibana", "portainer", "jira", "confluence", "gitlab", "sonar", "webmail",
          "cpanel", "plesk", "swagger", "api-docs", "actuator", "server-status"]


def domain_dorks(domain: str) -> dict[str, list[str]]:
    d = domain
    out: dict[str, list[str]] = {
        "google": [
            f"site:{d}",
            f"site:{d} -www",
            f"site:*{d}",
            f"site:{d} inurl:admin",
            f"site:{d} inurl:login | inurl:signin | inurl:auth",
            f"site:{d} inurl:api | inurl:graphql | inurl:swagger",
            f"site:{d} inurl:dev | inurl:staging | inurl:test | inurl:uat",
            f"site:{d} ext:env | ext:ini | ext:conf",
            f"site:{d} ext:sql | ext:db | ext:sqlite",
            f"site:{d} ext:log | ext:bak | ext:old | ext:backup",
            f"site:{d} ext:git | inurl:.git",
            f"site:{d} intitle:\"index of\"",
            f"site:{d} \"index of /\"",
            f"site:{d} intext:\"sql syntax near\" | intext:\"Warning: mysql\"",
            f"site:{d} intext:@gmail.com | intext:@yahoo.com",
            f"site:{d} \"api_key\" | \"apikey\" | \"secret\"",
            f"site:{d} \"BEGIN RSA PRIVATE KEY\" | \"BEGIN OPENSSH PRIVATE KEY\"",
            f"site:{d} \"access_token\" | \"refresh_token\"",
            f"site:{d} inurl:\".well-known\" | inurl:\"security.txt\"",
            f"site:{d} inurl:phpinfo.php | inurl:info.php",
            f"site:{d} inurl:jenkins | inurl:grafana | inurl:kibana | inurl:portainer",
            f"site:{d} inurl:swagger-ui.html | inurl:openapi.json | inurl:/v2/api-docs",
            f"site:{d} inurl:actuator/env | inurl:actuator/heapdump",
            f"site:{d} \"Index of /\" + \"backup\"",
            f"site:pastebin.com \"{d}\"",
            f"site:trello.com \"{d}\"",
            f"site:docs.google.com \"{d}\"",
            f"site:s3.amazonaws.com \"{d}\"",
            f"site:blob.core.windows.net \"{d}\"",
            f"site:storage.googleapis.com \"{d}\"",
        ],
        "bing": [
            f"site:{d} filetype:env",
            f"site:{d} filetype:sql",
            f"site:{d} inurl:admin",
            f"site:{d} \"index of\"",
            f"ip:{d}",
        ],
        "github": [
            f"\"{d}\" password",
            f"\"{d}\" api_key",
            f"\"{d}\" secret",
            f"\"@{d}\"",
            f"org:{d.split('.')[0]}",
            f"\"{d}\" filename:.env",
            f"\"{d}\" filename:config.json",
            f"\"{d}\" \"BEGIN RSA PRIVATE KEY\"",
        ],
        "shodan": [
            f"hostname:{d}",
            f"ssl:\"{d}\"",
            f"http.title:\"{d}\"",
            f"org:\"{d.split('.')[0]}\"",
            f"ssl.cert.subject.CN:\"{d}\" 200",
        ],
        "censys": [f'"{d}"', f"services.tls.certificates.leaf_data.subject.common_name: \"{d}\""],
        "wayback": [f"{d}/*"],
    }
    return out


def org_dorks(org: str) -> dict[str, list[str]]:
    q = org.strip()
    return {
        "google": [
            f'"{q}" filetype:pdf',
            f'"{q}" (confidential | internal | proprietary)',
            f'"{q}" "api key" | "apikey" | "token"',
            f'"{q}" site:pastebin.com',
            f'"{q}" site:github.com',
            f'"{q}" email list | "mailing list"',
            f'"{q}" "invoice" filetype:pdf',
            f'"{q}" "org chart" | "organization chart"',
            f'"{q}" "vpn" | "citrix" | "remote access"',
        ],
        "linkedin": [f'site:linkedin.com/company "{q}"', f'site:linkedin.com/in "{q}"'],
        "github": [f'"{q}"', f'org:{q.replace(" ", "-").lower()}'],
        "shodan": [f'org:"{q}"'],
    }


def email_dorks(email: str) -> dict[str, list[str]]:
    local, _, dom = email.partition("@")
    return {
        "google": [
            f'"{email}"',
            f'"{local}" "{dom}"',
            f'"{email}" password',
            f'"{email}" filetype:pdf',
            f'"{email}" site:pastebin.com',
            f'"{email}" -site:{dom}',
        ],
        "github": [f'"{email}"', f'"{local}"'],
        "haveibeenpwned": [email],
    }


def person_dorks(name: str) -> dict[str, list[str]]:
    n = name.strip()
    return {
        "google": [
            f'"{n}"',
            f'"{n}" (email | contact | phone)',
            f'"{n}" site:linkedin.com',
            f'"{n}" site:facebook.com | site:instagram.com | site:x.com',
            f'"{n}" filetype:pdf',
            f'"{n}" resume | cv',
            f'"{n}" "date of birth" | DOB',
            f'"{n}" site:gov | site:edu',
        ],
        "github": [f'"{n}"'],
        "truepeoplesearch": [n],
    }


def username_dorks(u: str) -> dict[str, list[str]]:
    return {
        "google": [
            f'"{u}"',
            f'"{u}" (site:github.com | site:gitlab.com)',
            f'"{u}" (site:reddit.com | site:news.ycombinator.com)',
            f'"{u}" "@gmail.com" | "@protonmail.com"',
            f'inurl:"{u}" -site:facebook.com',
            f'site:pastebin.com "{u}"',
        ],
        "github": [f'"{u}" in:login', f'author:{u}'],
        "keybase": [u],
    }


def _curl(url: str, timeout: int = 25, referer: str = "https://search.brave.com/") -> str:
    """Fetch via the curl binary.

    Python's TLS fingerprint (JA3) is rejected by Brave/Bing with 429 while the
    same request from curl returns 200, so search traffic goes through curl.
    """
    import subprocess
    from .http import UA_POOL
    import random
    cmd = ["curl", "-s", "-L", "--compressed", "--max-time", str(timeout),
           "-A", random.choice(UA_POOL),
           "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9",
           "-H", "Accept-Language: en-US,en;q=0.9",
           "-H", f"Referer: {referer}",
           url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 8)
        return r.stdout or ""
    except Exception:
        return ""


def _brave(q: str, timeout: int = 25) -> list[dict]:
    """Brave Search HTML — the most bot-tolerant keyless engine for this host."""
    from urllib.parse import quote_plus
    html = _curl(f"https://search.brave.com/search?q={quote_plus(q)}&source=web", timeout)
    if not html:
        return []
    results: list[dict] = []
    seen: set[str] = set()
    for block in html.split('<div class="snippet ')[1:]:
        m = re.search(r'<a href="(https?://[^"]+)"[^>]*class="[^"]*\bl1\b', block)
        if not m:
            continue
        url = m.group(1)
        if "brave.com" in url or url in seen:
            continue
        seg = block[m.start():m.start() + 1500]
        title = re.sub(r"<[^>]+>", " ", seg)
        title = re.sub(r"\s+", " ", title).strip()[:200]
        seen.add(url)
        results.append({"url": url, "title": title})
    return results


def _bing(q: str, timeout: int = 25) -> list[dict]:
    """Bing HTML. b_algo blocks; outbound URL decoded from the ck/a redirect."""
    from urllib.parse import quote_plus
    html = _curl(f"https://www.bing.com/search?q={quote_plus(q)}&count=30", timeout,
                 referer="https://www.bing.com/")
    if not html:
        return []
    out, seen = [], set()
    for block in re.findall(r'<li class="b_algo".*?</li>', html, re.S):
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        url = m.group(1).replace("&amp;", "&")
        um = re.search(r"[?&]u=a1([A-Za-z0-9_\-]+)", url)
        if um:
            import base64
            raw = um.group(1)
            pad = "=" * (-len(raw) % 4)
            try:
                url = base64.urlsafe_b64decode(raw + pad).decode("utf-8", "replace")
            except Exception:
                continue
        if not url.startswith("http") or "bing.com" in url or url in seen:
            continue
        seen.add(url)
        title = re.sub(r"<[^>]+>", " ", m.group(2))
        out.append({"url": url, "title": re.sub(r"\s+", " ", title).strip()[:200]})
    return out


def _ddg(q: str, timeout: int = 20) -> list[dict]:
    """DuckDuckGo html/lite. Often 202-challenges; kept as last resort."""
    from urllib.parse import quote_plus, parse_qs
    results, seen = [], set()
    for base in ("https://html.duckduckgo.com/html/?q=", "https://lite.duckduckgo.com/lite/?q="):
        html = _curl(base + quote_plus(q), timeout, referer="https://duckduckgo.com/")
        if "result__a" not in html and "result-link" not in html:
            continue
        for m in re.finditer(r'<a[^>]+class="(?:result__a|result-link)"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                             html, re.S):
            href = m.group(1)
            if "uddg=" in href:
                qs = parse_qs(urlparse(href).query)
                href = (qs.get("uddg") or [href])[0]
            href = unquote(href)
            if not href.startswith("http") or href in seen:
                continue
            seen.add(href)
            results.append({"url": href,
                            "title": re.sub(r"<[^>]+>", "", m.group(2)).strip()[:200]})
        if results:
            return results
    return []


ENGINES = {"brave": _brave, "bing": _bing, "ddg": _ddg}
_STOP = {"site", "filetype", "inurl", "intitle", "intext", "ext", "filetype", "and", "or",
         "the", "not", "with", "from", "http", "https", "www"}


def _relevant(query: str, results: list[dict]) -> list[dict]:
    """Drop engine noise. Bing in particular returns unrelated pages when it
    decides the client is a bot, so every literal anchor in the query must show
    up in the result URL/title (operators like site:/inurl: are handled)."""
    anchors: list[str] = []
    site = re.search(r"site:([^\s]+)", query)
    if site:
        anchors.append(site.group(1).lstrip("*.").lower())
    inurl = re.search(r"inurl:([^\s]+)", query)
    if inurl:
        anchors.append(inurl.group(1).lower())
    for q in re.findall(r'"([^"]{3,})"', query):
        anchors.append(q.lower())
    stripped = re.sub(r"\b(?:site|inurl|intitle|intext|filetype|ext):\S+", " ", query)
    for tok in re.split(r"[^A-Za-z0-9._\-]+", stripped):
        t = tok.lower().strip("._-")
        if len(t) > 3 and t not in _STOP:
            anchors.append(t)
    if not anchors:
        return results
    keep = []
    for r in results:
        hay = (r["url"] + " " + (r.get("title") or "")).lower()
        if all(a in hay for a in anchors):
            keep.append(r)
    return keep


def _search(q: str, engine: str = "auto") -> list[dict]:
    """Search with fallback: brave -> bing -> ddg, then relevance-filter."""
    order = [engine] if engine in ENGINES else ["brave", "bing", "ddg"]
    for name in order:
        hits = _relevant(q, ENGINES[name](q))
        if hits:
            for h in hits:
                h["engine"] = name
            return hits
    return []


def run_dorks(queries: list[str], limit_per_query: int = 10,
              engine: str = "auto", delay: float = 1.2) -> dict:
    import time as _t
    out = []
    for i, q in enumerate(queries):
        hits = _search(q, engine)[:limit_per_query]
        out.append({"query": q, "results": hits, "count": len(hits)})
        if i + 1 < len(queries):
            _t.sleep(delay)
    total = sum(x["count"] for x in out)
    return {"queries": len(queries), "total_results": total,
            "engine": engine, "results": out}
