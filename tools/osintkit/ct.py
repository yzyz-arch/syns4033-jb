"""Certificate-transparency mining with multi-source fallback and SAN pivoting.

Source order is chosen by what actually answers from cloud hosts:
  certspotter (JSON API, fast) -> subdomain.center -> anubis/jldc -> rapiddns HTML
  -> hackertarget hostsearch -> crt.sh (slow / often 502, last resort)
"""
from __future__ import annotations

import concurrent.futures as cf
import re

from . import net
from .http import get_json, get_text, session

_HOSTISH = re.compile(r"^[a-z0-9_]([a-z0-9_-]*[a-z0-9_])?(\.[a-z0-9_]([a-z0-9_-]*[a-z0-9_])?)+$")


def certspotter(domain: str) -> dict:
    data = get_json(
        "https://api.certspotter.com/v1/issuances",
        params=[("domain", domain), ("include_subdomains", "true"),
                ("expand", "dns_names"), ("expand", "issuer")],
        tries=2, timeout=25,
    )
    names: set[str] = set()
    related: set[str] = set()
    issuers: set[str] = set()
    if isinstance(data, list):
        for row in data:
            for n in row.get("dns_names") or []:
                n = str(n).strip().lower().lstrip("*.").rstrip(".")
                if not n or "@" in n:
                    continue
                if n == domain or n.endswith("." + domain):
                    names.add(n)
                else:
                    related.add(n)
            iss = row.get("issuer") or {}
            if isinstance(iss, dict) and iss.get("name"):
                issuers.add(iss["name"])
    return {"names": sorted(names), "related": sorted(related),
            "issuers": sorted(issuers), "certs": len(data) if isinstance(data, list) else 0}


def subdomain_center(domain: str) -> list[str]:
    data = get_json("https://api.subdomain.center/", params={"domain": domain}, tries=2, timeout=30)
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def anubis(domain: str) -> list[str]:
    data = get_json(f"https://jldc.me/anubis/subdomains/{domain}", tries=2, timeout=25)
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def rapiddns(domain: str) -> list[str]:
    html = get_text(f"https://rapiddns.io/subdomain/{domain}", params={"full": "1"},
                    tries=2, timeout=25)
    if not html:
        return []
    cand = set(re.findall(r"<td>([A-Za-z0-9_.*-]+\.%s)</td>" % re.escape(domain), html))
    return sorted(cand)


def hackertarget(domain: str) -> list[str]:
    txt = get_text(f"https://api.hackertarget.com/hostsearch/?q={domain}", tries=2, timeout=20)
    if not txt or "error" in txt[:80].lower() or "API count" in txt:
        return []
    return [line.split(",")[0] for line in txt.splitlines() if line.strip()]


def crtsh(domain: str) -> list[str]:
    """crt.sh is the classic source but frequently times out; last resort only."""
    out: set[str] = set()
    s = session()
    try:
        r = s.get("https://crt.sh/", params={"q": f"%.{domain}", "output": "json"},
                  timeout=45)
        if r.status_code == 200 and r.text.strip().startswith("["):
            for row in r.json():
                for nv in str(row.get("name_value", "")).splitlines():
                    out.add(nv.strip().lower())
    except Exception:
        pass
    return sorted(out)


def enumerate_all(domain: str, use_crtsh: bool = False, workers: int = 6) -> dict:
    """Fan out to every live source, merge, dedupe, detect wildcard + pivots."""
    sources: dict[str, list[str]] = {}
    related: set[str] = set()
    issuers: set[str] = set()

    jobs = {
        "certspotter": lambda: certspotter(domain),
        "subdomain_center": lambda: subdomain_center(domain),
        "anubis": lambda: anubis(domain),
        "rapiddns": lambda: rapiddns(domain),
        "hackertarget": lambda: hackertarget(domain),
    }
    if use_crtsh:
        jobs["crtsh"] = lambda: crtsh(domain)

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn): name for name, fn in jobs.items()}
        for f in cf.as_completed(futs):
            name = futs[f]
            try:
                res = f.result()
            except Exception:
                res = []
            if isinstance(res, dict):
                sources[name] = res.get("names", [])
                related.update(res.get("related", []))
                issuers.update(res.get("issuers", []))
            else:
                sources[name] = list(res or [])

    merged: set[str] = set()
    for v in sources.values():
        merged.update(v)
    clean = net.dedupe_hosts(list(merged), domain)
    wc = net.wildcard_probe(domain)
    return {
        "domain": domain,
        "combined": clean,
        "count": len(clean),
        "by_source": {k: len(v) for k, v in sources.items()},
        "sources": {k: sorted(set(v)) for k, v in sources.items()},
        "wildcard_dns": wc["wildcard"],
        "wildcard_ips": wc["ips"],
        "related_domains_from_san": sorted(related)[:200],
        "certificate_issuers": sorted(issuers),
    }


def san_pivot(domain: str) -> dict:
    """Domains that share a certificate with the target -> sibling/related assets."""
    cs = certspotter(domain)
    return {"domain": domain, "related_domains": cs["related"],
            "issuers": cs["issuers"], "cert_count": cs["certs"]}


def dns_resolve_set(hosts: list[str], workers: int = 60) -> dict:
    resolved = net.bulk_resolve(hosts, workers=workers)
    return {"total": len(hosts), "resolved": len(resolved),
            "alive": resolved}
