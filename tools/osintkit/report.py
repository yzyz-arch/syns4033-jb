"""Reporting: JSON + Markdown + single-file HTML dossier with embedded graph.

The HTML report is self-contained (no CDN needed for the data tables; Mermaid is
loaded from a CDN for graph rendering and degrades to the raw diagram text).
"""
from __future__ import annotations

import html as _html
import json
from datetime import datetime, timezone
from pathlib import Path

SEV_COLOR = {"critical": "#e5484d", "high": "#f76b15", "medium": "#f5a623", "low": "#9ca3af"}


def _grade_headers(sec: dict) -> dict:
    present = [k for k, v in sec.items() if v]
    missing = [k for k, v in sec.items() if not v]
    score = int(round(100 * len(present) / max(1, len(sec))))
    return {"present": present, "missing": missing, "score": score}


def summarize(target: str, data: dict) -> dict:
    out = {"target": target, "generated": datetime.now(timezone.utc).isoformat()}
    http = data.get("http") or {}
    if http.get("security_headers"):
        out["header_grade"] = _grade_headers(http["security_headers"])
    if http.get("technologies"):
        out["technologies"] = http["technologies"]
    subs = (data.get("subdomains") or {})
    if isinstance(subs, dict) and subs.get("combined"):
        out["subdomain_count"] = len(subs["combined"])
    elif isinstance(subs, list):
        out["subdomain_count"] = len(subs)
    ct = data.get("ct") or {}
    if ct.get("count"):
        out["ct_subdomain_count"] = ct["count"]
        out.setdefault("subdomain_count", ct["count"])
    sc = data.get("score") or {}
    if sc:
        out["risk_score"] = sc.get("score")
        out["risk_grade"] = sc.get("grade")
    return out


def render_mermaid_html(mermaid: str, title: str = "graph") -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{_html.escape(title)}</title>
<style>body{{background:#0b0e14;color:#c9d1d9;font-family:ui-monospace,Menlo,monospace;margin:0;padding:24px}}</style>
</head><body>
<h2 style="color:#58a6ff">{_html.escape(title)}</h2>
<pre class="mermaid">{_html.escape(mermaid)}</pre>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
</script>
</body></html>"""


def _kv_table(d: dict) -> str:
    rows = "".join(
        f"<tr><th>{_html.escape(str(k))}</th><td>{_html.escape(str(v)[:400])}</td></tr>"
        for k, v in (d or {}).items())
    return f"<table>{rows}</table>"


def _list(items, limit: int = 300) -> str:
    items = list(items or [])[:limit]
    if not items:
        return "<p class='muted'>none</p>"
    return "<ul>" + "".join(f"<li>{_html.escape(str(i))}</li>" for i in items) + "</ul>"


def _findings_html(findings: list[dict]) -> str:
    if not findings:
        return "<p class='muted'>no findings</p>"
    rows = []
    for f in findings:
        color = SEV_COLOR.get(f.get("severity", "low"), "#9ca3af")
        rows.append(
            f"<tr><td><span class='sev' style='background:{color}'>{_html.escape(f.get('severity',''))}</span></td>"
            f"<td><b>{_html.escape(str(f.get('title','')))}</b><br><span class='muted'>"
            f"{_html.escape(str(f.get('detail',''))[:300])}</span></td></tr>")
    return "<table class='findings'>" + "".join(rows) + "</table>"


def render_html(target: str, dossier: dict, summary: dict, graph_mermaid: str | None) -> str:
    score = dossier.get("score") or {}
    subs = (dossier.get("ct") or {}).get("combined") or \
           ((dossier.get("subdomains") or {}).get("combined") if isinstance(dossier.get("subdomains"), dict) else []) or []
    js = dossier.get("js") or {}
    to = dossier.get("takeover") or {}
    cl = dossier.get("cloud") or {}
    arch = dossier.get("archive") or {}
    em = dossier.get("emails") or {}

    grade = score.get("grade", "-")
    score_val = score.get("score", "-")
    color = SEV_COLOR.get("critical" if score_val != "-" and score_val >= 70 else
                         "high" if score_val != "-" and score_val >= 45 else
                         "medium" if score_val != "-" and score_val >= 25 else "low", "#9ca3af")

    section_style = """
    body{background:#0b0e14;color:#c9d1d9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,sans-serif;margin:0;padding:0}
    .wrap{max-width:1100px;margin:0 auto;padding:28px 20px 80px}
    h1{font-size:24px;margin:0 0 4px}
    h2{font-size:17px;margin:32px 0 10px;color:#58a6ff;border-bottom:1px solid #21262d;padding-bottom:6px}
    .muted{color:#8b949e;font-size:12px}
    table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}
    th,td{border:1px solid #21262d;padding:6px 8px;text-align:left;vertical-align:top}
    th{background:#11151c;width:220px;color:#8b949e;font-weight:600}
    .findings th{width:auto}
    ul{margin:6px 0;padding-left:20px;font-size:13px}
    li{margin:2px 0;word-break:break-all}
    .sev{color:#0b0e14;padding:1px 7px;border-radius:9px;font-size:11px;font-weight:700;text-transform:uppercase}
    .badge{display:inline-block;padding:10px 16px;border-radius:10px;background:#11151c;border:1px solid #21262d;margin-right:10px}
    .big{font-size:30px;font-weight:800;color:__SCORE_COLOR__}
    code{background:#11151c;padding:1px 5px;border-radius:4px;font-size:12px}
    pre{background:#11151c;border:1px solid #21262d;border-radius:10px;padding:12px;overflow:auto;font-size:12px}
    """.replace("__SCORE_COLOR__", color)

    def stat(label: str, value) -> str:
        return f"<div class='badge'><div class='muted'>{_html.escape(label)}</div><div style='font-size:20px;font-weight:700'>{_html.escape(str(value))}</div></div>"

    parts = [f"""<!doctype html><html><head><meta charset="utf-8">
<title>OSINT — {_html.escape(target)}</title><style>{section_style}</style></head><body><div class="wrap">
<h1>OSINT Dossier — {_html.escape(target)}</h1>
<div class="muted">generated {_html.escape(summary.get('generated',''))} · osintkit</div>
<h2>Risk</h2>
<div class='badge'><div class='muted'>exposure score</div><div class='big'>{_html.escape(str(score_val))}/100</div></div>
<div class='badge'><div class='muted'>grade</div><div class='big'>{_html.escape(str(grade))}</div></div>
<div class='badge'><div class='muted'>critical / high</div><div class='big'>{_html.escape(str((score.get('counts') or {}).get('critical',0)))} / {_html.escape(str((score.get('counts') or {}).get('high',0)))}</div></div>
<p class="muted">{_html.escape(str(score.get('interpretation','')))}</p>
""",
             "<h2>Findings</h2>", _findings_html(score.get("findings") or []),
             "<h2>Overview</h2>",
             stat("subdomains", len(subs)), stat("open buckets", len(cl.get("public") or [])),
             stat("takeover vulns", len(to.get("vulnerable") or [])),
             stat("js secrets (crit/high)", ((js.get("finding_counts") or {}).get("critical", 0) +
                                             (js.get("finding_counts") or {}).get("high", 0))),
             stat("emails", em.get("count", 0)),
             stat("archived urls", (arch.get("wayback") or {}).get("count", 0)),
             ]

    if dossier.get("http"):
        parts += ["<h2>HTTP surface</h2>", _kv_table({
            k: v for k, v in (dossier["http"] or {}).items()
            if k in ("status", "final_url", "server", "powered_by", "title")}),
            "<h3>Security headers</h3>",
            _kv_table(dossier["http"].get("security_headers") or {})]
    if dossier.get("tls"):
        tls = dossier["tls"]
        parts += ["<h2>TLS certificate</h2>", _kv_table({
            "subject": tls.get("subject"), "issuer": tls.get("issuer"),
            "not_before": tls.get("not_before"), "not_after": tls.get("not_after"),
            "tls_version": tls.get("tls_version")}),
            "<h3>SAN</h3>", _list(tls.get("san") or [])]
    if dossier.get("whois"):
        parts += ["<h2>Registration (RDAP)</h2>", _kv_table(dossier["whois"])]
    if subs:
        parts += ["<h2>Subdomains</h2>", _list(sorted(subs), 400)]
    if to.get("vulnerable"):
        parts += ["<h2>Subdomain takeover</h2>"]
        for v in to["vulnerable"]:
            parts.append(f"<p><span class='sev' style='background:{SEV_COLOR['critical']}'>vulnerable</span> "
                         f"<b>{_html.escape(str(v.get('host')))}</b> → {_html.escape(str(v.get('provider')))}<br>"
                         f"<span class='muted'>{_html.escape(str(v.get('evidence')))}</span></p>")
    if js.get("findings"):
        parts += ["<h2>JavaScript secrets</h2>", "<ul>"]
        for f in js["findings"][:80]:
            parts.append(f"<li><span class='sev' style='background:{SEV_COLOR.get(f.get('severity'),'#888')}'>"
                         f"{_html.escape(f.get('severity',''))}</span> <b>{_html.escape(f.get('type',''))}</b> "
                         f"<code>{_html.escape(str(f.get('masked','')))}</code> "
                         f"<span class='muted'>{_html.escape(str(f.get('source',''))[:120])}</span></li>")
        parts.append("</ul>")
    if js.get("endpoints"):
        parts += ["<h2>Discovered endpoints</h2>", _list(js["endpoints"], 200)]
    if cl.get("public") or cl.get("private"):
        parts += ["<h2>Cloud storage</h2>", "<ul>"]
        for b in (cl.get("public") or []) + (cl.get("private") or []):
            parts.append(f"<li><b>{_html.escape(b.get('status',''))}</b> {_html.escape(b.get('provider',''))}:"
                         f"{_html.escape(str(b.get('bucket','')))} — <code>{_html.escape(str(b.get('url','')))}</code></li>")
        parts.append("</ul>")
    if arch.get("interesting"):
        parts += ["<h2>Archived artifacts</h2>"]
        for ext, urls in (arch["interesting"] or {}).items():
            parts.append(f"<h3>{_html.escape(ext)}</h3>" + _list(urls, 12))
    if em.get("emails"):
        parts += ["<h2>Emails</h2>", _list(em["emails"], 200)]
    if dossier.get("security_posture"):
        sp = dossier["security_posture"]
        parts += ["<h2>Email authentication posture</h2>", _kv_table({
            "SPF": sp.get("spf"), "DMARC": sp.get("dmarc"),
            "MTA-STS": sp.get("mta_sts"), "BIMI": sp.get("bimi"),
            "DKIM selectors": [d.get("selector") for d in (sp.get("dkim_selectors") or [])]})]
    if dossier.get("host_intel"):
        parts += ["<h2>Host intel</h2>"]
        for ip, info in dossier["host_intel"].items():
            parts.append(f"<h3>{_html.escape(ip)}</h3>" + _kv_table({
                "open ports": info.get("open_ports"),
                "high risk": info.get("high_risk"),
                "internetdb vulns": (info.get("internetdb") or {}).get("vulns"),
                "hostnames": (info.get("internetdb") or {}).get("hostnames"),
                "cpes": (info.get("internetdb") or {}).get("cpes")}))
    if graph_mermaid:
        parts += ["<h2>Pivot graph</h2>",
                  f"<pre class='mermaid'>{_html.escape(graph_mermaid)}</pre>",
                  "<script type='module'>import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';"
                  "mermaid.initialize({startOnLoad:true, theme:'dark'});</script>"]

    parts.append("<h2>Raw JSON</h2><details><summary class='muted'>expand</summary><pre>"
                 + _html.escape(json.dumps(dossier, indent=2, default=str)[:400000])
                 + "</pre></details></div></body></html>")
    return "".join(parts)


def render_markdown(target: str, dossier: dict, summary: dict) -> str:
    score = dossier.get("score") or {}
    lines = [f"# OSINT Dossier — {target}", "",
             f"- generated: {summary.get('generated')}",
             f"- exposure score: **{score.get('score','-')}/100** (grade {score.get('grade','-')})",
             f"- interpretation: {score.get('interpretation','-')}", ""]
    findings = score.get("findings") or []
    if findings:
        lines += ["## Findings", "", "| severity | finding | detail |", "|---|---|---|"]
        for f in findings:
            lines.append(f"| {f.get('severity')} | {f.get('title')} | {str(f.get('detail'))[:160]} |")
        lines.append("")
    ct = dossier.get("ct") or {}
    if ct.get("combined"):
        lines += ["## Subdomains", "", f"count: {ct.get('count')}",
                  "", "```"] + sorted(ct["combined"])[:500] + ["```", ""]
    js = dossier.get("js") or {}
    if js.get("findings"):
        lines += ["## JS secrets", ""]
        for f in js["findings"][:40]:
            lines.append(f"- **{f.get('severity')}** `{f.get('type')}` {f.get('masked')} — {str(f.get('source'))[:100]}")
        lines.append("")
    to = dossier.get("takeover") or {}
    if to.get("vulnerable"):
        lines += ["## Subdomain takeover", ""]
        for v in to["vulnerable"]:
            lines.append(f"- **VULNERABLE** {v.get('host')} → {v.get('provider')}: {v.get('evidence')}")
        lines.append("")
    if dossier.get("emails"):
        em = dossier["emails"]
        if em.get("emails"):
            lines += ["## Emails", ""] + [f"- {e}" for e in em["emails"][:200]] + [""]
    return "\n".join(lines)


def write_report(target: str, dossier: dict, outdir: str = ".", graph: dict | None = None) -> dict:
    safe = "".join(c if c.isalnum() or c in ".-_" else "_" for c in target[:80])
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    stem = d / f"osint_{safe}_{ts}"
    summary = summarize(target, dossier)

    mermaid = None
    graph_files = {}
    if graph:
        from . import pivot as pivot_mod
        mermaid = pivot_mod.to_mermaid(graph)
        gj = Path(str(stem) + "_graph.json")
        gj.write_text(json.dumps(graph, indent=2, default=str))
        Path(str(stem) + "_graph.mmd").write_text(mermaid)
        Path(str(stem) + "_graph.dot").write_text(pivot_mod.to_dot(graph))
        graph_files = {"graph_json": str(gj),
                       "graph_mermaid": str(stem) + "_graph.mmd",
                       "graph_dot": str(stem) + "_graph.dot"}

    json_path = Path(str(stem) + ".json")
    md_path = Path(str(stem) + ".md")
    html_path = Path(str(stem) + ".html")

    payload = dict(dossier)
    payload.setdefault("summary", summary)
    json_path.write_text(json.dumps(payload, indent=2, default=str))
    md_path.write_text(render_markdown(target, dossier, summary))
    html_path.write_text(render_html(target, dossier, summary, mermaid))

    return {"json": str(json_path), "md": str(md_path), "html": str(html_path),
            "summary": summary, **graph_files}


# --- legacy API kept so the v1 CLI/handlers keep working ---
def write_dossier(target: str, data: dict, outdir: str = ".") -> dict:
    return write_report(target, data, outdir)
