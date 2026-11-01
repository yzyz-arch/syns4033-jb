"""Exposure scoring: turns the dossier into a 0-100 risk score + findings list.

Score is "badness": 0 = clean, 100 = trivially owned. Every point is traceable
to a finding with a severity, so nothing in the number is invented.
"""
from __future__ import annotations

SEV_WEIGHT = {"critical": 12, "high": 7, "medium": 3, "low": 1}

RISKY_PORTS = {21: "FTP", 23: "Telnet", 135: "MSRPC", 139: "NetBIOS", 445: "SMB",
               1433: "MSSQL", 2375: "Docker API", 3306: "MySQL", 3389: "RDP",
               5432: "PostgreSQL", 5601: "Kibana", 5900: "VNC", 6379: "Redis",
               9200: "Elasticsearch", 11211: "Memcached", 27017: "MongoDB",
               10250: "Kubelet", 15672: "RabbitMQ mgmt"}


def findings_from(dossier: dict) -> list[dict]:
    f: list[dict] = []

    for v in (dossier.get("takeover") or {}).get("vulnerable") or []:
        f.append({"id": "takeover", "severity": "critical",
                  "title": f"Subdomain takeover: {v.get('host')}",
                  "detail": f"dangling {v.get('provider')} resource - {(v.get('evidence') or [''])[0]}",
                  "evidence": v.get("evidence")})

    js = dossier.get("js") or {}
    for s in js.get("findings") or []:
        if s.get("severity") in ("critical", "high"):
            f.append({"id": "secret", "severity": s["severity"],
                      "title": f"Secret in JS bundle: {s.get('type')}",
                      "detail": f"{s.get('masked')} @ {s.get('source')}",
                      "evidence": s.get("source")})

    cl = dossier.get("cloud") or {}
    for b in cl.get("public") or []:
        f.append({"id": "bucket-public", "severity": "critical",
                  "title": f"Public bucket listing: {b.get('provider')}:{b.get('bucket')}",
                  "detail": b.get("url"), "evidence": b.get("sample_keys")})

    post = dossier.get("security_posture")
    if isinstance(post, dict):
        spf = post.get("spf")
        dmarc = post.get("dmarc") or ""
        if not spf:
            f.append({"id": "email-spf", "severity": "high",
                      "title": "No SPF record", "detail": "domain can be spoofed in MAIL FROM"})
        if not dmarc:
            f.append({"id": "email-dmarc", "severity": "high",
                      "title": "No DMARC record", "detail": "no policy for unauthenticated mail"})
        elif "p=none" in dmarc.lower():
            f.append({"id": "email-dmarc-none", "severity": "medium",
                      "title": "DMARC p=none", "detail": dmarc[:200]})

    http = dossier.get("http")
    if isinstance(http, dict) and http.get("security_headers"):
        sh = http.get("security_headers") or {}
        missing = [k for k, v in sh.items() if not v]
        if missing:
            f.append({"id": "headers", "severity": "medium" if len(missing) >= 5 else "low",
                      "title": f"{len(missing)} security headers missing",
                      "detail": ", ".join(missing)})

    intel = dossier.get("host_intel") or {}
    risky = []
    for ip, info in (intel.items() if isinstance(intel, dict) else []):
        for p in (info or {}).get("open_ports") or []:
            if p in RISKY_PORTS:
                risky.append(f"{ip}:{p} ({RISKY_PORTS[p]})")
    if risky:
        f.append({"id": "risky-ports", "severity": "high",
                  "title": f"{len(risky)} risky service port(s) exposed",
                  "detail": ", ".join(risky[:20])})

    arch = dossier.get("archive") or {}
    interesting = arch.get("interesting") or {}
    for ext in (".env", ".git", ".sql", ".bak", ".log", ".pem", ".key", ".db"):
        if interesting.get(ext):
            f.append({"id": "archived-artifact", "severity": "medium",
                      "title": f"Archived {ext} files indexed",
                      "detail": ", ".join(interesting[ext][:3])})

    vt = dossier.get("vulns") or []
    for v in vt[:50]:
        f.append({"id": "cve", "severity": "high",
                  "title": f"Known CVE exposed: {v.get('cve') if isinstance(v, dict) else v}",
                  "detail": str(v)[:200]})
    return f


def score(dossier: dict) -> dict:
    findings = findings_from(dossier)
    per_sev: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    raw = 0
    for f in findings:
        s = f.get("severity", "low")
        per_sev[s] = per_sev.get(s, 0) + 1
        raw += SEV_WEIGHT.get(s, 1)
    total = min(100, raw)
    grade = ("A" if total < 10 else "B" if total < 25 else "C" if total < 45
             else "D" if total < 70 else "F")
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: sev_rank.get(f["severity"], 9))
    return {"score": total, "grade": grade, "raw_points": raw,
            "counts": per_sev, "findings": findings,
            "interpretation": {
                "A": "hardened, little external signal",
                "B": "minor hygiene gaps",
                "C": "meaningful exposure, worth targeted testing",
                "D": "significant exposure, multiple attack paths",
                "F": "trivially exploitable surface present",
            }[grade]}
