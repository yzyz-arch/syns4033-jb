#!/usr/bin/env python3
"""
filter_residential.py — keep only exit nodes that are actually residential.

`farm.py` labels a proxy "residential" from ip-api's bare `hosting` flag, which is
unreliable: CtrlS (AS18229), Timeweb (AS210976) and E2E Networks (AS132420) all come
back hosting=false while being pure datacenter. This filter cross-checks three signals
before an entry earns the residential label:

  1. ASN membership in a hosting/VPN ASN list (fetched, cached in state/bad_asn.json)
     plus a curated set of mega-provider / known-DC ASNs.
  2. Name heuristics (cloud|colo|hosting|server|vps|dedicated|gmbh|s.a.r.l|llp).
  3. Suspect netblocks where hosting and consumer space are mixed (45.194.0.0/16).

input : out/residential.json (metadata) + out/active_https.txt / out/active_http.txt
        (from verify.py — an entry must be verified working AND anon to qualify)
output: out/residential_only.txt / _iponly.txt / _json

usage:
  python3 filter_residential.py [--refresh-asn] [--min-latency 60000]
"""
import argparse, json, re, ssl, urllib.request
from pathlib import Path

BASE = Path(__file__).parent
OUT, STATE = BASE / "out", BASE / "state"
BAD_ASN = STATE / "bad_asn.json"
BAD_ASN_URLS = (
    "https://raw.githubusercontent.com/brianhama/bad-asn-list/master/bad-asn-list.csv",
    "https://raw.githubusercontent.com/brianhama/bad-asn-list/master/bad-asn-list-aggregated.csv",
)

# hosting / cloud / datacenter ASN — big providers plus the ones proven DC in this pool
CURATED_DC = {
    16509, 15169, 8075, 14061, 24940, 16276, 63949, 20473, 51167, 197540, 12876, 60781,
    9009, 212238, 174, 3352, 12912, 9123, 210976, 18229, 132420, 45102, 37963, 132203,
    45090, 135377, 55720, 133199, 131293, 206092, 199524, 42831, 395954, 396982, 19527,
    63018, 30633, 46844, 53667, 29802, 36352, 40021, 8100, 22612, 3223, 200373, 209854,
    9002, 30722, 62240, 51852, 203020, 199599,
}
NAME_HINT = re.compile(
    r"cloud|colo|datacenter|data ?center|hosting|server|vps|dedicated|\bllp\b|gmbh|s\.?a\.?r\.?l",
    re.I,
)
SUSPECT_NET = re.compile(r"^45\.194\.")  # mixed DC/anon space
ASN_RE = re.compile(r"AS(\d+)")


def fetch_bad_asn(refresh=False):
    if BAD_ASN.exists() and not refresh:
        return set(json.load(BAD_ASN.open()))
    found = set()
    for url in BAD_ASN_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            txt = urllib.request.urlopen(req, timeout=25,
                                         context=ssl.create_default_context()).read().decode("utf-8", "ignore")
        except Exception:
            continue
        for line in txt.splitlines():
            m = re.match(r"\s*(?:AS)?(\d{1,10})[,\t]", line, re.I)
            if m:
                found.add(int(m.group(1)))
        break
    if found:
        BAD_ASN.write_text(json.dumps(sorted(found)))
    return found


def load_verified():
    rows = []
    for name, verdict in (("active_https.txt", "https_anon"), ("active_http.txt", "http_anon")):
        f = OUT / name
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            p = line.split()
            if len(p) >= 4:
                rows.append({"proxy": p[0], "verdict": verdict, "cc": p[2],
                             "ms": int(p[3].rstrip("ms")), "isp": " ".join(p[6:])})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-asn", action="store_true")
    ap.add_argument("--min-latency", type=int, default=60000, help="ms ceiling")
    a = ap.parse_args()

    dc_as = fetch_bad_asn(a.refresh_asn) | CURATED_DC
    meta = {x["proxy"]: x for x in json.load((OUT / "residential.json").open())}
    rows = load_verified()

    keep, drop = [], []
    for r in rows:
        pr = r["proxy"]
        m = meta.get(pr)
        if not m:
            drop.append((pr, "no-metadata", "")); continue
        m = dict(m); m.update(verdict=r["verdict"], cc=r["cc"], ms=r["ms"])
        if r["ms"] > a.min_latency:
            drop.append((pr, f"latency >{a.min_latency}ms", m.get("isp", ""))); continue
        n = ASN_RE.search(str(m.get("asn", "")))
        if n and int(n.group(1)) in dc_as:
            drop.append((pr, f"DC ASN {m['asn'].split()[0]}", m.get("isp", ""))); continue
        if SUSPECT_NET.match(pr.split(":")[0]):
            drop.append((pr, "net 45.194.0.0/16", m.get("isp", ""))); continue
        blob = " ".join(str(m.get(k, "")) for k in ("isp", "org", "asname"))
        h = NAME_HINT.search(blob)
        if h:
            drop.append((pr, f"name '{h.group(0)}'", m.get("isp", ""))); continue
        keep.append(m)

    keep.sort(key=lambda x: (0 if x["verdict"] == "https_anon" else 1, x["ms"]))
    (OUT / "residential_only.txt").write_text(
        "\n".join(f"{x['proxy']} http {x['cc']} {x['ms']}ms {x['verdict']} "
                  f"{x['asn'].split()[0]} | {x['isp']}" for x in keep) + ("\n" if keep else ""))
    (OUT / "residential_only_iponly.txt").write_text(
        "\n".join(x["proxy"] for x in keep) + ("\n" if keep else ""))
    (OUT / "residential_only.json").write_text(json.dumps(keep, indent=1))

    print(f"verified anon {len(rows)}  ->  RESIDENTIAL-only {len(keep)}  (dropped {len(drop)})")
    for x in keep:
        tag = "HTTPS" if x["verdict"] == "https_anon" else "http "
        print(f"  {tag}  {x['proxy']:<23} {x['cc']} {x['ms']:>6}ms  {x['asn'].split()[0]:<9} {x['isp'][:44]}")
    if drop:
        print("\n-- dropped --")
        for pr, why, isp in drop:
            print(f"  {pr:<23} {why:<30} {isp[:36]}")


if __name__ == "__main__":
    main()
