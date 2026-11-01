"""Shared HTTP layer: rotating UA, retries, timeouts, optional proxy."""
from __future__ import annotations
import random, time, json
import requests

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]


def session(proxy: str | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(UA_POOL),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    })
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


def get_json(url: str, *, proxy: str | None = None, headers: dict | None = None,
             params: dict | None = None, tries: int = 3, timeout: int = 20):
    """GET returning parsed JSON or None. Retries with backoff on 429/5xx."""
    s = session(proxy)
    if headers:
        s.headers.update(headers)
    for i in range(tries):
        try:
            r = s.get(url, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (i + 1)); continue
            if not r.text:
                return None
            return r.json()
        except (requests.RequestException, json.JSONDecodeError):
            time.sleep(1.0 * (i + 1))
    return None


def get_text(url: str, *, proxy: str | None = None, headers: dict | None = None,
             params: dict | None = None, tries: int = 3, timeout: int = 20) -> str | None:
    s = session(proxy)
    if headers:
        s.headers.update(headers)
    for i in range(tries):
        try:
            r = s.get(url, params=params, timeout=timeout, allow_redirects=True)
            if r.status_code >= 500:
                time.sleep(1.0 * (i + 1)); continue
            return r.text
        except requests.RequestException:
            time.sleep(1.0 * (i + 1))
    return None


def probe(url: str, *, proxy: str | None = None, timeout: int = 12):
    """Return (status, final_url, headers, body_snippet) or (None,...) on failure."""
    s = session(proxy)
    try:
        r = s.get(url, timeout=timeout, allow_redirects=True)
        return r.status_code, r.url, dict(r.headers), r.text[:200000]
    except requests.RequestException as e:
        return None, None, {"error": str(e)}, ""


BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Dest": "document",
    "sec-ch-ua": '"Chromium";v="126", "Not-A.Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# status codes that mean "the edge refused our client", not "the site said no"
BLOCK_STATUS = {401, 403, 406, 429, 451, 503}


def fetch(url: str, *, proxy: str | None = None, timeout: int = 12, tries: int = 2) -> dict:
    """Single-shot fetch that classifies edge blocks instead of returning silence.

    Returns {status, final_url, headers, body, blocked, error}. A tiny body with a
    403/429 means a WAF/Akamai/Cloudflare decision against the requesting IP — the
    caller must surface that, not report "no data".
    """
    last_err = None
    for attempt in range(tries):
        s = session(proxy)
        if attempt:
            s.headers.update(BROWSER_HEADERS)
        try:
            r = s.get(url, timeout=timeout, allow_redirects=True)
            body = r.text[:200000]
            blocked = r.status_code in BLOCK_STATUS and len(body) < 3000
            return {"status": r.status_code, "final_url": r.url,
                    "headers": dict(r.headers), "body": body,
                    "blocked": blocked, "error": None}
        except requests.RequestException as e:
            last_err = str(e)[:160]
    return {"status": None, "final_url": None, "headers": {}, "body": "",
            "blocked": False, "error": last_err or "unreachable"}
