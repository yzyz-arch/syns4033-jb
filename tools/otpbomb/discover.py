"""Endpoint discovery — crawl a brand's web app for real OTP-trigger URLs.

Providers drift and hand-written guesses 404. This walks the login/register
surface, harvests script bundles, and greps for otp/verification endpoints so
you can fold working URLs back into providers.py (or a --providers-file).

    python3 -m otpbomb.discover shopee.co.id tokopedia.com --out found.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from urllib.parse import urljoin, urlparse

import httpx

UA = ("Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")

PAGES = ("/", "/login", "/masuk", "/register", "/daftar", "/signup", "/signin",
         "/auth/login", "/user/login", "/account/login")
CANDIDATE = (
    "/api/v1/otp/send", "/api/v2/otp/send", "/api/otp/send", "/api/otp",
    "/api/v1/auth/otp", "/api/v1/user/otp", "/api/v2/authentication/send_otp",
    "/api/v1/authentication/send_otp", "/api/send-otp", "/api/v1/send-otp",
    "/otp/send", "/otp/request", "/api/v1/otp", "/api/otp/request",
)
HIT = re.compile(r"""["'`(](https?://[^"'`) ]{8,200}|/[a-z0-9._\-/]{3,120})["'`)]""", re.I)
KEY = re.compile(r"otp|verif|send.?code|send.?sms|send.?wa|whatsapp", re.I)
SCRIPT = re.compile(r"""<script[^>]+src=["']([^"']+)["']""", re.I)


def _keep(u: str) -> bool:
    if not KEY.search(u):
        return False
    if any(x in u for x in (".png", ".jpg", ".svg", ".css", ".woff", ".ico", ".gif")):
        return False
    return True


def _registrable(domain: str) -> str:
    """Crude eTLD+1 — enough for the ccTLD set this tool is used on."""
    parts = domain.lower().strip(".").split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    if len(parts[-1]) == 2 and len(parts[-2]) <= 3:  # co.id, com.my, co.uk-ish
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _same_site(url: str, domain: str) -> bool:
    netloc = urlparse(url).netloc.lower().split(":")[0]
    apex = _registrable(domain)
    return netloc == apex or netloc.endswith("." + apex)


async def _get(client: httpx.AsyncClient, url: str) -> str:
    try:
        r = await client.get(url, follow_redirects=True, timeout=8.0)
        if r.status_code < 400 and "text" in r.headers.get("content-type", ""):
            return r.text
    except Exception:  # HTTPError, InvalidURL, too many redirects, TLS
        return ""
    return ""


async def crawl(client: httpx.AsyncClient, domain: str) -> dict:
    from .probe_paths import probe  # local import to avoid cycles

    base = f"https://{domain}"
    found_site: set[str] = set()
    bodies = await asyncio.gather(*(_get(client, base + p) for p in PAGES))
    html = "\n".join(bodies)

    for m in HIT.finditer(html):
        u = urljoin(base, m.group(1))
        if _keep(u) and _same_site(u, domain):
            found_site.add(u)

    scripts = [urljoin(base, s) for s in SCRIPT.findall(html)][:14]
    js_bodies = await asyncio.gather(*(_get(client, s) for s in scripts))
    for body in js_bodies:
        for m in HIT.finditer(body):
            u = urljoin(base, m.group(1))
            if _keep(u):
                found_site.add(u)

    hits = await probe(client, base, CANDIDATE)
    return {
        "domain": domain,
        "from_site": sorted(found_site)[:40],
        "path_probe": hits,
    }


async def main_async(domains: list[str], out: str, conc: int) -> int:
    sem = asyncio.Semaphore(conc)
    results = []

    async with httpx.AsyncClient(headers={"user-agent": UA, "accept": "*/*"},
                                 follow_redirects=True, timeout=20.0) as client:
        async def one(d):
            async with sem:
                try:
                    res = await crawl(client, d)
                except Exception as exc:  # one dead domain must not sink the batch
                    res = {"domain": d, "from_site": [], "path_probe": [],
                           "error": f"{type(exc).__name__}: {exc}"}
                print(f"== {d}: {len(res['from_site'])} url / "
                      f"{sum(1 for h in res['path_probe'] if h['alive'])} path hidup"
                      + (f"  [{res['error']}]" if res.get("error") else ""))
                for h in res["path_probe"]:
                    if h["alive"]:
                        print(f"   [{h['status']}] {h['path']}")
                for u in res["from_site"][:8]:
                    print(f"   . {u}")
                results.append(res)

        await asyncio.gather(*(one(d) for d in domains))

    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"\n[+] {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="otpbomb.discover")
    p.add_argument("domains", nargs="+")
    p.add_argument("--out", default="discovered.json")
    p.add_argument("--concurrency", type=int, default=6)
    args = p.parse_args(argv)
    return asyncio.run(main_async(args.domains, args.out, args.concurrency))


if __name__ == "__main__":
    sys.exit(main())
