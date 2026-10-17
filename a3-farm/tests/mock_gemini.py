"""Mock Gemini endpoint to prove balancer rotation/failover without real keys.

Serves on 127.0.0.1:8899: first request per key returns 429, then 200.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, time
from collections import defaultdict

SEEN = defaultdict(int)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        # /v1beta/models?key=...
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        key = (q.get("key") or [""])[0]
        SEEN[key] += 1
        if SEEN[key] == 1:
            body = json.dumps({"error": {"code": 429, "message": "Quota exceeded (mock)",
                                         "status": "RESOURCE_EXHAUSTED"}}).encode()
            self.send_response(429); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            body = json.dumps({"models": [{"name": "models/gemini-3.5-flash-lite"}]}).encode()
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        key = (q.get("key") or [""])[0]
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        SEEN[key] += 1
        # odd attempts on a key -> 429, even -> 200
        if SEEN[key] % 2 == 1:
            body = json.dumps({"error": {"code": 429, "message": "Quota exceeded (mock)",
                                         "status": "RESOURCE_EXHAUSTED"}}).encode()
            self.send_response(429)
        else:
            body = json.dumps({"candidates":[{"content":{"parts":[{"text":"pong:"+key[-4:]}]}}],
                               "usageMetadata":{"totalTokenCount":3}}).encode()
            self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


if __name__ == "__main__":
    print("mock gemini on 127.0.0.1:8899")
    ThreadingHTTPServer(("127.0.0.1", 8899), H).serve_forever()
