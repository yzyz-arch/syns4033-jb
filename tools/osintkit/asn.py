"""ASN / netblock intelligence: IP -> ASN -> org -> announced prefixes -> neighbourhood.

bgpview.io is unreachable from most cloud egress, so the chain is:
  ip-api.com (geo+asn)  ->  hackertarget aslookup  ->  RIPE stat (prefixes, holder)
  ->  hackertarget reverseiplookup (co-hosted domains)
"""
from __future__ import annotations

import concurrent.futures as cf

from .http import get_json, get_text

_FIELDS = ("status,message,country,countryCode,region,regionName,city,zip,lat,lon,"
           "timezone,isp,org,as,asname,reverse,mobile,proxy,hosting,query")


def ip_api(ip: str) -> dict:
    d = get_json(f"http://ip-api.com/json/{ip}", params={"fields": _FIELDS}, tries=2, timeout=12)
    return d if isinstance(d, dict) else {"status": "fail", "query": ip}


def hackertarget_asn(ip: str) -> dict:
    txt = get_text(f"https://api.hackertarget.com/aslookup/?q={ip}", tries=2, timeout=15)
    if not txt or "error" in txt[:80].lower():
        return {}
    parts = [p.strip().strip('"') for p in txt.split(",")]
    if len(parts) >= 3:
        return {"ip": parts[0], "asn": parts[1], "prefix": parts[2]}
    return {"raw": txt.strip()[:200]}


def _asn_number(asn: str) -> str:
    return asn.upper().replace("AS", "").strip()


def announced_prefixes(asn: str, timeout: int = 25) -> dict:
    num = _asn_number(asn)
    d = get_json("https://stat.ripe.net/data/announced-prefixes/data.json",
                 params={"resource": f"AS{num}"}, tries=2, timeout=timeout)
    if not isinstance(d, dict):
        return {"asn": f"AS{num}", "prefixes": [], "error": "ripe-stat unreachable"}
    prefixes = [p.get("prefix") for p in (d.get("data") or {}).get("prefixes", []) or []]
    return {"asn": f"AS{num}", "prefixes": sorted(set(prefixes)), "count": len(set(prefixes))}


def asn_overview(asn: str) -> dict:
    num = _asn_number(asn)
    d = get_json("https://stat.ripe.net/data/prefix-overview/data.json",
                 params={"resource": f"AS{num}"}, tries=2, timeout=25)
    if not isinstance(d, dict):
        return {"asn": f"AS{num}", "error": "ripe-stat unreachable"}
    data = d.get("data") or {}
    asns = data.get("asns") or []
    holder = asns[0].get("holder") if asns else None
    return {"asn": f"AS{num}", "holder": holder,
            "announced": data.get("announced"),
            "block": data.get("block"), "resource": data.get("resource")}


def reverse_ip(ip: str) -> dict:
    txt = get_text(f"https://api.hackertarget.com/reverseiplookup/?q={ip}", tries=2, timeout=20)
    hosts: list[str] = []
    if txt and "error" not in txt[:80].lower() and "API count" not in txt:
        hosts = sorted({h.strip() for h in txt.splitlines() if h.strip()})
    return {"ip": ip, "domains": hosts[:300], "count": len(hosts)}


def enrich(ip: str, prefixes: bool = True, rev: bool = False) -> dict:
    """Full ASN dossier for one IP."""
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        f_geo = ex.submit(ip_api, ip)
        f_ht = ex.submit(hackertarget_asn, ip)
        out = {"ip": ip, "geo": f_geo.result(), "asn_raw": f_ht.result()}
    asn = (out["asn_raw"] or {}).get("asn")
    if prefixes and asn:
        with cf.ThreadPoolExecutor(max_workers=2) as ex:
            f_p = ex.submit(announced_prefixes, asn)
            f_o = ex.submit(asn_overview, asn)
            out["prefixes"] = f_p.result()
            out["asn_holder"] = f_o.result()
    if rev:
        out["reverse_ip"] = reverse_ip(ip)
    return out


def netblocks(asn: str) -> dict:
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        f_p = ex.submit(announced_prefixes, asn)
        f_o = ex.submit(asn_overview, asn)
        return {"asn": asn, "overview": f_o.result(), "prefixes": f_p.result()}
