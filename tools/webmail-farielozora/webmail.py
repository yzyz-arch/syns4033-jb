#!/usr/bin/env python3
"""
webmail.py — self-hosted webmail for farielozora.biz.id
Stdlib only (no pip install). IMAP read + SMTP send.

Run:
    python3 webmail.py                     # http://0.0.0.0:8080
    WEBMAIL_PORT=8443 python3 webmail.py

Env config:
    WEBMAIL_DOMAIN     default farielozora.biz.id
    WEBMAIL_IMAP       default mail.<domain>   (port 993, SSL)
    WEBMAIL_IMAP_PORT  default 993
    WEBMAIL_SMTP       default mail.<domain>   (port 587, STARTTLS)
    WEBMAIL_SMTP_PORT  default 587
    WEBMAIL_PORT       default 8080
    WEBMAIL_BIND       default 0.0.0.0
    WEBMAIL_SECRET     session cookie secret (set a strong value in prod)

Deploy behind TLS (caddy/nginx) and set WEBMAIL_SECRET. Use app passwords
if the mail server has MFA enabled. Sessions are in-memory (per-process).
"""

import html
import imaplib
import json
import os
import re
import smtplib
import ssl
import threading
import time
import uuid
from email import message_from_bytes, message_from_string
from email.header import decode_header
from email.utils import parseaddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, quote
import urllib.parse

# ---------------------------------------------------------------- config

DOMAIN = os.environ.get("WEBMAIL_DOMAIN", "farielozora.biz.id")
IMAP_HOST = os.environ.get("WEBMAIL_IMAP", "mail." + DOMAIN)
IMAP_PORT = int(os.environ.get("WEBMAIL_IMAP_PORT", "993"))
SMTP_HOST = os.environ.get("WEBMAIL_SMTP", "mail." + DOMAIN)
SMTP_PORT = int(os.environ.get("WEBMAIL_SMTP_PORT", "587"))
PORT = int(os.environ.get("WEBMAIL_PORT", "8080"))
BIND = os.environ.get("WEBMAIL_BIND", "0.0.0.0")
SESSION_TTL = 8 * 3600
PAGE_SIZE = 50

BACKEND = os.environ.get("WEBMAIL_BACKEND", "local").strip().lower()

SESSIONS = {}
LOCK = threading.Lock()

# ---------------------------------------------------------------- session
# Store sesi dipindah ke sessions.py supaya dipakai bareng api.py (SPA).

from sessions import (  # noqa: E402
    new_session,
    get_session,
    drop_session,
    secure_flag as _secure_flag,
)


# ---------------------------------------------------------------- mail


def imap_connect(user, password):
    c = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=20)
    c.login(user, password)
    return c


def _imap_list_folders(user, password):
    c = imap_connect(user, password)
    try:
        typ, data = c.list()
        folders = []
        if typ == "OK" and data:
            for line in data:
                if not line:
                    continue
                if isinstance(line, tuple):
                    line = line[-1]
                line = line.decode("utf-8", "replace") if isinstance(line, bytes) else str(line)
                m = re.search(r' "?([^"]+)"?\s*$', line)
                if m:
                    name = m.group(1)
                    name = name.split(".")[-1] if "." in name and "/" in name else name
                    folders.append(name.replace('"', "").strip())
        return folders or ["INBOX"]
    finally:
        try:
            c.logout()
        except Exception:
            pass


def _decode_hdr(val):
    if not val:
        return ""
    try:
        parts = decode_header(val)
        out = []
        for chunk, enc in parts:
            if isinstance(chunk, bytes):
                out.append(chunk.decode(enc or "utf-8", "replace"))
            else:
                out.append(chunk)
        return "".join(out)
    except Exception:
        return str(val)


def _imap_list_messages(user, password, folder="INBOX", limit=PAGE_SIZE):
    c = imap_connect(user, password)
    try:
        typ, _ = c.select(folder, readonly=True)
        if typ != "OK":
            raise RuntimeError("folder tidak ditemukan: %s" % folder)
        typ, data = c.uid("search", None, "ALL")
        uids = (data[0] or b"").split()
        uids = uids[-limit:][::-1]  # newest first
        if not uids:
            return []
        seq = b",".join(uids)
        typ, data = c.uid(
            "fetch", seq, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
        )
        by_uid = {}
        for item in data or []:
            if isinstance(item, tuple):
                meta, raw = item
                m = re.search(rb"UID (\d+)", meta)
                if not m:
                    continue
                uid = int(m.group(1))
                msg = message_from_bytes(raw)
                by_uid[uid] = {
                    "uid": uid,
                    "from": parseaddr(_decode_hdr(msg.get("From")))[0]
                    or parseaddr(_decode_hdr(msg.get("From")))[1],
                    "subject": _decode_hdr(msg.get("Subject")) or "(tanpa subjek)",
                    "date": _decode_hdr(msg.get("Date")),
                }
        return [by_uid[uid] for uid in sorted(by_uid, reverse=True)]
    finally:
        try:
            c.logout()
        except Exception:
            pass


def _decode_part(part):
    try:
        raw = part.get_payload(decode=True)
        if raw is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return raw.decode(charset, "replace")
    except Exception:
        return ""


def extract_body(msg):
    text = htmlp = None
    if msg.is_multipart():
        for p in msg.walk():
            ctype = p.get_content_type()
            if "attachment" in str(p.get("Content-Disposition", "")):
                continue
            if ctype == "text/plain" and text is None:
                text = _decode_part(p)
            elif ctype == "text/html" and htmlp is None:
                htmlp = _decode_part(p)
    else:
        if msg.get_content_type() == "text/html":
            htmlp = _decode_part(msg)
        else:
            text = _decode_part(msg)
    return text or "", htmlp or ""


def _imap_get_message(user, password, folder, uid):
    c = imap_connect(user, password)
    try:
        typ, _ = c.select(folder, readonly=True)
        if typ != "OK":
            raise RuntimeError("folder tidak ditemukan: %s" % folder)
        typ, data = c.uid("fetch", str(int(uid)).encode(), "(BODY.PEEK[])")
        raw = None
        for item in data or []:
            if isinstance(item, tuple):
                raw = item[1]
        if raw is None:
            raise RuntimeError("pesan tidak ditemukan")
        msg = message_from_bytes(raw)
        text, htmlp = extract_body(msg)
        return {
            "from": _decode_hdr(msg.get("From")),
            "to": _decode_hdr(msg.get("To")),
            "subject": _decode_hdr(msg.get("Subject")) or "(tanpa subjek)",
            "date": _decode_hdr(msg.get("Date")),
            "text": text,
            "html": htmlp,
        }
    finally:
        try:
            c.logout()
        except Exception:
            pass


def _imap_send_mail(user, password, to, subject, body):
    msg = message_from_string(
        "From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n%s" % (user, to, subject, body)
    )
    msg["From"] = user
    msg["To"] = to
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.ehlo()
        try:
            s.starttls(context=ctx)
            s.ehlo()
        except smtplib.SMTPNotSupportedError:
            pass
        s.login(user, password)
        s.send_message(msg)


# ---------------------------------------------------------------- backend dispatch


def _local():
    import backend_local

    return backend_local


def authenticate(user, password):
    if BACKEND == "local":
        return _local().verify(user, password)
    try:
        c = imap_connect(user, password)
        c.logout()
        return True
    except Exception:
        return False


def list_folders(user, password):
    if BACKEND == "local":
        return _local().folders(user)
    return _imap_list_folders(user, password)


def list_messages(user, password, folder="INBOX", limit=PAGE_SIZE):
    if BACKEND == "local":
        return _local().list_messages(user, folder, limit)
    return _imap_list_messages(user, password, folder, limit)


def get_message(user, password, folder, uid):
    if BACKEND == "local":
        return _local().get_message(user, folder, uid)
    return _imap_get_message(user, password, folder, uid)


def send_mail(user, password, to, subject, body):
    if BACKEND == "local":
        return _local().send(user, password, to, subject, body)
    return _imap_send_mail(user, password, to, subject, body)


def mark_read(user, folder, uid):
    if BACKEND == "local":
        try:
            _local().mark_read(user, folder, uid)
        except Exception:
            pass


# ---------------------------------------------------------------- html ui

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;background:#0f1420;color:#e7ecf5}
a{color:#7cc4ff;text-decoration:none}
.wrap{max-width:1000px;margin:0 auto;padding:24px}
.brand{font-size:20px;font-weight:700;letter-spacing:.5px}
.brand span{color:#4f8cff}
.top{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;background:#151c2c;border-bottom:1px solid #232c42}
.top .who{color:#93a0b8;font-size:12px}
.card{background:#151c2c;border:1px solid #232c42;border-radius:12px;padding:24px;margin-top:24px}
input,textarea{width:100%;padding:11px 13px;border-radius:9px;border:1px solid #2a3550;background:#0f1524;color:#e7ecf5;font:inherit}
input:focus,textarea:focus{outline:none;border-color:#4f8cff}
label{display:block;margin:14px 0 6px;color:#93a0b8;font-size:12px;text-transform:uppercase;letter-spacing:.7px}
.btn{display:inline-block;background:#4f8cff;color:#fff;border:0;border-radius:9px;padding:11px 20px;font:inherit;font-weight:600;cursor:pointer}
.btn:hover{background:#3a72e8}
.btn.sec{background:#232c42}
.err{background:#3a1c2c;border:1px solid #7a2c4c;color:#ff9db4;padding:11px 14px;border-radius:9px;margin-top:14px}
.ok{background:#12301f;border:1px solid #2c7a4c;color:#9de0b4;padding:11px 14px;border-radius:9px;margin-top:14px}
.layout{display:grid;grid-template-columns:200px 1fr;gap:20px}
.side a{display:block;padding:10px 13px;border-radius:9px;color:#93a0b8}
.side a.on,.side a:hover{background:#1b2438;color:#e7ecf5}
table{width:100%;border-collapse:collapse}
th{text-align:left;color:#93a0b8;font-size:11px;text-transform:uppercase;letter-spacing:.8px;padding:10px 12px;border-bottom:1px solid #232c42}
td{padding:12px;border-bottom:1px solid #1c2438}
tr:hover td{background:#182034}
.muted{color:#93a0b8}
.wrapmail{background:#fff;color:#111;border-radius:10px;padding:18px;overflow:auto}
pre{white-space:pre-wrap;font:inherit}
h2{font-size:18px;margin-bottom:6px}
"""


def page(title, body, session=None):
    who = ""
    nav = ""
    if session:
        who = '<div class="who">%s &nbsp;|&nbsp; <a href="/logout">keluar</a></div>' % html.escape(
            session["user"]
        )
        nav = ""
    return f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} &middot; Webmail {html.escape(DOMAIN)}</title>
<style>{CSS}</style></head><body>
<div class="top"><div class="brand">webmail<span>.</span>{html.escape(DOMAIN)}</div>{who}</div>
<div class="wrap">{body}</div></body></html>"""


def login_page(msg=""):
    err = f'<div class="err">{html.escape(msg)}</div>' if msg else ""
    return page(
        "Masuk",
        f"""<div class="card" style="max-width:420px;margin:48px auto">
<h2>Masuk ke webmail</h2>
<p class="muted">Akun email @{html.escape(DOMAIN)} Anda.</p>
{err}
<form method="post" action="/login">
<label>Email</label><input name="email" type="email" placeholder="nama@{html.escape(DOMAIN)}" required autofocus>
<label>Password</label><input name="password" type="password" required>
<div style="margin-top:20px"><button class="btn" type="submit">Masuk</button></div>
</form></div>""",
    )


# ---------------------------------------------------------------- handler


class Handler(BaseHTTPRequestHandler):
    server_version = "webmail/" + DOMAIN
    protocol_version = "HTTP/1.1"

    # ---- helpers
    def _cookie(self):
        raw = self.headers.get("Cookie", "")
        m = re.search(r"webmail_session=([0-9a-f]+)", raw)
        return m.group(1) if m else None

    def _sess(self):
        return get_session(self._cookie())

    def _send(self, html_doc, status=200, extra_headers=None):
        data = html_doc.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra_headers or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, loc, headers=None):
        self.send_response(302)
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        for k, v in (headers or []):
            self.send_header(k, v)
        self.end_headers()

    def _raw_body(self):
        if getattr(self, "_body_cache", None) is None:
            length = int(self.headers.get("Content-Length") or 0)
            self._body_cache = self.rfile.read(length) if length else b""
        return self._body_cache

    def _form(self):
        body = self._raw_body().decode("utf-8", "replace")
        return {k: v[0] for k, v in parse_qs(body).items()}

    def _json(self, payload, status=200, extra_headers=None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra_headers or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _bytes(self, data, ctype, filename=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        if filename:
            safe = urllib.parse.quote(filename)
            self.send_header(
                "Content-Disposition", "attachment; filename*=UTF-8''%s" % safe
            )
        self.end_headers()
        self.wfile.write(data)

    def _static(self, relpath):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
        target = os.path.realpath(os.path.join(base, relpath.lstrip("/")))
        if not target.startswith(os.path.realpath(base)) or not os.path.isfile(target):
            self._json({"message": "not found"}, 404)
            return
        ctypes = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".mjs": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
        }
        ext = os.path.splitext(target)[1].lower()
        with open(target, "rb") as f:
            data = f.read()
        cache = "public, max-age=86400" if ext == ".mjs" else "no-cache"
        self.send_response(200)
        self.send_header("Content-Type", ctypes.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass

    # ---- GET
    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = u.path.rstrip("/") or "/"
        sess = self._sess()

        if path.startswith("/api"):
            import api as _api

            if _api.handle(self, "GET"):
                return

        if path in ("/", "/app"):
            self._static("index.html")
            return

        if path.startswith("/ui/"):
            self._static(path[len("/ui/") :])
            return

        if path == "/healthz":
            self._send("<html><body>ok</body></html>")
            return

        if path == "/login":
            if sess:
                self._redirect("/inbox")
                return
            self._send(login_page())
            return

        if not sess:
            self._redirect("/login")
            return

        try:
            if path == "/inbox":
                folder = q.get("folder", "INBOX")
                msgs = list_messages(sess["user"], sess["password"], folder)
                rows = "".join(
                    '<tr onclick="location.href=\'/view?folder=%s&amp;uid=%s\'" style="cursor:pointer">'
                    "<td>%s</td><td>%s</td><td class='muted'>%s</td></tr>"
                    % (
                        quote(folder),
                        quote(str(m["uid"])),
                        html.escape(m["from"] or "-"),
                        html.escape(m["subject"]),
                        html.escape(m["date"] or ""),
                    )
                    for m in msgs
                ) or '<tr><td colspan="3" class="muted">Kotak masuk kosong.</td></tr>'
                try:
                    folder_links = "".join(
                        '<a class="%s" href="/inbox?folder=%s">%s</a>'
                        % (
                            "on" if f_ == folder else "",
                            quote(f_),
                            html.escape(f_),
                        )
                        for f_ in list_folders(sess["user"], sess["password"])
                    )
                except Exception:
                    folder_links = '<a class="on" href="/inbox?folder=INBOX">INBOX</a>'
                body = f"""<div class="layout"><div class="side">
{folder_links}
<a href="/compose">Tulis Pesan</a>
<a href="/logout">Keluar</a></div>
<div><div class="card"><h2>Kotak Masuk &mdash; {html.escape(folder)}</h2>
<p class="muted">{len(msgs)} pesan terbaru</p>
<table><tr><th>Pengirim</th><th>Subjek</th><th>Tanggal</th></tr>{rows}</table>
</div></div></div>"""
                self._send(page("Kotak Masuk", body, sess))
                return

            if path == "/view":
                folder = q.get("folder", "INBOX")
                m = get_message(
                    sess["user"],
                    sess["password"],
                    folder,
                    q.get("uid", ""),
                )
                mark_read(sess["user"], folder, q.get("uid", ""))
                if m["html"]:
                    inner = '<iframe sandbox="allow-popups" style="width:100%;min-height:420px;border:0" srcdoc="%s"></iframe>' % html.escape(
                        m["html"], quote=True
                    )
                else:
                    inner = "<pre>%s</pre>" % html.escape(m["text"])
                body = f"""<div class="card"><a href="/inbox">&larr; kembali</a>
<h2 style="margin-top:12px">{html.escape(m["subject"])}</h2>
<p class="muted">{html.escape(m["from"])} &rarr; {html.escape(m["to"])}<br>{html.escape(m["date"])}</p>
<hr style="border-color:#232c42;margin:14px 0">
<div class="wrapmail">{inner}</div></div>"""
                self._send(page(m["subject"], body, sess))
                return

            if path == "/compose":
                body = f"""<div class="card" style="max-width:640px">
<h2>Tulis Pesan</h2>
<form method="post" action="/send">
<input type="hidden" name="csrf" value="{sess["csrf"]}">
<label>Kepada</label><input name="to" type="email" required value="{html.escape(q.get("to",""))}">
<label>Subjek</label><input name="subject" required>
<label>Isi Pesan</label><textarea name="body" rows="12" required></textarea>
<div style="margin-top:18px"><button class="btn" type="submit">Kirim</button>
<a class="btn sec" href="/inbox" style="margin-left:8px">Batal</a></div>
</form></div>"""
                self._send(page("Tulis Pesan", body, sess))
                return

            if path == "/logout":
                drop_session(self._cookie())
                self._redirect("/login", [("Set-Cookie", "webmail_session=; Max-Age=0; Path=/")])
                return

            self._send(page("404", '<div class="card">Halaman tidak ditemukan.</div>', sess), 404)
        except Exception as e:
            body = f'<div class="card"><div class="err">Gagal: {html.escape(str(e))}</div><p style="margin-top:12px"><a href="/inbox">kembali</a></p></div>'
            self._send(page("Error", body, sess), 500)

    # ---- POST
    def do_POST(self):
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"

        if path.startswith("/api"):
            import api as _api

            if _api.handle(self, "POST"):
                return

        f = self._form()

        if path == "/login":
            user = (f.get("email") or "").strip()
            pw = f.get("password") or ""
            if not user or not pw:
                self._send(login_page("Email dan password wajib diisi."))
                return
            if not authenticate(user, pw):
                self._send(login_page("Login gagal. Cek email/password."))
                return
            tok = new_session(user, pw)
            self._redirect("/inbox", [("Set-Cookie", "webmail_session=%s; HttpOnly; SameSite=Lax%s; Path=/" % (tok, _secure_flag(self.headers)))])
            return

        sess = self._sess()
        if not sess:
            self._redirect("/login")
            return

        if path == "/send":
            if f.get("csrf") != sess["csrf"]:
                self._send(page("Error", '<div class="card"><div class="err">CSRF token tidak valid.</div></div>', sess), 403)
                return
            try:
                res = send_mail(
                    sess["user"],
                    sess["password"],
                    (f.get("to") or "").strip(),
                    f.get("subject") or "(tanpa subjek)",
                    f.get("body") or "",
                )
                note = ""
                if isinstance(res, dict) and res.get("missing"):
                    note = '<p class="muted" style="margin-top:10px">Catatan: mailbox tidak ada untuk: %s</p>' % html.escape(
                        ", ".join(res["missing"])
                    )
                body = '<div class="card"><div class="ok">Pesan terkirim.</div>%s<p style="margin-top:12px"><a href="/inbox">kembali ke kotak masuk</a></p></div>' % note
                self._send(page("Terkirim", body, sess))
            except Exception as e:
                body = f'<div class="card"><div class="err">Gagal mengirim: {html.escape(str(e))}</div><p style="margin-top:12px"><a href="/compose">coba lagi</a></p></div>'
                self._send(page("Gagal", body, sess), 500)
            return

        self._redirect("/inbox")


def main():
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    print("[*] webmail %s -> http://%s:%d  (IMAP %s:%d, SMTP %s:%d)"
          % (DOMAIN, BIND, PORT, IMAP_HOST, IMAP_PORT, SMTP_HOST, SMTP_PORT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
