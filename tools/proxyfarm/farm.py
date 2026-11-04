#!/usr/bin/env python3
"""
residential proxy farm v2 — prioritized harvest -> resumable egress-check -> ASN classify -> rank.

  harvest : fresh feeds first (geonode metadata-filtered, openproxylist, proxyscrape), then public dumps
  check   : proxy must return an exit IP != our own (transparent proxies die here); resumable via state/
  classify: ip-api.com/batch -> asn/isp/org/hosting/mobile -> residential score, datacenter demoted
  output  : out/residential.json + out/residential.txt + out/stats.json

usage: python3 farm.py [-j 600] [-n 20000] [--min-score 3] [--harvest-only] [--no-resume]
"""
import argparse, asyncio, json, random, re, sys, time
from pathlib import Path

import aiohttp

BASE = Path(__file__).parent
OUT, STATE = BASE / "out", BASE / "state"
OUT.mkdir(exist_ok=True)
STATE.mkdir(exist_ok=True)
CAND, LIVE, DEAD = STATE / "candidates.tsv", STATE / "live.jsonl", STATE / "dead.txt"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
PAT = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b")


def ok_port(p):
    try:
        return 1 <= int(p) <= 65535
    except Exception:
        return False


# ---- feeds: (name, url, proto) ; proto in {http, socks5, mixed} ----
TEXT_FEEDS = [
    ("openproxylist-http", "https://api.openproxylist.xyz/http.txt", "http"),
    ("openproxylist-socks5", "https://api.openproxylist.xyz/socks5.txt", "socks5"),
    ("proxyscrape-http-5s", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&proxy_format=ipport&format=text&timeout=5000", "http"),
    ("proxyscrape-socks5", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks5&proxy_format=ipport&format=text", "socks5"),
    ("monosans-http", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt", "http"),
    ("monosans-socks5", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt", "socks5"),
    ("thespeedx-http", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", "http"),
    ("thespeedx-socks5", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt", "socks5"),
    ("roosterkid-https", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt", "http"),
    ("iplocate-http", "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt", "http"),
    ("clarketm", "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt", "http"),
    ("shifty-http", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt", "http"),
    ("vakhov-https", "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt", "http"),
    ("proxifly-all", "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt", "mixed"),
    ("hookzof-socks5", "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", "socks5"),
]

ECHO_HTTPS = ["https://api.ipify.org?format=json", "https://ifconfig.me/ip", "https://icanhazip.com"]
ECHO_HTTP = ["http://api.ipify.org?format=json", "http://ifconfig.me/ip", "http://icanhazip.com"]


def parse_echo(t):
    t = t.strip()
    if t.startswith("{"):
        try:
            d = json.loads(t)
            for k in ("ip", "query", "origin"):
                v = d.get(k)
                if isinstance(v, str):
                    m = re.search(r"(?:\d{1,3}\.){3}\d{1,3}", v)
                    if m:
                        return m.group(0)
        except Exception:
            pass
    m = re.search(r"(?:\d{1,3}\.){3}\d{1,3}", t)
    return m.group(0) if m else None


async def own_ip(sess):
    for u in ECHO_HTTPS:
        try:
            async with sess.get(u, timeout=aiohttp.ClientTimeout(total=8)) as r:
                m = re.search(r"(?:\d{1,3}\.){3}\d{1,3}", await r.text())
                if m:
                    return m.group(0)
        except Exception:
            continue
    return None


async def fetch_text(sess, url, timeout=25):
    async with sess.get(url, headers={"User-Agent": UA},
                        timeout=aiohttp.ClientTimeout(total=timeout)) as r:
        if r.status != 200:
            return None
        return await r.text(errors="ignore")


async def harvest(sess):
    """returns list of (proxy, proto, priority) — priority 0 = freshest/most likely alive"""
    seen, out, report = set(), [], {}

    def add(proxy, proto, prio):
        if proxy in seen:
            return False
        ip, _, port = proxy.partition(":")
        if not ok_port(port):
            return False
        seen.add(proxy)
        out.append((proxy, proto, prio))
        return True

    # tier 0: geonode fresh w/ uptime+latency metadata (best hit-rate by far)
    for page in range(1, 9):
        url = (f"https://proxylist.geonode.com/api/proxy-list?limit=500&page={page}"
               f"&sort_by=lastChecked&sort_type=desc&protocols=http,https,socks5")
        try:
            body = await fetch_text(sess, url)
            rows = json.loads(body)["data"]
        except Exception as e:
            report[f"geonode p{page}"] = f"err {type(e).__name__}"
            break
        n = 0
        for r in rows:
            try:
                lat = float(r.get("latency") or 9999)
                checked = int(r.get("lastChecked") or 0)
            except Exception:
                lat, checked = 9999, 0
            if lat > 3000 or (checked and time.time() - checked > 3600):
                continue
            proto = "socks5" if "socks5" in str(r.get("protocols")) else "http"
            n += add(f"{r['ip']}:{r['port']}", proto, 0)
        report[f"geonode p{page}"] = n

    # tier 1: fresh text feeds
    for name, url, proto in TEXT_FEEDS:
        try:
            body = await fetch_text(sess, url)
        except Exception as e:
            report[name] = f"err {type(e).__name__}"
            continue
        if not body:
            report[name] = "dead"
            continue
        n = 0
        for h in set(PAT.findall(body)):
            n += add(h, proto if proto != "mixed" else "http", 1)
        report[name] = n

    random.shuffle(out)  # de-bias dump ordering within a tier
    out.sort(key=lambda x: x[2])
    return out, report


async def probe(sess, proxy, real_ip, timeout):
    """plain-HTTP egress check (3-4x higher yield than CONNECT), then CONNECT probe.
    returns dict(exit_ip, transparent, tls_ok, ms) or None."""
    ip, _, port = proxy.partition(":")
    px = f"http://{ip}:{port}"
    t0 = time.perf_counter()
    try:
        async with sess.get(random.choice(ECHO_HTTP), proxy=px,
                            headers={"User-Agent": UA},
                            timeout=aiohttp.ClientTimeout(total=timeout),
                            ssl=False) as r:
            if r.status != 200:
                return None
            seen = parse_echo(await r.text(errors="ignore"))
    except Exception:
        return None
    if not seen:
        return None
    ms = int((time.perf_counter() - t0) * 1000)
    transparent = seen == real_ip
    tls_ok = False
    if not transparent:
        try:
            async with sess.get(random.choice(ECHO_HTTPS), proxy=px,
                                headers={"User-Agent": UA},
                                timeout=aiohttp.ClientTimeout(total=timeout + 3),
                                ssl=False) as r:
                tls_ok = r.status == 200
        except Exception:
            tls_ok = False
    return {"exit_ip": seen, "transparent": transparent, "tls_ok": tls_ok, "ms": ms}


async def probe_socks(proxy, real_ip, timeout):
    """same contract as probe(), via SOCKS5 connector (fresh session — connector is per-proxy)."""
    from aiohttp_socks import ProxyConnector
    t0 = time.perf_counter()
    try:
        conn = ProxyConnector.from_url(f"socks5://{proxy}")
        async with aiohttp.ClientSession(connector=conn) as s:
            try:
                async with s.get(random.choice(ECHO_HTTP), headers={"User-Agent": UA},
                                 timeout=aiohttp.ClientTimeout(total=timeout), ssl=False) as r:
                    if r.status != 200:
                        return None
                    seen = parse_echo(await r.text(errors="ignore"))
            except Exception:
                return None
            if not seen:
                return None
            ms = int((time.perf_counter() - t0) * 1000)
            transparent = seen == real_ip
            tls_ok = False
            if not transparent:
                try:
                    async with s.get(random.choice(ECHO_HTTPS), headers={"User-Agent": UA},
                                     timeout=aiohttp.ClientTimeout(total=timeout + 3), ssl=False) as r:
                        tls_ok = r.status == 200
                except Exception:
                    pass
    except Exception:
        return None
    return {"exit_ip": seen, "transparent": transparent, "tls_ok": tls_ok, "ms": ms}


async def run_pool(entries, real_ip, jobs, timeout, limit=None, resume=True):
    done = set()
    live = []
    if resume and DEAD.exists():
        done = set(l.split("|")[0] for l in DEAD.read_text().splitlines() if l)
    if resume and LIVE.exists():
        for l in LIVE.read_text().splitlines():
            try:
                d = json.loads(l)
                done.add(d["proxy"])
                live.append(d)
            except Exception:
                pass
    todo = [e for e in entries if e[0] not in done]
    if limit:
        todo = todo[:limit]
    print(f"[*] own ip={real_ip} | candidates={len(entries)} | todo={len(todo)} | live={len(live)}", flush=True)

    fdead, flive = DEAD.open("a"), LIVE.open("a")
    sem = asyncio.Semaphore(jobs)
    cnt = {"i": 0, "live": 0}
    conn = aiohttp.TCPConnector(limit=jobs, ttl_dns_cache=600, force_close=True)
    t0 = time.time()

    async def one(proxy, proto):
        async with sem:
            r = await (probe_socks(proxy, real_ip, timeout) if proto == "socks5"
                       else probe(sess, proxy, real_ip, timeout))
            cnt["i"] += 1
            if r:
                rec = {"proxy": proxy, "proto": proto, "exit_ip": r["exit_ip"],
                       "transparent": r["transparent"], "tls_ok": r["tls_ok"],
                       "ms": r["ms"]}
                flive.write(json.dumps(rec) + "\n")
                flive.flush()
                live.append(rec)
                if not r["transparent"]:
                    cnt["live"] += 1
            else:
                fdead.write(f"{proxy}|{proto}\n")
                fdead.flush()
            if cnt["i"] % 500 == 0:
                print(f"    {cnt['i']}/{len(todo)} anon_live={cnt['live']} "
                      f"anon_rate={cnt['live']/max(cnt['i'],1)*100:.1f}%", flush=True)

    async with aiohttp.ClientSession(connector=conn) as sess:
        await asyncio.gather(*(one(p, pr) for p, pr in todo))
    fdead.close()
    flive.close()
    return live


DC_HINT = re.compile(
    r"amazon|aws|google llc|microsoft|azure|digitalocean|linode|vultr|hetzner|ovh|contabo|"
    r"racknerd|oracle|alibaba|tencent|cloudflare|leaseweb|hostinger|choopa|m247|datacamp|"
    r"colocation|server|hosting|dedicated|data ?center|gmbh|s\.a\.r\.l",
    re.I,
)
RES_HINT = re.compile(
    r"telekom|telkom|indihome|telkomsel|indosat|xl axiata|smartfren|hutchison|"
    r"comcast|verizon|at&t|spectrum|charter|cox |centurylink|frontier|virgin media|"
    r"sky broadband|talktalk|orange|sfr|vodafone|telefonica|movistar|fastweb|"
    r"kddi|ntt|softbank|jcom|chinanet|china unicom|china mobile|pldt|globe telecom|"
    r"converge|viettel|vnpt|fpt telecom|true internet|3bb|tot |cat telecom|"
    r"singtel|starhub|maxis|celcom|digi |unifi|tm net|bharti|jio|bsnl|etisalat|stc |"
    r"zain|mobily|beeline|megafon|mts |rostelecom|mgts|telia|telenor|"
    r"broadband|cable|fiber|fttx|adsl|vdsl|residential|wifi|wireless|cellular|mobile|"
    r"lte|4g|5g|gpon|\bisp\b",
    re.I,
)


async def classify(sess, live):
    ips = sorted({x["exit_ip"] for x in live})
    meta = {}
    for i in range(0, len(ips), 100):
        chunk = ips[i:i + 100]
        try:
            async with sess.post(
                "http://ip-api.com/batch?fields=status,query,country,countryCode,regionName,city,isp,org,as,asname,hosting,mobile,proxy",
                json=[{"query": q} for q in chunk],
                timeout=aiohttp.ClientTimeout(total=25)) as r:
                for row in await r.json(content_type=None):
                    if row.get("status") == "success":
                        meta[row["query"]] = row
        except Exception as e:
            print(f"[!] ip-api fail: {type(e).__name__}", flush=True)
        await asyncio.sleep(4.3)

    out = []
    for it in live:
        m = meta.get(it["exit_ip"])
        if not m:
            continue
        blob = " ".join(str(m.get(k, "")) for k in ("isp", "org", "as", "asname"))
        s = 0
        s += 3 if not m.get("hosting") else 0
        s += 2 if m.get("mobile") else 0
        s += 3 if RES_HINT.search(blob) else 0
        s -= 2 if DC_HINT.search(blob) else 0
        s += 2 if it.get("tls_ok") else 0
        s -= 2 if it.get("transparent") else 0
        s += 1 if it["ms"] < 1500 else 0
        s += 1 if it["ms"] < 600 else 0
        it.update(score=s, asn=m.get("as", ""), asname=m.get("asname", ""), isp=m.get("isp", ""),
                  org=m.get("org", ""), cc=m.get("countryCode", ""), city=m.get("city", ""),
                  hosting=bool(m.get("hosting")), mobile=bool(m.get("mobile")))
        out.append(it)
    out.sort(key=lambda x: (-x["score"], x["ms"]))
    return out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", "--jobs", type=int, default=600)
    ap.add_argument("-n", "--batch", type=int, default=None, help="max candidates this run")
    ap.add_argument("-t", "--timeout", type=float, default=7.0)
    ap.add_argument("--min-score", type=int, default=3)
    ap.add_argument("--only", choices=["http", "socks5"])
    ap.add_argument("--harvest-only", action="store_true")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--reclassify", action="store_true", help="re-run classify on existing live.jsonl")
    ap.add_argument("--reverify", action="store_true", help="re-probe existing live.jsonl, refresh latency, drop dead")
    a = ap.parse_args()

    if a.no_resume:
        for p in (DEAD, LIVE, CAND):
            p.exists() and p.unlink()

    if a.reverify:
        old = [json.loads(l) for l in LIVE.read_text().splitlines() if l.strip()]
        async with aiohttp.ClientSession() as sess:
            real = await own_ip(sess)
        ent = [(o["proxy"], o["proto"]) for o in old]
        DEAD.unlink(missing_ok=True)
        LIVE.unlink(missing_ok=True)
        live = await run_pool(ent, real, a.jobs, a.timeout, None, False)
        async with aiohttp.ClientSession() as sess:
            live = await classify(sess, live)
    elif a.reclassify:
        live = [json.loads(l) for l in LIVE.read_text().splitlines() if l.strip()]
        async with aiohttp.ClientSession() as sess:
            live = await classify(sess, live)
    else:
        async with aiohttp.ClientSession() as sess:
            real = await own_ip(sess)
        if not real:
            sys.exit("no own ip")

        entries, report = [], {}
        if CAND.exists() and CAND.read_text().strip():
            for line in CAND.read_text().splitlines():
                p, pr = (line.split("\t") + ["http"])[:2]
                entries.append((p, pr))
            print(f"[*] reused {len(entries)} cached candidates (state/candidates.tsv)")
        else:
            async with aiohttp.ClientSession() as sess:
                entries, report = await harvest(sess)
            CAND.write_text("\n".join(f"{p}\t{pr}" for p, pr, _ in entries))
            print(f"[*] harvested {len(entries)} unique; report={json.dumps(report)}")
            for k, v in report.items():
                print(f"    {k:22s} {v}")
            entries = [(p, pr) for p, pr, _ in entries]  # priority already applied by sort

        if a.harvest_only:
            return
        if a.only:
            entries = [e for e in entries if e[1] == a.only]
        live = await run_pool(entries, real, a.jobs, a.timeout, a.batch, not a.no_resume)
        async with aiohttp.ClientSession() as sess:
            ranked = await classify(sess, live)
        live = ranked

    # dedupe: 1 entry per exit IP for anon; transparent keep per-proxy (they all share our IP)
    seen_ip, good, trans = set(), [], []
    for x in live:
        if "cc" not in x:
            continue
        if x.get("transparent"):
            trans.append(x)
            continue
        if x["exit_ip"] in seen_ip:
            continue
        seen_ip.add(x["exit_ip"])
        if x.get("score", 0) >= a.min_score:
            good.append(x)
    trans.sort(key=lambda x: x["ms"])
    trans = trans[:60]

    def fmt(x):
        return f"{x['exit_ip']}@{x['proxy']} {x['proto']} {x['cc']} {x['ms']}ms tls={int(bool(x.get('tls_ok')))} {x['isp']}"

    (OUT / "residential.json").write_text(json.dumps(good, indent=1))
    (OUT / "residential.txt").write_text("\n".join(fmt(x) for x in good))
    (OUT / "transparent.txt").write_text("\n".join(fmt(x) for x in trans))
    stats = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "alive": len(live), "residential": len(good), "transparent": len(trans),
        "by_country": {c: sum(1 for x in good if x["cc"] == c) for c in sorted({x["cc"] for x in good})},
        "avg_ms": int(sum(x["ms"] for x in good) / len(good)) if good else None,
        "mobile": sum(1 for x in good if x["mobile"]),
        "tls_capable": sum(1 for x in good if x.get("tls_ok")),
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))
    print(f"[+] -> {OUT}/residential.txt ({len(good)}) | {OUT}/transparent.txt ({len(trans)})")


if __name__ == "__main__":
    asyncio.run(main())
