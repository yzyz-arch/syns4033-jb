"""Favicon fingerprinting with a pure-python murmur3_32 (Shodan-compatible).

Shodan's `http.favicon.hash` is mmh3.hash(base64.encodebytes(favicon_bytes)).
Implementing murmur3 here means the toolkit produces hashes you can paste
straight into Shodan/Censys/ZoomEye without installing mmh3.
"""
from __future__ import annotations

import base64
import re

from .http import session


def murmur3_32(data: bytes, seed: int = 0) -> int:
    """MurmurHash3 x86_32. Returns a signed 32-bit int, matching mmh3.hash()."""
    c1, c2 = 0xCC9E2D51, 0x1B873593
    length = len(data)
    h = seed & 0xFFFFFFFF
    nblocks = length // 4

    for i in range(nblocks):
        k = int.from_bytes(data[i * 4:i * 4 + 4], "little")
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF

    tail = data[nblocks * 4:]
    k = 0
    if len(tail) >= 3:
        k ^= tail[2] << 16
    if len(tail) >= 2:
        k ^= tail[1] << 8
    if len(tail) >= 1:
        k ^= tail[0]
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k

    h ^= length
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h - 0x100000000 if h & 0x80000000 else h


def shodan_hash(raw: bytes) -> int:
    """Shodan-compatible favicon hash."""
    return murmur3_32(base64.encodebytes(raw))


def _candidate_icon_urls(host: str, body: str | None) -> list[str]:
    urls = []
    if body:
        for m in re.finditer(
                r'<link[^>]+rel=["\']?[^"\'>]*icon[^"\'>]*["\']?[^>]*>', body, re.I):
            tag = m.group(0)
            hm = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
            if hm:
                href = hm.group(1)
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = f"https://{host}{href}"
                elif not href.startswith("http"):
                    href = f"https://{host}/{href.lstrip('./')}"
                urls.append(href)
    urls += [f"https://{host}/favicon.ico", f"http://{host}/favicon.ico"]
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def favicon(host: str, body: str | None = None) -> dict:
    s = session()
    for url in _candidate_icon_urls(host, body):
        try:
            r = s.get(url, timeout=10, allow_redirects=True)
        except Exception:
            continue
        if r.status_code == 200 and r.content and len(r.content) > 40:
            h = shodan_hash(r.content)
            return {
                "url": url,
                "shodan_hash": h,
                "shodan_dork": f'http.favicon.hash:{h}',
                "mmh3_hex": hex(h & 0xFFFFFFFF),
                "size": len(r.content),
                "content_type": r.headers.get("Content-Type"),
            }
    return {"url": None, "shodan_hash": None, "error": "no favicon found"}


def favicon_from_bytes(raw: bytes) -> dict:
    h = shodan_hash(raw)
    return {"shodan_hash": h, "shodan_dork": f"http.favicon.hash:{h}", "size": len(raw)}
