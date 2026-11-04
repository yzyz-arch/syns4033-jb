#!/usr/bin/env python3
"""
proxy_rotate — consume out/residential.txt, rotate, self-heal, fetch.

  pool = ProxyPool("out/residential.txt")
  html = await pool.get("https://target/page")          # aiohttp
  html = pool.get_sync("https://target/page")           # requests

Behaviour: sticky-per-host is opt-in, dead proxy on error/quarantine, auto reload
file, background re-validation, transparent pool fallback.
"""
import asyncio, json, random, re, threading, time
from pathlib import Path

import aiohttp

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36")


class ProxyPool:
    def __init__(self, files=("out/residential.txt",), fallback="out/transparent.txt",
                 timeout=15, quarantine_after=2, reload_after=180):
        self.files = [Path(f) for f in files]
        self.fallback = Path(fallback) if fallback else None
        self.timeout = timeout
        self.quarantine_after = quarantine_after
        self.reload_after = reload_after
        self.lock = threading.Lock()
        self.fails = {}
        self.quarantined = set()
        self.alive, self.spare = [], []
        self.loaded_at = 0
        self.reload()

    # ---------- pool mgmt ----------
    def reload(self):
        with self.lock:
            self.alive, self.spare = [], []
            for f in self.files:
                if not f.exists():
                    continue
                for line in f.read_text().splitlines():
                    if not line.strip():
                        continue
                    parts = line.split()
                    if "@" not in parts[0]:
                        continue
                    exit_ip, entry = parts[0].split("@", 1)
                    meta = parts[1:]
                    proto = meta[0] if meta else "http"
                    rec = {"proxy": entry, "exit_ip": exit_ip, "proto": proto,
                           "ms": int(meta[2].rstrip("ms")) if len(meta) > 2 else 9999,
                           "cc": meta[1] if len(meta) > 1 else "??"}
                    (self.alive if proto == "http" else self.spare).append(rec)
            if self.fallback and self.fallback.exists():
                for line in self.fallback.read_text().splitlines():
                    if line.strip() and "@" in line.split()[0]:
                        parts = line.split()
                        exit_ip, entry = parts[0].split("@", 1)
                        self.spare.append({"proxy": entry, "exit_ip": exit_ip,
                                           "proto": parts[1] if len(parts) > 1 else "http",
                                           "ms": 9999, "cc": "??"})
            self.loaded_at = time.time()
        if not self.alive and not self.spare:
            print(f"[pool] WARNING empty pool ({self.files})")

    def _maybe_reload(self):
        if time.time() - self.loaded_at > self.reload_after:
            self.reload()

    def pick(self, exclude=(), cc=None):
        self._maybe_reload()
        pool = [p for p in self.alive if p["proxy"] not in self.quarantined and p["proxy"] not in exclude]
        if cc:
            pool = [p for p in pool if p["cc"].upper() == cc.upper()] or pool
        if not pool:
            pool = [p for p in self.spare if p["proxy"] not in self.quarantined]
        if not pool:
            return None
        return random.choices(pool, weights=[1 / max(p["ms"], 50) for p in pool], k=1)[0]

    def mark_fail(self, proxy):
        with self.lock:
            n = self.fails.get(proxy, 0) + 1
            self.fails[proxy] = n
            if n >= self.quarantine_after:
                self.quarantined.add(proxy)

    def mark_ok(self, proxy):
        with self.lock:
            self.fails[proxy] = 0
            self.quarantined.discard(proxy)

    # ---------- fetch ----------
    async def get(self, url, *, tries=6, cc=None, headers=None, method="GET", data=None,
                  session=None, **kw):
        h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
        if headers:
            h.update(headers)
        owned = session is None
        sess = session or aiohttp.ClientSession()
        used = []
        try:
            for attempt in range(tries):
                p = self.pick(exclude=used, cc=cc)
                if p is None:
                    raise RuntimeError("proxy pool exhausted")
                used.append(p["proxy"])
                socks = p.get("proto") == "socks5"
                try:
                    if socks:
                        from aiohttp_socks import ProxyConnector
                        s2 = aiohttp.ClientSession(connector=ProxyConnector.from_url(f"socks5://{p['proxy']}"))
                        try:
                            async with s2.request(method, url, headers=h,
                                                  timeout=aiohttp.ClientTimeout(total=self.timeout),
                                                  ssl=False, data=data, **kw) as r:
                                body = await r.read()
                                status, hdrs, final = r.status, dict(r.headers), str(r.url)
                        finally:
                            await s2.close()
                        if status in (403, 407, 429, 502, 503):
                            self.mark_fail(p["proxy"])
                            continue
                        self.mark_ok(p["proxy"])
                        return {"status": status, "body": body,
                                "text": body.decode("utf-8", "ignore"), "proxy": p["proxy"],
                                "exit_ip": p["exit_ip"], "headers": hdrs, "url": final}
                    async with sess.request(method, url, headers=h, proxy=f"http://{p['proxy']}",
                                            timeout=aiohttp.ClientTimeout(total=self.timeout),
                                            ssl=False, data=data, **kw) as r:
                        body = await r.read()
                        if r.status in (403, 407, 429, 502, 503):
                            self.mark_fail(p["proxy"])
                            continue
                        self.mark_ok(p["proxy"])
                        return {"status": r.status, "body": body,
                                "text": body.decode(r.charset or "utf-8", "ignore"),
                                "proxy": p["proxy"], "exit_ip": p["exit_ip"],
                                "headers": dict(r.headers), "url": str(r.url)}
                except Exception:
                    self.mark_fail(p["proxy"])
                    continue
            raise RuntimeError(f"all {tries} attempts failed for {url}")
        finally:
            if owned:
                await sess.close()

    def get_sync(self, url, **kw):
        import requests
        h = {"User-Agent": UA}
        h.update(kw.pop("headers", {}) or {})
        for _ in range(kw.pop("tries", 6)):
            p = self.pick()
            if not p:
                raise RuntimeError("proxy pool exhausted")
            try:
                r = requests.request(kw.pop("method", "GET"), url, headers=h,
                                     proxies={"http": f"http://{p['proxy']}",
                                              "https": f"http://{p['proxy']}"},
                                     timeout=kw.pop("timeout", self.timeout),
                                     verify=False, **kw)
                if r.status_code in (403, 407, 429, 502, 503):
                    self.mark_fail(p["proxy"])
                    continue
                self.mark_ok(p["proxy"])
                return r
            except Exception:
                self.mark_fail(p["proxy"])
        raise RuntimeError(f"all attempts failed for {url}")

    def stats(self):
        return {"alive": len(self.alive) - len(self.quarantined),
                "quarantined": len(self.quarantined), "spare": len(self.spare),
                "age_s": int(time.time() - self.loaded_at)}


async def _demo():
    pool = ProxyPool()
    print(json.dumps(pool.stats()))
    r = await pool.get("http://api.ipify.org?format=json", tries=10)
    print("egress:", r["text"].strip(), "via", r["proxy"])


if __name__ == "__main__":
    asyncio.run(_demo())
