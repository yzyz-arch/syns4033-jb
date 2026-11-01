"""Email harvesting + pattern generation + optional SMTP verification.

Harvest order: live site pages -> archived URLs -> search-engine dorks.
Verification uses SMTP RCPT against the domain's MX; if egress port 25 is blocked
(common on cloud) the result says so explicitly instead of guessing.
"""
from __future__ import annotations

import concurrent.futures as cf
import re
import socket

from . import net
from .archives import wayback_urls
from .http import get_text

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}\b")
JUNK = re.compile(r"(?:sentry|wixpress|example\.com|example\.org|example\.net|domain\.com|"
                  r"email\.com|@2x|\.png|\.jpg|\.gif|\.svg|\.webp|\.css|\.js|no-?reply@|@sentry|"
                  r"@localhost|your@|test@test|user@domain|pass@|@proxy\.|@example\b|"
                  r"@(?:test|invalid|localhost|sample|mailinator)\b|\.(?:local|internal|invalid)$)",
                  re.I)

PAGES = ["", "/contact", "/contact-us", "/about", "/about-us", "/team", "/support",
         "/help", "/privacy", "/legal", "/imprint", "/careers", "/jobs", "/press"]


def _extract(text: str) -> set[str]:
    out = set()
    from urllib.parse import unquote
    # decode first: harvests often contain %7c-encoded mailto / tracking addresses
    text = unquote(text or "")
    for m in EMAIL_RE.finditer(text):
        e = m.group(0).lower().strip(".")
        if JUNK.search(e):
            continue
        out.add(e)
    # de-obfuscate common forms: "john [at] acme [dot] com", "john(at)acme.com"
    for m in re.finditer(r"([A-Za-z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|&#64;|\s+at\s+)\s*"
                         r"([A-Za-z0-9.\-]+(?:\s*(?:\[dot\]|\(dot\)|\.)\s*[A-Za-z0-9.\-]+)+)",
                         text or "", re.I):
        local = m.group(1)
        dom = re.sub(r"\s+", "", m.group(2))
        dom = re.sub(r"\[dot\]|\(dot\)", ".", dom, flags=re.I)
        dom = dom.strip(".").lower()
        if re.fullmatch(r"[a-z0-9.\-]+\.[a-z]{2,24}", dom):
            out.add(f"{local}@{dom}".lower())
    return out


def harvest_web(host: str, workers: int = 8) -> dict:
    from .http import fetch
    found: set[str] = set()
    checked: list[str] = []
    blocked = 0

    def one(path: str):
        r = fetch(f"https://{host}{path}", timeout=12, tries=1)
        return path, _extract(r.get("body") or ""), r.get("status"), r.get("blocked")

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for path, emails, status, is_blocked in ex.map(one, PAGES):
            checked.append(f"{host}{path} -> {status}{' (blocked)' if is_blocked else ''}")
            if is_blocked:
                blocked += 1
            found |= emails
    return {"emails": sorted(found), "pages_checked": checked, "blocked_pages": blocked}


def harvest_archive(host: str, limit: int = 1500) -> dict:
    urls = wayback_urls(host, limit=limit)
    found: set[str] = set()
    # archived contact pages are the highest yield; fetch a bounded sample
    cand = [u for u in urls if re.search(r"(contact|about|team|support|press|legal)", u, re.I)][:25]
    for u in cand:
        txt = get_text(u, tries=1, timeout=12)
        found |= _extract(txt or "")
    # also scrape any email literals present in archived URL paths
    found |= _extract(" ".join(urls))
    return {"emails": sorted(found), "archived_pages_fetched": len(cand)}


def harvest(host: str, use_archive: bool = True) -> dict:
    web = harvest_web(host)
    arch = harvest_archive(host) if use_archive else {"emails": []}
    allm = sorted(set(web["emails"]) | set(arch["emails"]))
    by_domain: dict[str, int] = {}
    for e in allm:
        d = e.split("@")[-1]
        by_domain[d] = by_domain.get(d, 0) + 1
    return {
        "host": host, "emails": allm, "count": len(allm),
        "by_domain": sorted(by_domain.items(), key=lambda kv: -kv[1]),
        "web": web["emails"], "archive": arch["emails"],
        "blocked_pages": web.get("blocked_pages", 0),
        "note": ("site edge blocked the crawler on some pages — zeros here do not "
                 "prove the domain publishes no addresses") if web.get("blocked_pages") else None,
    }


def generate_patterns(first: str, last: str, domain: str) -> list[str]:
    f, l = first.lower().strip(), last.lower().strip()
    fi, li = f[:1], l[:1]
    locals_ = [f"{f}.{l}", f"{f}{l}", f"{fi}{l}", f"{f}{li}", f"{f}_{l}", f"{l}.{f}",
               f"{l}{f}", f"{f}", f"{l}", f"{f}-{l}", f"{fi}.{l}", f"{f}.{li}",
               f"{l}{fi}", f"{f}{l[-1]}", f"{f}.{l}{li}"]
    out = sorted({f"{u}@{domain}" for u in locals_ if u})
    return out


def smtp_verify(email: str, timeout: float = 8.0, sender: str = "verify@example.org") -> dict:
    domain = email.split("@")[-1]
    mxs = net.mx(domain)
    if not mxs:
        return {"email": email, "result": "no-mx", "detail": "domain has no MX"}
    mx_host = mxs[0]["host"]
    if not mx_host:
        return {"email": email, "result": "null-mx", "detail": "domain publishes null MX (no mail)"}
    try:
        ip = net.resolve(mx_host) or mx_host
        with socket.create_connection((ip, 25), timeout=timeout) as s:
            s.settimeout(timeout)
            banner = s.recv(512).decode("latin-1", "replace").strip()

            def cmd(line: str) -> str:
                s.sendall((line + "\r\n").encode())
                return s.recv(512).decode("latin-1", "replace").strip()

            cmd("HELO osintkit.local")
            cmd(f"MAIL FROM:<{sender}>")
            resp = cmd(f"RCPT TO:<{email}>")
            cmd("QUIT")
            code = resp[:3]
            verdict = {"250": "exists", "251": "exists", "252": "maybe",
                       "550": "not-exists", "551": "not-exists", "553": "not-exists"}.get(code, "unknown")
            return {"email": email, "result": verdict, "mx": mx_host, "code": code,
                    "response": resp[:200], "banner": banner[:120]}
    except (socket.timeout, TimeoutError):
        return {"email": email, "result": "unverified", "mx": mx_host,
                "detail": "smtp timeout (port 25 filtered?)"}
    except OSError as e:
        return {"email": email, "result": "unverified", "mx": mx_host,
                "detail": f"port 25 blocked/unreachable: {e}"}
    except Exception as e:
        return {"email": email, "result": "unverified", "mx": mx_host, "detail": str(e)[:120]}


def verify_batch(emails: list[str], workers: int = 5) -> dict:
    out = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(smtp_verify, emails):
            out.append(r)
    summary: dict[str, int] = {}
    for r in out:
        summary[r["result"]] = summary.get(r["result"], 0) + 1
    return {"checked": len(out), "summary": summary, "results": out}
