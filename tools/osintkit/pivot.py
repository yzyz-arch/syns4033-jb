"""Pivot graph: turn a dossier into nodes/edges + Mermaid / Graphviz exports.

Everything collected by the other modules becomes one linkable graph so the
operator can see the attack surface instead of reading nested JSON.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _nid(kind: str, value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", str(value))[:90]
    return f"{kind}:{safe}"


def build_graph(target: str, dossier: dict, max_nodes: int = 400) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add(kind: str, value: str, **attrs) -> str:
        nid = _nid(kind, value)
        if nid not in nodes and len(nodes) < max_nodes:
            nodes[nid] = {"id": nid, "kind": kind, "label": str(value), **attrs}
        return nid

    def link(a: str, b: str, rel: str, **attrs):
        if a in nodes and b in nodes:
            edges.append({"from": a, "to": b, "rel": rel, **attrs})

    root = add("domain", target)
    if not root or len(nodes) >= max_nodes:
        return {"nodes": list(nodes.values()), "edges": edges}

    # subdomains + their IPs (v2 pipeline stores them under ct.combined)
    subs = (dossier.get("subdomains") or {}).get("combined") \
        or dossier.get("subdomains") \
        or (dossier.get("ct") or {}).get("combined") \
        or []
    if isinstance(subs, dict):
        subs = subs.get("combined") or []
    resolved = (dossier.get("resolved") or {})
    for h in list(subs)[:150]:
        sid = add("host", h)
        link(root, sid, "has_subdomain")
        ip = resolved.get(h) if isinstance(resolved, dict) else None
        if ip:
            iid = add("ip", ip)
            link(sid, iid, "resolves_to")

    # ips -> asn
    for ip, info in (dossier.get("ip_intel") or {}).items() if isinstance(dossier.get("ip_intel"), dict) else []:
        iid = add("ip", ip)
        asn = ((info or {}).get("geo") or {}).get("as")
        if asn:
            aid = add("asn", asn)
            link(iid, aid, "announced_by")

    # technologies
    techs = ((dossier.get("http") or {}).get("technologies") or [])
    for t in techs:
        tid = add("tech", t)
        link(root, tid, "runs")

    # TLS issuer + SANs
    tls = dossier.get("tls") or {}
    issuer = (tls.get("issuer") or {}).get("organizationName") or (tls.get("issuer") or {}).get("commonName")
    if issuer:
        cid = add("ca", issuer)
        link(root, cid, "certificate_issued_by")
    for san in (tls.get("san") or [])[:30]:
        if san.lower() != target.lower():
            sid = add("host", san)
            link(root, sid, "same_certificate")

    # emails
    em = dossier.get("emails") or {}
    for e in (em.get("emails") if isinstance(em, dict) else em) or []:
        eid = add("email", e)
        link(root, eid, "email_contact")

    # buckets
    cl = dossier.get("cloud") or {}
    for b in (cl.get("public") or []) + (cl.get("private") or []):
        bid = add("bucket", f'{b.get("provider")}:{b.get("bucket")}')
        link(root, bid, "cloud_storage", status=b.get("status"))

    # takeover findings
    to = dossier.get("takeover") or {}
    for v in (to.get("vulnerable") or []):
        hid = add("host", v.get("host"))
        pid = add("provider", v.get("provider") or "unknown")
        link(hid, pid, "DANGLING_TO", severity="critical")

    # secret findings
    js = dossier.get("js") or {}
    for f in (js.get("findings") or [])[:40]:
        if f.get("severity") in ("critical", "high"):
            sid = add("secret", f'{f.get("type")}@{f.get("source")}'[:90])
            link(root, sid, "leaks_secret", severity=f.get("severity"))

    # related domains from CT
    for rd in ((dossier.get("ct") or {}).get("related_domains_from_san") or [])[:24]:
        rid = add("domain", rd)
        link(root, rid, "shares_certificate")

    return {"target": target, "nodes": list(nodes.values()), "edges": edges,
            "node_count": len(nodes), "edge_count": len(edges)}


def to_mermaid(graph: dict) -> str:
    lines = ["graph LR"]
    ids: dict[str, str] = {}
    for i, n in enumerate(graph.get("nodes") or []):
        alias = f"n{i}"
        ids[n["id"]] = alias
        label = str(n.get("label", "")).replace('"', "'")[:60]
        lines.append(f'  {alias}["{n.get("kind")}: {label}"]')
    for e in graph.get("edges") or []:
        a, b = ids.get(e["from"]), ids.get(e["to"])
        if a and b:
            lines.append(f'  {a} -->|{e.get("rel","")}| {b}')
    return "\n".join(lines)


def to_dot(graph: dict) -> str:
    lines = ["digraph osint {", "  rankdir=LR;", '  node [shape=box, style=rounded, fontname="Helvetica"];']
    colors = {"domain": "#1f77b4", "host": "#2ca02c", "ip": "#ff7f0e", "asn": "#9467bd",
              "tech": "#8c564b", "email": "#e377c2", "bucket": "#d62728", "secret": "#d62728",
              "ca": "#7f7f7f", "provider": "#bcbd22"}
    for n in graph.get("nodes") or []:
        nid = n["id"].replace('"', "")
        label = str(n.get("label", "")).replace('"', "'")[:60]
        color = colors.get(n.get("kind"), "#cccccc")
        lines.append(f'  "{nid}" [label="{n.get("kind")}: {label}", fillcolor="{color}", style=filled];')
    for e in graph.get("edges") or []:
        a = e["from"].replace('"', "")
        b = e["to"].replace('"', "")
        style = "color=red, penwidth=2" if e.get("severity") == "critical" else ""
        lines.append(f'  "{a}" -> "{b}" [label="{e.get("rel","")}"{("," + style) if style else ""}];')
    lines.append("}")
    return "\n".join(lines)


def save(graph: dict, outdir: str = ".", stem: str = "graph") -> dict:
    d = Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    mermaid = to_mermaid(graph)
    dot = to_dot(graph)
    (d / f"{stem}.mmd").write_text(mermaid)
    (d / f"{stem}.dot").write_text(dot)
    (d / f"{stem}.json").write_text(json.dumps(graph, indent=2, default=str))
    try:
        from .report import render_mermaid_html
        (d / f"{stem}.html").write_text(render_mermaid_html(mermaid, stem))
    except Exception:
        pass
    return {"mermaid": str(d / f"{stem}.mmd"), "dot": str(d / f"{stem}.dot"),
            "json": str(d / f"{stem}.json"), "html": str(d / f"{stem}.html"),
            "node_count": graph.get("node_count"), "edge_count": graph.get("edge_count")}
