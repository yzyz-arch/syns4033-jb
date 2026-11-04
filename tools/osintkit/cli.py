"""osintkit CLI — python -m osintkit <command> [args]"""
from __future__ import annotations

import argparse
import json
import sys

from . import (__version__, archives, asn, cloud, ct, dns_recon, domain, dorks,
               emails, favicon, gitintel, hostintel, identity, ip_intel, jsintel,
               livegeo, net, phone_nik, pipeline, pivot, score as score_mod,
               takeover, report as report_mod)

WORDLIST = [
    "www", "mail", "api", "app", "admin", "dev", "staging", "test", "beta", "portal",
    "vpn", "cdn", "static", "assets", "img", "media", "blog", "shop", "store", "docs",
    "support", "help", "status", "git", "gitlab", "jenkins", "ci", "build", "docker",
    "registry", "k8s", "grafana", "prometheus", "kibana", "elastic", "db", "mysql",
    "postgres", "redis", "mongo", "cache", "queue", "smtp", "imap", "pop", "webmail",
    "autodiscover", "autoconfig", "mx", "ns1", "ns2", "proxy", "gateway", "internal",
    "intranet", "extranet", "remote", "rdp", "ssh", "ftp", "sftp", "backup", "old",
    "new", "demo", "sandbox", "preview", "qa", "uat", "prod", "prod-api", "stg",
    "auth", "sso", "login", "account", "accounts", "id", "oauth", "billing", "pay",
    "payments", "checkout", "cart", "order", "user", "users", "customer", "crm", "erp",
    "analytics", "metrics", "logs", "monitor", "health", "config", "secret", "secrets",
]


def emit(data, path: str | None = None):
    text = json.dumps(data, indent=2, default=str)
    if path:
        with open(path, "w") as fh:
            fh.write(text)
        print(json.dumps({"written": path, "bytes": len(text)}))
    else:
        print(text)


# --------------------------- handlers ---------------------------

def cmd_domain(a):
    d = domain.correlate(a.target)
    if a.dns:
        d["dns_records"] = dns_recon.records(a.target)
        d["security_posture"] = dns_recon.security_posture(a.target)
    if a.subdomains:
        d["ct"] = ct.enumerate_all(a.target)
        if a.brute:
            d["brute"] = dns_recon.brute_subdomains(
                a.target, WORDLIST if a.brute_full else WORDLIST[:40])
    if a.wayback:
        d["wayback"] = archives.wayback_urls(a.target, limit=a.wayback)
    if a.js:
        d["js"] = jsintel.analyze(a.target)
    emit(d, a.out)


def cmd_dns(a):
    emit({"records": dns_recon.records(a.target),
          "security_posture": dns_recon.security_posture(a.target),
          "doh": {"ns": net.ns(a.target), "mx": net.mx(a.target),
                  "soa": net.soa(a.target), "caa": net.caa(a.target),
                  "txt": net.txt(a.target)}}, a.out)


def cmd_subs(a):
    res = ct.enumerate_all(a.target, use_crtsh=a.crtsh)
    if a.brute:
        res["brute"] = dns_recon.brute_subdomains(
            a.target, WORDLIST if a.full else WORDLIST[:40])
        res["combined"] = sorted(set(res["combined"]) | set(res["brute"]))
        res["count"] = len(res["combined"])
    res["resolved"] = net.bulk_resolve(res["combined"])
    emit(res, a.out)


def cmd_ct(a):
    emit(ct.san_pivot(a.target) if a.san else ct.enumerate_all(a.target, use_crtsh=a.crtsh), a.out)


def cmd_axfr(a):
    emit(dns_recon.zone_transfer(a.target), a.out)


def cmd_ip(a):
    emit(ip_intel.intel(a.target, ports=a.ports), a.out)


def cmd_host(a):
    emit(hostintel.host_report(a.target, deep=not a.no_scan), a.out)


def cmd_asn(a):
    target = a.target
    if target.lower().startswith("as") or target.isdigit():
        emit(asn.netblocks(target), a.out)
    else:
        emit(asn.enrich(target, prefixes=not a.no_prefixes, rev=a.rev), a.out)


def cmd_user(a):
    emit(identity.enumerate_username(a.target), a.out)


def cmd_email(a):
    out = {"syntax": identity.validate_email_syntax(a.target),
           "gravatar": identity.gravatar(a.target),
           "breach": identity.breach_lookup(a.target)}
    if a.accounts:
        out["accounts"] = identity.account_exists_signup(a.target)
    emit(out, a.out)


def cmd_harvest(a):
    res = emails.harvest(a.target, use_archive=not a.no_archive)
    if a.verify and res.get("emails"):
        res["verification"] = emails.verify_batch(res["emails"][: a.verify])
    if a.patterns and a.patterns.count(",") == 2:
        first, last, dom = [x.strip() for x in a.patterns.split(",")]
        res["generated_patterns"] = emails.generate_patterns(first, last, dom)
    emit(res, a.out)


def cmd_js(a):
    extra = a.extra or []
    emit(jsintel.analyze(a.target, extra_js=extra, limit=a.limit), a.out)


def cmd_sourcemap(a):
    emit(jsintel.fetch_sourcemap(a.target), a.out)


def cmd_archive(a):
    urls = archives.wayback_urls(a.target, limit=a.limit)
    out = {"wayback": {"count": len(urls), "urls": urls[:a.limit]},
           "interesting": archives.interesting_urls(urls),
           "params": archives.param_mining(urls),
           "urlscan": archives.urlscan_search(a.target, size=a.urlscan_size)}
    if not a.no_commoncrawl:
        out["commoncrawl"] = archives.commoncrawl(a.target, limit=min(a.limit, 500))
    emit(out, a.out)


def cmd_takeover(a):
    hosts = []
    if a.hosts_file:
        with open(a.hosts_file) as fh:
            hosts += [ln.strip() for ln in fh if ln.strip()]
    if a.from_subdomains:
        hosts += (ct.enumerate_all(a.target).get("combined") or [])
    if a.target:
        hosts.append(a.target)
    hosts = list(dict.fromkeys([h for h in hosts if h]))
    emit(takeover.scan(hosts) if len(hosts) > 1 else takeover.check_host(hosts[0]), a.out)


def cmd_cloud(a):
    provs = tuple(p.strip() for p in a.providers.split(",") if p.strip())
    emit(cloud.enumerate_all(a.target, providers=provs, limit=a.limit), a.out)


def cmd_dork(a):
    if a.generate:
        kind = a.generate
        gens = {"domain": dorks.domain_dorks, "org": dorks.org_dorks,
                "email": dorks.email_dorks, "person": dorks.person_dorks,
                "username": dorks.username_dorks}
        emit(gens[kind](a.target), a.out)
        return
    queries = a.queries or []
    if not queries:
        queries = dorks.domain_dorks(a.target)["google"][:5]
    emit(dorks.run_dorks(queries, limit_per_query=a.limit, engine=a.engine), a.out)


def cmd_gh(a):
    if a.scan_repo:
        owner, _, repo = a.scan_repo.partition("/")
        emit(gitintel.repo_secret_scan(owner, repo), a.out)
    else:
        emit(gitintel.footprint(a.target, deep=a.deep), a.out)


def cmd_scan(a):
    emit(gitintel.scan_local(a.target, limit_files=a.limit), a.out)


def cmd_score(a):
    with open(a.target) as fh:
        dossier = json.load(fh)
    emit(score_mod.score(dossier), a.out)


def cmd_graph(a):
    with open(a.target) as fh:
        dossier = json.load(fh)
    target = dossier.get("target") or dossier.get("summary", {}).get("target") or "target"
    g = pivot.build_graph(target, dossier)
    if a.outdir:
        emit(pivot.save(g, a.outdir, a.stem), a.out)
    else:
        emit(g, a.out)


def cmd_deep(a):
    log = (lambda m: print(m, file=sys.stderr)) if a.verbose else None
    dossier = pipeline.deep(
        a.target,
        brute=a.brute,
        wordlist=WORDLIST if a.brute else None,
        scan_hosts=not a.no_scan,
        include_dorks=a.dorks,
        include_cloud=not a.no_cloud,
        include_emails=not a.no_emails,
        include_js=not a.no_js,
        include_archive=not a.no_archive,
        max_takeover_hosts=a.takeover_hosts,
        max_ip_intel=a.ip_intel,
        log=log,
    )
    if a.outdir:
        res = report_mod.write_report(a.target, dossier, a.outdir, dossier.get("graph"))
        res["score"] = (dossier.get("score") or {}).get("score")
        res["grade"] = (dossier.get("score") or {}).get("grade")
        res["findings"] = len((dossier.get("score") or {}).get("findings") or [])
        emit(res, a.out)
    else:
        emit(dossier, a.out)


def cmd_favicon(a):
    emit(favicon.favicon(a.target), a.out)


def cmd_wildcard(a):
    emit(net.wildcard_probe(a.target), a.out)


# --------------------------- identity: NIK / phone ---------------------------

def cmd_nik(a):
    livegeo.require_authorization(a.i_have_authorization, "nik decode")
    emit(phone_nik.parse_nik(a.target, authorized=True), a.out)


def cmd_phone(a):
    livegeo.require_authorization(a.i_have_authorization, "phone decode")
    emit(phone_nik.normalize_phone(a.target), a.out)


def cmd_id(a):
    livegeo.require_authorization(a.i_have_authorization, "identity correlate")
    if not (a.nik or a.phone):
        raise SystemExit("id: pass --nik and/or --phone")
    emit(phone_nik.correlate(nik=a.nik, phone=a.phone, authorized=True), a.out)


# --------------------------- livegeo ---------------------------

def cmd_geo(a):
    db = a.db or livegeo.DEFAULT_DB
    if a.action == "selftest":
        emit(phone_nik.selftest(), a.out)
        return
    if a.action == "guardtest":
        checks = {}
        for host in ("127.0.0.1", "localhost", "::1"):
            checks[f"allow_{host}"] = livegeo.assert_loopback(host)
        for host in ("0.0.0.0", "8.8.8.8", "google.com", "192.168.1.10"):
            try:
                livegeo.assert_loopback(host)
                checks[f"deny_{host}"] = "FAILED — accepted"
            except livegeo.GuardrailViolation as e:
                checks[f"deny_{host}"] = f"blocked: {str(e)[:70]}"
        checks["missing_flag_refused"] = _flag_refused()
        emit(checks, a.out)
        return

    livegeo.require_authorization(a.i_have_authorization, f"geo {a.action}")
    store = livegeo.Store(db)
    try:
        if a.action == "register":
            emit(store.register(a.device, label=a.label, phone=a.phone, nik=a.nik), a.out)
        elif a.action == "devices":
            emit({"db": db, "devices": store.devices_for()}, a.out)
        elif a.action == "locate":
            emit(livegeo.locate(store, phone=a.phone, nik=a.nik, device_id=a.device,
                                ref_lat=a.ref_lat, ref_lon=a.ref_lon), a.out)
        elif a.action == "track":
            emit(livegeo.track_report(store, a.device, hours=a.hours), a.out)
        elif a.action == "simulate":
            emit(livegeo.simulate(store, a.device, points=a.points,
                                  lat=a.lat, lon=a.lon, step_m=a.step_m), a.out)
        elif a.action == "serve":
            livegeo.serve(store, a.host, a.port, authorized=True)
        else:
            raise SystemExit(f"unknown geo action {a.action!r}")
    finally:
        if a.action != "serve":
            store.close()


def _flag_refused() -> str:
    try:
        livegeo.require_authorization(False, "probe")
        return "FAILED — accepted without flag"
    except livegeo.GuardrailViolation as e:
        return f"blocked: {str(e)[:70]}"


# --------------------------- parser ---------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="osintkit",
        description="High-level OSINT toolkit — domain, CT, takeover, archives, JS secrets, cloud, ASN, graph.",
        epilog="examples:\n"
               "  osintkit deep example.com --outdir ./out --verbose\n"
               "  osintkit subs example.com --brute --full\n"
               "  osintkit takeover --target example.com --from-subdomains\n"
               "  osintkit js example.com --limit 60\n"
               "  osintkit dork --generate domain example.com\n"
               "  osintkit cloud example.com --providers s3,gcs\n"
               "  osintkit gh torvalds --deep\n"
               "  osintkit scan ./myrepo\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"osintkit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, help_, fn, target=True, metavar="TARGET"):
        p = sub.add_parser(name, help=help_)
        if target:
            p.add_argument("target", metavar=metavar)
        p.add_argument("--out", help="write JSON output to this file")
        p.set_defaults(func=fn)
        return p

    d = add("domain", "domain/web surface intel (whois, TLS, headers, tech, robots)", cmd_domain)
    d.add_argument("--dns", action="store_true")
    d.add_argument("--subdomains", action="store_true")
    d.add_argument("--brute", action="store_true")
    d.add_argument("--brute-full", action="store_true")
    d.add_argument("--wayback", type=int, metavar="N")
    d.add_argument("--js", action="store_true")

    add("dns", "DNS records + SPF/DMARC/DKIM/MTA-STS posture", cmd_dns)
    s = add("subs", "subdomain enumeration (5 CT sources + optional brute)", cmd_subs)
    s.add_argument("--brute", action="store_true")
    s.add_argument("--full", action="store_true")
    s.add_argument("--crtsh", action="store_true", help="also query crt.sh (slow)")

    c = add("ct", "certificate transparency only (+ SAN pivot)", cmd_ct)
    c.add_argument("--crtsh", action="store_true")
    c.add_argument("--san", action="store_true", help="only related domains from cert SANs")

    add("axfr", "attempt DNS zone transfer", cmd_axfr)
    i = add("ip", "IP intel: geo, ASN, rDNS, optional port scan", cmd_ip, metavar="IP")
    i.add_argument("--ports", action="store_true")

    h = add("host", "host intel: InternetDB + port scan + banners + TLS", cmd_host, metavar="IP")
    h.add_argument("--no-scan", action="store_true", help="InternetDB only, no TCP scan")

    n = add("asn", "ASN / netblocks / reverse-IP (accepts AS15169 or an IP)", cmd_asn, metavar="ASN|IP")
    n.add_argument("--rev", action="store_true", help="include reverse-IP neighbourhood")
    n.add_argument("--no-prefixes", action="store_true")

    add("user", "username enumeration across 30 platforms", cmd_user, metavar="USERNAME")
    e = add("email", "email intel: gravatar, breach signals, account probes", cmd_email, metavar="EMAIL")
    e.add_argument("--accounts", action="store_true")

    hv = add("harvest", "email harvesting from site + archive (+ optional SMTP verify)", cmd_harvest)
    hv.add_argument("--verify", type=int, metavar="N", help="SMTP-verify first N addresses")
    hv.add_argument("--no-archive", action="store_true")
    hv.add_argument("--patterns", metavar="FIRST,LAST,DOMAIN", help="generate address patterns")

    j = add("js", "JS bundle analysis: secrets, endpoints, sourcemaps", cmd_js)
    j.add_argument("--limit", type=int, default=40)
    j.add_argument("--extra", action="append", metavar="URL", help="extra JS URL (repeatable)")

    add("sourcemap", "parse a sourcemap URL for original source paths", cmd_sourcemap, metavar="URL")

    ar = add("archive", "wayback + commoncrawl + urlscan historical surface", cmd_archive)
    ar.add_argument("--limit", type=int, default=2000)
    ar.add_argument("--no-commoncrawl", action="store_true")
    ar.add_argument("--urlscan-size", type=int, default=50)

    t = add("takeover", "subdomain takeover scan (dangling CNAME + fingerprints)", cmd_takeover)
    t.add_argument("--hosts-file", metavar="FILE")
    t.add_argument("--from-subdomains", action="store_true")

    cl = add("cloud", "S3/GCS/Azure bucket enumeration", cmd_cloud)
    cl.add_argument("--providers", default="s3,gcs,azure")
    cl.add_argument("--limit", type=int, default=40)

    dk = add("dork", "generate or execute dorks (brave/bing/ddg, keyless)", cmd_dork)
    dk.add_argument("queries", nargs="*", help="raw queries to execute")
    dk.add_argument("--generate", choices=["domain", "org", "email", "person", "username"],
                    help="generate a dork set for TARGET as this type")
    dk.add_argument("--engine", default="auto", choices=["auto", "brave", "bing", "ddg"])
    dk.add_argument("--limit", type=int, default=10)

    g = add("gh", "GitHub footprint / repo secret scan", cmd_gh, metavar="LOGIN|OWNER/REPO")
    g.add_argument("--deep", action="store_true", help="include commit-author emails")
    g.add_argument("--scan-repo", metavar="OWNER/REPO")

    sc = add("scan", "offline secret scan of a local directory", cmd_scan, metavar="PATH")
    sc.add_argument("--limit", type=int, default=5000, help="max files to read")

    add("score", "score an existing dossier JSON", cmd_score, metavar="DOSSIER.json")
    gr = add("graph", "build/emit a pivot graph from a dossier JSON", cmd_graph, metavar="DOSSIER.json")
    gr.add_argument("--outdir")
    gr.add_argument("--stem", default="graph")

    dp = add("deep", "full pipeline: recon -> takeover -> archive -> JS -> cloud -> score", cmd_deep)
    dp.add_argument("--outdir", help="write json+md+html+graph files")
    dp.add_argument("--brute", action="store_true")
    dp.add_argument("--dorks", action="store_true", help="also execute search dorks")
    dp.add_argument("--no-scan", action="store_true")
    dp.add_argument("--no-cloud", action="store_true")
    dp.add_argument("--no-emails", action="store_true")
    dp.add_argument("--no-js", action="store_true")
    dp.add_argument("--no-archive", action="store_true")
    dp.add_argument("--takeover-hosts", type=int, default=80)
    dp.add_argument("--ip-intel", type=int, default=3)
    dp.add_argument("--verbose", action="store_true")

    add("favicon", "Shodan-compatible favicon hash (pure mmh3)", cmd_favicon)
    add("wildcard", "wildcard DNS detection for a domain", cmd_wildcard)

    # ---- identity: NIK / phone (offline, PII-gated) -----------------------
    nk = add("nik", "structural decode of a 16-digit NIK (no checksum exists)",
             cmd_nik, metavar="NIK")
    nk.add_argument("--i-have-authorization", action="store_true",
                    help="required: confirms the subject is under authorized scope")

    ph = add("phone", "normalize an Indonesian number: E.164, line type, operator prefix",
             cmd_phone, metavar="PHONE")
    ph.add_argument("--i-have-authorization", action="store_true")

    idd = add("id", "correlate NIK + phone into one capability matrix", cmd_id, target=False)
    idd.add_argument("--nik", metavar="NIK")
    idd.add_argument("--phone", metavar="PHONE")
    idd.add_argument("--i-have-authorization", action="store_true")

    # ---- livegeo: device-reported live location (loopback collector) -----
    ge = sub.add_parser(
        "geo", help="device-reported live location: register handset, ingest, locate")
    ge.add_argument("action", choices=["register", "devices", "locate", "track",
                                       "simulate", "serve", "selftest", "guardtest"])
    ge.add_argument("--device", metavar="ID")
    ge.add_argument("--phone", metavar="PHONE", help="join key: E.164 identity")
    ge.add_argument("--nik", metavar="NIK", help="join key: 16-digit NIK")
    ge.add_argument("--label", metavar="TEXT")
    ge.add_argument("--db", metavar="PATH", help="sqlite path (default .osintkit/livegeo.db)")
    ge.add_argument("--host", default="127.0.0.1", help="loopback only; non-loopback is refused")
    ge.add_argument("--port", type=int, default=8099)
    ge.add_argument("--hours", type=float, default=24.0)
    ge.add_argument("--ref-lat", type=float, metavar="LAT", help="reference point for distance/bearing")
    ge.add_argument("--ref-lon", type=float, metavar="LON")
    ge.add_argument("--points", type=int, default=6, help="simulate: number of fixes")
    ge.add_argument("--lat", type=float, default=-6.2088, help="simulate: start latitude")
    ge.add_argument("--lon", type=float, default=106.8456, help="simulate: start longitude")
    ge.add_argument("--step-m", type=float, default=120.0, help="simulate: metres per fix")
    ge.add_argument("--out", help="write JSON output to this file")
    ge.add_argument("--i-have-authorization", action="store_true")
    ge.set_defaults(func=cmd_geo)

    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
