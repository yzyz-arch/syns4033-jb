"""Deep pipeline: run the whole kill-chain of collection in dependency order.

Stages are grouped so slow external calls overlap, and every stage degrades
independently — a blocked source returns an error field instead of killing the run.
"""
from __future__ import annotations

import concurrent.futures as cf
import time

from . import (archives, asn, cloud, ct, dns_recon, domain, dorks, emails,
               hostintel, jsintel, net, pivot, score, takeover)


def _safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:  # never let one stage kill the dossier
        return {"error": f"{type(e).__name__}: {str(e)[:160]}"}


def deep(host: str, *, brute: bool = False, wordlist: list[str] | None = None,
         scan_hosts: bool = True, include_dorks: bool = False,
         include_cloud: bool = True, include_emails: bool = True,
         include_js: bool = True, include_archive: bool = True,
         max_takeover_hosts: int = 80, max_ip_intel: int = 3,
         log=None) -> dict:
    t0 = time.time()

    def note(msg):
        if log:
            log(f"[{time.time() - t0:6.1f}s] {msg}")

    dossier: dict = {"target": host, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    # ---- stage 1: parallel independent collectors -------------------------
    note("stage 1: web surface, dns, ct, archive seeds")
    with cf.ThreadPoolExecutor(max_workers=7) as ex:
        f_web = ex.submit(_safe, domain.correlate, host)
        f_dns = ex.submit(_safe, dns_recon.records, host)
        f_post = ex.submit(_safe, dns_recon.security_posture, host)
        f_ct = ex.submit(_safe, ct.enumerate_all, host)
        f_js = ex.submit(_safe, jsintel.analyze, host) if include_js else None
        f_em = ex.submit(_safe, emails.harvest, host) if include_emails else None
        f_cl = ex.submit(_safe, cloud.enumerate_all, host) if include_cloud else None

        web = f_web.result(); dossier.update(web if isinstance(web, dict) else {})
        dossier["dns_records"] = f_dns.result()
        dossier["security_posture"] = f_post.result()
        dossier["ct"] = f_ct.result()
        if f_js:
            dossier["js"] = f_js.result()
        if f_em:
            dossier["emails"] = f_em.result()
        if f_cl:
            dossier["cloud"] = f_cl.result()

    ctres = dossier.get("ct") or {}
    subs = ctres.get("combined") or []
    if brute and wordlist:
        note(f"stage 1b: dns bruteforce ({len(wordlist)} labels)")
        brute_hosts = _safe(dns_recon.brute_subdomains, host, wordlist)
        if isinstance(brute_hosts, list):
            subs = sorted(set(subs) | set(brute_hosts))
            ctres["combined"] = subs
            ctres["count"] = len(subs)

    # ---- stage 2: resolve + takeover --------------------------------------
    note(f"stage 2: resolve {len(subs)} hosts + takeover scan")
    resolved = _safe(net.bulk_resolve, subs) if subs else {}
    dossier["resolved"] = resolved if isinstance(resolved, dict) else {}
    if scan_hosts and subs:
        candidates = list(dict.fromkeys([host] + subs))[:max_takeover_hosts]
        dossier["takeover"] = _safe(takeover.scan, candidates)

    # ---- stage 3: host intel on unique IPs --------------------------------
    ips = sorted({ip for ip in (dossier.get("resolved") or {}).values() if ip})
    apex = (dossier.get("http") or {}).get("final_url")
    if isinstance(apex, dict):
        apex = None
    web_ips = []
    for ip in ips[:max_ip_intel]:
        web_ips.append(ip)
    if web_ips:
        note(f"stage 3: host intel for {len(web_ips)} ip(s)")
        intel = {}
        with cf.ThreadPoolExecutor(max_workers=len(web_ips)) as ex:
            futs = {ip: ex.submit(_safe, hostintel.host_report, ip, True) for ip in web_ips}
            for ip, f in futs.items():
                intel[ip] = f.result()
        dossier["host_intel"] = intel
        vulns = []
        for ip, info in intel.items():
            for v in ((info or {}).get("internetdb") or {}).get("vulns", []) or []:
                vulns.append({"ip": ip, "cve": v})
        if vulns:
            dossier["vulns"] = vulns[:100]

    # ---- stage 4: archive + dorks ----------------------------------------
    if include_archive:
        note("stage 4: wayback / commoncrawl / urlscan")
        dossier["archive"] = _safe(archives.archive_dossier, host)
        wb_js = []
        try:
            wb_js = archives.wayback_js(host, limit=800)
        except Exception:
            pass
        if include_js and wb_js:
            note(f"stage 4b: archived JS analysis ({len(wb_js)} files)")
            dossier["js_archive"] = _safe(jsintel.analyze, host, wb_js, 25, True)

    if include_dorks:
        note("stage 4c: dork execution")
        q = dorks.domain_dorks(host)["google"][:8]
        dossier["dorks"] = _safe(dorks.run_dorks, q, 5)

    # ---- stage 5: ASN pivot ----------------------------------------------
    if ips:
        note("stage 5: asn pivot")
        dossier["asn"] = _safe(asn.enrich, ips[0], True, True)

    # ---- stage 6: scoring + graph ----------------------------------------
    note("stage 6: score + graph")
    dossier["score"] = score.score(dossier)
    dossier["graph"] = pivot.build_graph(host, dossier)
    dossier["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    dossier["elapsed_s"] = round(time.time() - t0, 1)
    note("done")
    return dossier


def quick(host: str) -> dict:
    """Fast pass: no port scan, no archive, no dorks."""
    return deep(host, scan_hosts=False, include_dorks=False, include_cloud=False,
                include_emails=False, include_js=True, include_archive=False,
                max_ip_intel=0)
