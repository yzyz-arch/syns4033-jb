#!/usr/bin/env python3
"""
scrape.py — rotating-proxy scraper on top of proxy_rotate.ProxyPool.

usage:
  python3 scrape.py https://target/list --pages 20 --out data.jsonl [--cc US,ID] [-j 8] [--css a] [--attr href]

Output: JSONL, one record per page {url, page, status, proxy, exit_ip, len, links[], title, ts}.
Resume: existing --out is read, finished urls skipped.
"""
import argparse, asyncio, json, re, sys, time
from pathlib import Path

import aiohttp

from proxy_rotate import ProxyPool

TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def page_urls(base, n, pattern):
    tmpl = base if "{page}" in base else (pattern if pattern and "{page}" in pattern else None)
    if tmpl:
        return [tmpl.replace("{page}", str(i)) for i in range(1, n + 1)]
    return [base] * n


async def worker(pool, sess, q, out_fh, lock, ccs, extract_links):
    while True:
        try:
            url, idx = q.get_nowait()
        except asyncio.QueueEmpty:
            return
        cc = ccs[idx % len(ccs)] if ccs else None
        try:
            r = await pool.get(url, tries=6, cc=cc, session=sess)
        except Exception as e:
            rec = {"url": url, "page": idx, "error": f"{type(e).__name__}: {e}", "ts": int(time.time())}
        else:
            links = extract_links(r["text"], str(r["url"])) if extract_links else []
            t = TITLE.search(r["text"])
            rec = {"url": url, "page": idx, "status": r["status"], "proxy": r["proxy"],
                   "exit_ip": r["exit_ip"], "len": len(r["body"]),
                   "title": (t.group(1).strip()[:200] if t else ""),
                   "links": links[:200], "ts": int(time.time())}
        async with lock:
            out_fh.write(json.dumps(rec) + "\n")
            out_fh.flush()
        print(f"[{idx}] {rec.get('status', 'ERR')} {len(rec.get('links', []))} links  {url}", flush=True)


def make_link_extractor(css, attr):
    def ex(html, base):
        found = []
        if css:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for el in soup.select(css):
                    v = el.get(attr) if attr else el.get_text(strip=True)
                    if v:
                        found.append(v)
            except ImportError:
                pass
        else:
            found = re.findall(r'href=["\'](https?://[^"\']+)', html)
        return found
    return ex


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--pattern", default="{page}", help="url with {page} placeholder")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("-o", "--out", default="data.jsonl")
    ap.add_argument("-j", "--concurrency", type=int, default=8)
    ap.add_argument("--cc", default="", help="prefer exit countries, comma list (rotating)")
    ap.add_argument("--css")
    ap.add_argument("--attr")
    ap.add_argument("-pool", "--pool-file", default="out/residential.txt")
    ap.add_argument("--include-transparent", action="store_true")
    a = ap.parse_args()

    out = Path(a.out)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            try:
                done.add(json.loads(line)["url"])
            except Exception:
                pass
    urls = [u for u in page_urls(a.url, a.pages, a.pattern) if u not in done]
    if not urls:
        print("[=] nothing to do (all urls already in output)")
        return

    pool = ProxyPool(files=[a.pool_file],
                     fallback="out/transparent.txt" if a.include_transparent else None)
    print(f"[*] pool {pool.stats()} | urls={len(urls)} | jobs={a.concurrency}")

    sess_conn = aiohttp.TCPConnector(limit=a.concurrency * 2, force_close=True)
    q = asyncio.Queue()
    for i, u in enumerate(urls, 1):
        q.put_nowait((u, i))

    lock = asyncio.Lock()
    ex = make_link_extractor(a.css, a.attr)
    ccs = [c.strip() for c in a.cc.split(",") if c.strip()]
    with out.open("a") as fh:
        async with aiohttp.ClientSession(connector=sess_conn) as sess:
            awaits = [worker(pool, sess, q, fh, lock, ccs, ex) for _ in range(a.concurrency)]
            await asyncio.gather(*awaits)
    ok = sum(1 for _ in urls)
    print(f"[+] done {ok} urls -> {out} | pool {pool.stats()}")


if __name__ == "__main__":
    asyncio.run(main())
