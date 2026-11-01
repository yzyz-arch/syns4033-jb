---
name: osintkit
description: Full-stack OSINT recon with takeover and JS secrets.
version: 2.0.0
author: SYNS4033
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [osint, recon, subdomain, takeover, secrets, dorks, asn, cloud, redteam]
    category: security
    related_skills: [offensive-osint, osint-methodology, web2-recon, bb-methodology]
---

# osintkit Skill

Standalone Python CLI that runs an external-recon kill chain in one binary: certificate
transparency, dangling-CNAME takeover, archived attack surface, JS secret extraction,
cloud buckets, ASN pivoting, dork generation/execution, and a scored dossier with a
pivot graph. Output is JSON everywhere; `deep --outdir` also writes Markdown + a
single-file HTML report. No API keys are required for any default path.

It does not replace `amass`/`subfinder` for exhaustive brute force or `nuclei` for
exploitation — it is the fast first pass that says *what is exposed* and *what to hit*.

## When to Use

- Authorized external recon of a domain, IP, ASN, email, username, or GitHub org.
- You need subdomain takeover candidates, leaked keys in production bundles, or
  forgotten endpoints from Wayback/CommonCrawl/urlscan in one run.
- You want a scored, client-presentable dossier (`deep --outdir`) instead of raw JSON.

## Prerequisites

`requests` and `dnspython` (import name `dns`). `curl` binary on PATH (search engines
only accept its TLS fingerprint — see Pitfalls). Optional: `GITHUB_TOKEN`/`GH_TOKEN`
to lift the GitHub API limit from 60 req/h.

Path: `tools/osintkit/` (package), launcher `tools/osintkit.py`.

## How to Run

```bash
cd tools
python3 -m osintkit deep example.com --outdir ./out --verbose        # full pipeline
python3 -m osintkit subs example.com --brute --full                  # 5 CT sources + DNS brute
python3 -m osintkit takeover --target example.com --from-subdomains  # dangling CNAMEs
python3 -m osintkit js example.com --limit 60                        # secrets + endpoints
python3 -m osintkit archive example.com --limit 3000                 # wayback + CC + urlscan
python3 -m osintkit cloud example.com --providers s3,gcs,azure
python3 -m osintkit host 1.1.1.1                                     # InternetDB + port scan + TLS
python3 -m osintkit asn AS15169 --rev                                # netblocks + reverse-IP
python3 -m osintkit dork --generate domain example.com               # dork sets
python3 -m osintkit dork "site:example.com filetype:sql" --limit 10  # execute (brave/bing/ddg)
python3 -m osintkit gh torvalds --deep                               # profile + commit emails
python3 -m osintkit gh owner/repo --scan-repo                        # grep repo for secrets
python3 -m osintkit scan ./localrepo                                 # offline secret scan
python3 -m osintkit score out/osint_*.json                           # re-score a dossier
python3 -m osintkit graph out/osint_*.json --outdir ./out            # mermaid/dot/json
```

## Quick Reference

| Module | What it does | Key sources |
|---|---|---|
| `net` | DoH resolver, cache, bulk resolve, CNAME chains, wildcard probe | dns.google |
| `ct` | CT mining + SAN pivot to related domains | certspotter, subdomain.center, rapiddns, anubis, hackertarget, crt.sh |
| `takeover` | 50-provider dangling CNAME/body-signature detection | live probes |
| `archives` | Wayback CDX, CommonCrawl index, urlscan search + request dump | web.archive.org, index.commoncrawl.org, urlscan.io |
| `jsintel` | 30+ secret regexes, endpoint/third-party/sourcemap extraction | target JS bundles |
| `cloud` | S3/GCS/Azure/Spaces bucket classification | provider endpoints |
| `asn` | IP→ASN→holder→announced prefixes, reverse-IP neighbours | ip-api, hackertarget, RIPE stat |
| `hostintel` | InternetDB ports/vulns, TCP scan, banners, TLS, HTTP titles | internetdb.shodan.io |
| `dorks` | Dork sets per target class + keyless execution with relevance filter | brave, bing, ddg |
| `gitintel` | GitHub footprint, commit emails, repo secret grep, local scan | api.github.com |
| `score` | 0-100 exposure score, graded findings | local |
| `pivot` | entity graph → Mermaid / Graphviz / JSON | local |
| `report` | JSON + Markdown + single-file HTML dossier | local |

## Procedure

1. `deep <domain> --outdir out --verbose` — one pass, ~60-120s for a mid-size domain.
2. Read the score block first: `critical` findings are takeover hits, public buckets, and
   critical secrets. Verify each before reporting (the `note` field in `cloud` warns that a
   bucket hit proves the *name* is readable, not that the target owns it).
3. Pivot: `host <ip>` on exposed IPs, `js` on any interesting host, `archive` for params,
   `gh <org>` for leaked code, `asn <AS>` for the wider netblock.
4. Re-score after manual enrichment: `score out/osint_*.json`.
5. Hand off `out/*.html` (client-facing) and `*_graph.mmd` (diagram) — both are self-contained.

## Pitfalls

- **Large TXT RRsets truncate over UDP/53** — `dns_recon.records/security_posture` query DoH
  first for exactly this reason. A resolver-only SPF check produced false "no SPF" findings on
  domains with dozens of verification tokens. Never "simplify" it back to dnspython-first.
- **crt.sh is usually blocked/timeout from cloud egress** — it is the *last* source in `ct`;
  certspotter + subdomain.center + rapiddns carry the load. Do not "fix" it by raising
  timeouts; the pipeline already degrades.
- **bgpview.io is unreachable** — ASN data comes from ip-api + hackertarget + RIPE stat.
- **Brave/Bing reject Python's TLS fingerprint with 429** — `dorks._curl` shells out to the
  `curl` binary on purpose. Do not "simplify" it to `requests`.
- **Bing serves unrelated pages to suspected bots** — `dorks._relevant` requires every query
  anchor to appear in the result, so bad-engine output becomes `[]` instead of noise.
- **A generic HTTP 200 is not a bucket** — `check_gcs` requires `ListBucketResult` in the body.
- **SMTP verification usually returns `unverified`** — port 25 is filtered on most hosts. The
  result says so explicitly; never report it as "address does not exist".
- **whois/43 is blocked** — registration data comes from RDAP over HTTPS (`rdap.org`).
- **Username enumeration has false positives** on 200-for-missing sites; `REQUIRE_POSITIVE`
  in `identity` demands a positive marker for those. Treat `found` as a lead.
- **Rate limits**: ip-api 45/min, HudsonRock, GitHub 60/h unauthenticated, urlscan 100/h.
  The pipeline caps fan-out, but do not loop a target in a shell `while` loop.
- **Scope**: every command makes live outbound requests. Run it only against assets you are
  authorized to test.

## Verification

```bash
python3 tools/osintkit_selftest.py                 # offline: PASS 13/13
./venv/bin/python -m pytest tests/skills/test_osintkit_skill.py -q   # 31 passed
cd tools && python3 -m osintkit deep example.com --outdir /tmp/o   # live smoke
```

Live smoke is healthy when the returned JSON has `ct.count > 0`, `score.grade` set, and
`--outdir` produced `.json`/`.md`/`.html` plus `_graph.mmd`/`_graph.dot`.
