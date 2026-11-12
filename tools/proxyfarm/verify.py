#!/usr/bin/env python3
"""
verify.py — re-check a proxy pool RIGHT NOW and split by real capability.

farm.py marks a proxy residential from ASN metadata; that does NOT prove it still
works or that it hides your IP on the protocol you need. verify.py answers both:

  https_anon : HTTPS CONNECT works AND egress IP != ours   -> usable everywhere
  https_leak : HTTPS CONNECT works but egress IP == ours   -> useless for anonymity
  http_anon  : only plain HTTP works, egress IP != ours    -> http:// targets only
  http_leak  : only plain HTTP works, egress IP == ours    -> transparent, useless
  dead       : no response

usage:
  python3 verify.py                          # verifies out/residential.txt
  python3 verify.py -p out/residential.txt -o out/active -j 120 -t 12
  python3 verify.py --input out/proxies_iponly.txt   # bare ip:port list

outputs: <out>_https.txt (best pool), <out>_http.txt (fallback), <out>_stats.json
"""
import argparse, asyncio, json, re, time
from pathlib import Path

import aiohttp

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36")
ECHO = ("http://api.ipify.org?format=json", "http://icanhazip.com")
ECHO_HTTPS = ("https://api.ipify.org?format=json", "https://icanhazip.com")
IPRE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")


def parse_pool(path: Path):
    """accept 'exit@ip:port proto ...' (farm format) and bare 'ip:port'."""
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        first = line.split()[0]
        rest = line.split()[1:]
        if "@" in first:
            exit_ip, entry = first.split("@", 1)
        else:
            exit_ip, entry = None, first
        if ":" not in entry:
            continue
        proto = rest[0] if rest and rest[0] in ("http", "socks5") else "http"
        cc = rest[1] if len(rest) > 1 and len(rest[1]) == 2 else "??"
        isp = " ".join(rest[3:]) if proto == "http" and len(rest) > 3 else " ".join(rest[2:])
        out.append({"proxy": entry, "exit_ip": exit_ip, "proto": proto, "cc": cc, "isp": isp})
    return out


async def fetch(sess, proxy, url, timeout):
    async with sess.get(url, proxy=f"http://{proxy}", headers={"User-Agent": UA},
                        timeout=aiohttp.ClientTimeout(total=timeout), ssl=False) as r:
        body = (await r.text())[:200]
        m = IPRE.search(body)
        return r.status, (m.group(0) if m else None)


async def probe(sess, rec, own, timeout):
    t0 = time.perf_counter()
    res = {"proxy": rec["proxy"], "proto": rec["proto"], "cc": rec["cc"], "isp": rec["isp"],
           "verdict": "dead", "ms": None, "egress": None}
    # 1) HTTPS CONNECT path
    for url in ECHO_HTTPS:
        try:
            st, ip = await fetch(sess, rec["proxy"], url, timeout)
            if st == 200 and ip:
                res["ms"] = int((time.perf_counter() - t0) * 1000)
                res["egress"] = ip
                res["verdict"] = "https_anon" if ip != own else "https_leak"
                return res
        except Exception:
            continue
    # 2) plain HTTP path
    for url in ECHO:
        try:
            st, ip = await fetch(sess, rec["proxy"], url, timeout)
            if st == 200 and ip:
                res["ms"] = int((time.perf_counter() - t0) * 1000)
                res["egress"] = ip
                res["verdict"] = "http_anon" if ip != own else "http_leak"
                return res
        except Exception:
            continue
    return res


async def own_ip(sess):
    for u in ECHO_HTTPS + ECHO:
        try:
            async with sess.get(u, timeout=aiohttp.ClientTimeout(total=8)) as r:
                m = IPRE.search(await r.text())
                if m:
                    return m.group(0)
        except Exception:
            pass
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--pool", default="out/residential.txt")
    ap.add_argument("--input", help="bare ip:port list (overrides --pool)")
    ap.add_argument("-o", "--out", default="out/active")
    ap.add_argument("-j", "--jobs", type=int, default=120)
    ap.add_argument("-t", "--timeout", type=float, default=12.0)
    a = ap.parse_args()

    src = Path(a.input or a.pool)
    pool = parse_pool(src)
    if not pool:
        raise SystemExit(f"empty pool: {src}")

    conn = aiohttp.TCPConnector(limit=a.jobs, force_close=True)
    async with aiohttp.ClientSession(connector=conn) as sess:
        own = await own_ip(sess)
        print(f"[*] own ip={own} | checking {len(pool)} proxies from {src} | jobs={a.jobs} t={a.timeout}s", flush=True)
        sem = asyncio.Semaphore(a.jobs)

        async def guarded(r):
            async with sem:
                return await probe(sess, r, own, a.timeout)

        results = await asyncio.gather(*(guarded(r) for r in pool))

    order = {"https_anon": 0, "http_anon": 1, "https_leak": 2, "http_leak": 3, "dead": 4}
    results.sort(key=lambda x: (order[x["verdict"]], x["ms"] if x["ms"] else 9_999_999))

    best = [r for r in results if r["verdict"] == "https_anon"]
    http = [r for r in results if r["verdict"] == "http_anon"]
    leak = [r for r in results if r["verdict"].endswith("_leak")]
    dead = [r for r in results if r["verdict"] == "dead"]

    def line(r):
        return f"{r['proxy']} http {r['cc']} {r['ms']}ms {r['verdict']} egress={r['egress']} {r['isp']}"

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.parent / (out.name + "_https.txt")).write_text("\n".join(line(r) for r in best) + ("\n" if best else ""))
    (out.parent / (out.name + "_http.txt")).write_text("\n".join(line(r) for r in http) + ("\n" if http else ""))
    stats = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(src), "checked": len(results),
        "https_anon": len(best), "http_anon": len(http),
        "leak": len(leak), "dead": len(dead),
        "avg_ms": int(sum(r["ms"] for r in best) / len(best)) if best else None,
        "by_country_https": {c: sum(1 for r in best if r["cc"] == c) for c in sorted({r["cc"] for r in best})},
    }
    (out.parent / (out.name + "_stats.json")).write_text(json.dumps(stats, indent=1))

    print()
    for r in results:
        print(f"  {r['verdict']:<10} {r['proxy']:<24} {r['cc']}  {str(r['ms'] or '-'):>7}ms  {r['isp'][:40]}")
    print()
    print(json.dumps(stats, indent=1))
    print(f"[+] -> {out.parent}/{out.name}_https.txt ({len(best)}) | {out.name}_http.txt ({len(http)})")


if __name__ == "__main__":
    asyncio.run(main())
