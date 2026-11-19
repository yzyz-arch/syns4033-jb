#!/usr/bin/env python3
"""apipwn selftest: a deliberately broken mock API + detection assertions.

The mock reproduces every class the harness claims to catch:
  * exposed OpenAPI spec
  * auth on GET /api/v1/users, none on PUT (method gap) and on /api/v2/users
  * CORS origin reflection with credentials
  * tRPC protectedProcedure with no role check (anonymous admin.wipe)
  * CXF-style MTOM xop:Include that expands file:///etc/passwd
  * TRACE enabled

Run: python3 selftest.py      (or: ./apipwn.py selftest)
Exit 0 = all detections fired.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import apipwn

OPENAPI = {
    "openapi": "3.0.1",
    "servers": [{"url": "/"}],
    "components": {
        "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}}
    },
    "paths": {
        "/api/v1/users": {
            "get": {"operationId": "listUsers", "security": [{"ApiKeyAuth": []}]},
            "put": {"operationId": "replaceUsers"},
        },
        "/api/v1/orders": {"get": {"operationId": "listOrders"}},
    },
}


class Mock(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silence
        pass

    # -- helpers ---------------------------------------------------------
    def _send(self, code: int, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _cors(self) -> dict:
        origin = self.headers.get("Origin")
        if origin:
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Headers": "*",
                "Vary": "Origin",
            }
        return {}

    def _authed(self) -> bool:
        return self.headers.get("X-API-Key") == "secret"

    # -- routes ----------------------------------------------------------
    def do_GET(self):
        p = self.path.split("?")[0]
        cors = self._cors()
        if p == "/openapi.json":
            return self._send(200, OPENAPI)
        if p == "/api/v1/users":
            if not self._authed():
                return self._send(401, {"error": "api key required"}, extra=cors)
            return self._send(200, {"users": [{"id": 1, "email": "a@b.c"}]}, extra=cors)
        if p == "/api/v1/orders":
            if not self._authed():
                return self._send(403, {"error": "forbidden"}, extra=cors)
            return self._send(200, {"orders": []}, extra=cors)
        if p == "/api/v2/users":  # old version, no auth at all
            return self._send(200, {"users": [{"id": 1, "email": "a@b.c"}], "v": 2}, extra=cors)
        if p == "/api/v3/users":
            return self._send(200, {"users": [{"id": 1}, {"id": 2}]}, extra=cors)
        return self._send(404, {"error": "not found"}, extra=cors)

    def do_PUT(self):
        p = self.path.split("?")[0]
        self._body()
        if p == "/api/v1/users":
            return self._send(200, {"ok": True, "replaced": 1}, extra=self._cors())
        return self._send(404, {"error": "nf"}, extra=self._cors())

    def do_POST(self):
        p = self.path.split("?")[0]
        raw = self._body()
        cors = self._cors()

        if p.startswith("/api/trpc/"):
            proc = p.rsplit("/", 1)[-1]
            if proc in ("admin.wipe", "admin.list", "backgroundMigrations.retry"):
                return self._send(200, {"result": {"data": {"ok": True, "proc": proc}}}, extra=cors)
            if proc == "__apipwn.ping":
                return self._send(404, {"error": {"json": {"message": "No procedure"}}}, extra=cors)
            return self._send(404, {"error": {"json": {"message": "No procedure"}}}, extra=cors)

        if p == "/soap":
            if b"xop:Include" in raw and b"file:///etc/passwd" in raw:
                body = (
                    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                    "<soap:Body><ns:getFileResponse xmlns:ns=\"http://target/\">"
                    "<return>root:x:0:0:root:/root:/bin/bash\n"
                    "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n</return>"
                    "</ns:getFileResponse></soap:Body></soap:Envelope>"
                )
                return self._send(200, body, ctype="text/xml")
            if b"xop:Include" in raw:
                return self._send(500, "<soap:Fault>MTOM fetch failed</soap:Fault>", ctype="text/xml")
            return self._send(200, "<ok/>", ctype="text/xml")

        if p == "/graphql":
            return self._send(200, {"data": {"__schema": {"types": [{"name": "User"}]}}}, extra=cors)

        return self._send(404, {"error": "nf"}, extra=cors)

    def do_DELETE(self):
        return self._send(405, {"error": "method not allowed"}, extra=self._cors())

    def do_OPTIONS(self):
        return self._send(204, b"", extra=self._cors())

    def do_TRACE(self):
        self.send_response(200)
        self.send_header("Content-Type", "message/http")
        body = ("TRACE %s HTTP/1.1\r\nHost: mock\r\n" % self.path).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_against(port: int):
    target = "http://127.0.0.1:%d" % port
    client = apipwn.Client(timeout=5.0)
    rep = apipwn.Report()

    recon = apipwn.module_recon(client, target, rep)
    apipwn.module_probe(client, target, rep, recon)
    apipwn.module_trpc(client, target, rep, ["admin", "backgroundMigrations"])
    apipwn.module_cxf(client, target + "/soap", rep, "getFile", "arg0", None)
    return rep


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    print("[selftest] mock API on http://127.0.0.1:%d" % port)

    try:
        rep = run_against(port)
    finally:
        srv.shutdown()

    kinds = {f.kind for f in rep.findings}
    print("[selftest] kinds detected: %s" % ", ".join(sorted(kinds)))

    expect = {
        "spec_exposed",
        "cors_reflection",
        "method_authz_gap",
        "version_downgrade",
        "trace_enabled",
        "trpc_anonymous_privileged",
        "cxf_lfi",
        "graphql_introspection",
    }
    missing = sorted(expect - kinds)
    if missing:
        print("[selftest] FAIL missing: %s" % ", ".join(missing))
        rep.print_summary()
        return 1

    rep.print_summary()
    print("\n[selftest] PASS  %d/%d detections, %d findings"
          % (len(expect), len(expect), len(rep.findings)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
