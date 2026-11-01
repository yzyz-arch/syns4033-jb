"""JavaScript intelligence: endpoint harvesting + secret/key pattern detection.

Reads the target's own JS (and archived JS) and runs a pattern bank over it:
cloud keys, SaaS tokens, private key blocks, internal hostnames, API routes,
sourcemap references. This is the single highest-yield OSINT step on modern apps
because the frontend bundle leaks the entire backend surface.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import re
from urllib.parse import urljoin, urlparse

from .http import get_text

SECRET_PATTERNS: list[tuple[str, str, str, str]] = [
    # (name, severity, regex, note)
    ("aws_access_key_id", "high", r"\b(AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{12,20}\b", "AWS access key id"),
    ("aws_secret_access_key", "critical", r"(?i)aws_?secret_?(?:access_?)?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})", "AWS secret key"),
    ("gcp_api_key", "high", r"\bAIza[0-9A-Za-z\-_]{35}\b", "Google API key"),
    ("gcp_oauth_client", "medium", r"\b[0-9]{12}-[0-9a-z]{32}\.apps\.googleusercontent\.com\b", "Google OAuth client id"),
    ("firebase_url", "medium", r"https://[a-z0-9-]+\.firebaseio\.com", "Firebase realtime DB"),
    ("firebase_config", "medium", r"apiKey\"?\s*:\s*\"AIza[0-9A-Za-z\-_]{35}\"", "Firebase config block"),
    ("stripe_secret", "critical", r"\bsk_(?:live|test)_[0-9a-zA-Z]{20,}\b", "Stripe secret key"),
    ("stripe_publishable", "low", r"\bpk_(?:live|test)_[0-9a-zA-Z]{20,}\b", "Stripe publishable key"),
    ("github_token", "critical", r"\bgh[pousr]_[0-9A-Za-z]{36,255}\b", "GitHub token"),
    ("gitlab_token", "critical", r"\bglpat-[0-9A-Za-z\-_]{20,}\b", "GitLab PAT"),
    ("slack_token", "critical", r"\bxox[abprs]-[0-9A-Za-z\-]{10,}\b", "Slack token"),
    ("slack_webhook", "high", r"https://hooks\.slack\.com/services/T[0-9A-Z]+/B[0-9A-Z]+/[0-9A-Za-z]+", "Slack webhook"),
    ("discord_webhook", "high", r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/[0-9]+/[0-9A-Za-z\-_]+", "Discord webhook"),
    ("sendgrid_key", "critical", r"\bSG\.[0-9A-Za-z\-_]{22}\.[0-9A-Za-z\-_]{43}\b", "SendGrid API key"),
    ("mailgun_key", "high", r"\bkey-[0-9a-zA-Z]{32}\b", "Mailgun key"),
    ("twilio_sid", "medium", r"\bAC[0-9a-f]{32}\b", "Twilio account SID"),
    ("twilio_auth_token", "critical", r"(?i)twilio.{0,20}['\"][0-9a-f]{32}['\"]", "Twilio auth token"),
    ("private_key_block", "critical", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----", "private key material"),
    ("jwt", "medium", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b", "JWT embedded in bundle"),
    ("mapbox_token", "medium", r"\bpk\.[0-9A-Za-z\-_\.]{60,}\b", "Mapbox token"),
    ("algolia_key", "medium", r"(?i)algolia.{0,40}['\"][0-9a-f]{32}['\"]", "Algolia admin key"),
    ("cloudinary_url", "medium", r"cloudinary://[0-9]+:[A-Za-z0-9\-_]+@[a-z0-9\-]+", "Cloudinary credentials in URL"),
    ("s3_bucket", "low", r"\b[a-z0-9][a-z0-9.\-]{2,61}\.s3(?:[.\-][a-z0-9\-]+)?\.amazonaws\.com\b", "S3 bucket reference"),
    ("azure_storage_key", "critical", r"(?i)AccountKey=[A-Za-z0-9+/=]{60,}", "Azure storage account key"),
    ("db_connection", "critical", r"(?i)(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s'\"<>]{10,}", "database URI"),
    ("basic_auth_url", "critical", r"https?://[^\s'\"<>/:@]+:[^\s'\"<>/:@]{4,}@[^\s'\"<>]+", "credentials in URL"),
    ("internal_ip", "low", r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b", "internal IP leak"),
    ("internal_host", "low", r"\bhttps?://(?:[a-z0-9\-]+\.)*(?:internal|intranet|corp|local|lan|dev\.|staging\.)[a-z0-9\.\-]*\b", "internal hostname"),
    ("email", "low", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "email address"),
    ("bearer_literal", "high", r"(?i)authorization['\"]?\s*[:=]\s*['\"]bearer\s+[A-Za-z0-9\-_\.]{20,}", "hardcoded bearer token"),
    ("basic_literal", "high", r"(?i)['\"]basic\s+[A-Za-z0-9+/=]{20,}['\"]", "hardcoded basic auth"),
    ("google_maps_key", "medium", r"\bAIza[0-9A-Za-z\-_]{35}\b", "Google Maps key"),
    ("leak_env", "high", r"(?i)(?:SECRET_KEY|API_SECRET|PRIVATE_KEY|ACCESS_TOKEN|AUTH_TOKEN)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "env-style secret assignment"),
]

ENDPOINT_PAT = re.compile(
    r"""["'`]((?:https?://[^\s"'`<>]{4,200})|(/(?:api|v\d+|graphql|rest|oauth|auth|admin|internal|_next|wp-json|ajax|services)[^\s"'`<>]{0,150}))["'`]""",
    re.I)
ABS_URL_PAT = re.compile(r"https?://[^\s\"'`<>\\)]{6,200}")
SOURCEMAP_PAT = re.compile(r"sourceMappingURL=([^\s*]+)")


def _mask(secret: str) -> str:
    s = secret.strip()
    if len(s) <= 10:
        return s[:2] + "*" * max(0, len(s) - 2)
    return s[:6] + "..." + s[-4:]


def scan_text(text: str, source: str, include_values: bool = True) -> list[dict]:
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for name, sev, pat, note in SECRET_PATTERNS:
        for m in re.finditer(pat, text):
            val = m.group(0)
            key = (name, val[:80])
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                "type": name, "severity": sev, "source": source,
                "value": val if include_values else _mask(val),
                "masked": _mask(val),
                "note": note,
                "offset": m.start(),
            })
    return findings


def _collect_js_urls(host: str) -> tuple[list[str], str | None, dict]:
    from .http import fetch
    meta = {"status": None, "blocked": False, "final_url": None, "error": None}
    for scheme in ("https", "http"):
        r = fetch(f"{scheme}://{host}/")
        meta = {"status": r.get("status"), "blocked": r.get("blocked"),
                "final_url": r.get("final_url"), "error": r.get("error")}
        body = r.get("body") or ""
        if body:
            break
    else:
        return [], None, meta
    base = meta.get("final_url") or f"https://{host}/"
    js = set()
    for m in re.finditer(r'<script[^>]+src=["\']([^"\']+)["\']', body, re.I):
        js.add(urljoin(base, m.group(1)))
    for m in re.finditer(r'["\']([^"\']+\.m?js(?:\?[^"\']*)?)["\']', body):
        cand = m.group(1)
        if cand.startswith("http") or cand.startswith("/"):
            js.add(urljoin(base, cand))
    return sorted(js)[:60], body, meta


_NOISE_URL = re.compile(
    r"(?:w3\.org/|schema\.org|json-schema\.org|xmlns|/2000/svg|/1999/xhtml|"
    r"example\.com|localhost|127\.0\.0\.1|%27$|%22$)", re.I)


def _clean_endpoint(u: str) -> str | None:
    u = u.strip().strip("'\"").rstrip(".,;)%20")
    if not u or len(u) < 3 or len(u) > 300:
        return None
    if _NOISE_URL.search(u):
        return None
    if u.startswith("http"):
        return u
    if u.startswith("/") and not u.startswith("//"):
        return u
    return None


def analyze(host: str, extra_js: list[str] | None = None, limit: int = 40,
            include_values: bool = True, workers: int = 10) -> dict:
    js_urls, body, meta = _collect_js_urls(host)
    if extra_js:
        js_urls = sorted(set(js_urls) | set(extra_js))[:limit]
    js_urls = js_urls[:limit]

    texts: list[tuple[str, str]] = []
    if body:
        texts.append((f"https://{host}/ (inline)", body))

    def fetch(u: str):
        return u, get_text(u, tries=1, timeout=15)

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for u, txt in ex.map(fetch, js_urls):
            if txt:
                texts.append((u, txt))

    findings: list[dict] = []
    endpoints: set[str] = set()
    hosts_seen: set[str] = set()
    sourcemaps: set[str] = set()
    for src, txt in texts:
        findings.extend(scan_text(txt, src, include_values=include_values))
        for m in ENDPOINT_PAT.finditer(txt):
            e = _clean_endpoint(m.group(1))
            if e:
                endpoints.add(e)
        for m in ABS_URL_PAT.finditer(txt):
            e = _clean_endpoint(m.group(0))
            if e:
                endpoints.add(e)
                try:
                    h = urlparse(e).hostname
                    if h:
                        hosts_seen.add(h)
                except Exception:
                    pass
        for m in SOURCEMAP_PAT.finditer(txt):
            sourcemaps.add(urljoin(src, m.group(1)))

    # dedupe findings by (type, value)
    uniq: dict[tuple[str, str], dict] = {}
    for f in findings:
        k = (f["type"], f["value"][:120])
        if k not in uniq:
            uniq[k] = f
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ordered = sorted(uniq.values(), key=lambda f: sev_rank.get(f["severity"], 9))

    return {
        "host": host,
        "http_status": meta.get("status"),
        "blocked": bool(meta.get("blocked")),
        "note": ("edge blocked the request (WAF/Akamai/Cloudflare or rate limit) — "
                 "re-run from a different egress IP; an empty result here is NOT "
                 "'no secrets'") if meta.get("blocked") else None,
        "js_files_scanned": len(js_urls),
        "js_urls": js_urls,
        "js_fingerprints": [{"url": u, "sha256": hashlib.sha256(
            next((t for s, t in texts if s == u), "").encode()).hexdigest()} for u in js_urls[:20]],
        "findings": ordered,
        "finding_counts": {s: sum(1 for f in ordered if f["severity"] == s)
                           for s in ("critical", "high", "medium", "low")},
        "endpoints": sorted(endpoints)[:400],
        "third_party_hosts": sorted(hosts_seen)[:200],
        "sourcemaps": sorted(sourcemaps)[:40],
    }


def fetch_sourcemap(url: str) -> dict:
    txt = get_text(url, tries=2, timeout=30)
    if not txt:
        return {"url": url, "ok": False}
    import json as _json
    try:
        d = _json.loads(txt)
    except Exception:
        return {"url": url, "ok": False, "error": "not json"}
    return {
        "url": url, "ok": True,
        "sources": (d.get("sources") or [])[:300],
        "source_count": len(d.get("sources") or []),
        "has_sources_content": bool(d.get("sourcesContent")),
    }
