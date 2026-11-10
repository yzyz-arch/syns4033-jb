#!/usr/bin/env python3
"""
api.py — JSON API untuk SPA webmail (tampilan Cloud Mail).

Dipakai oleh webmail.py: setiap request /api/* didelegasikan ke handle().
Auth memakai cookie session yang sama dengan UI lama (sessions.py).

Endpoints:
    POST /api/login            {email,password}
    POST /api/logout
    GET  /api/me
    GET  /api/folders
    GET  /api/emails?folder=&offset=&size=
    GET  /api/email?folder=&uid=
    GET  /api/attach?folder=&uid=&idx=
    GET  /api/search?q=&type=&folder=
    POST /api/send             {to,cc,subject,body}
    POST /api/star             {folder,uid,star}
    POST /api/read             {folder,uids[]}
    POST /api/delete           {folder,uids[]}
"""

import json
import os
import re
import time
import urllib.parse
from email import message_from_bytes
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

import backend_local as be
import sessions as ss

STARS = os.environ.get(
    "WEBMAIL_STARS", "/var/lib/webmail-farielozora/stars.json"
)

FOLDERS = ("INBOX", "Sent", "Drafts", "Trash")

# ---------------------------------------------------------------- register

REGISTER_OPEN = (os.environ.get("WEBMAIL_REGISTER", "1").strip().lower()
                 not in ("0", "false", "no", "off"))
REGISTER_DOMAIN = os.environ.get(
    "WEBMAIL_REGISTER_DOMAIN",
    os.environ.get("WEBMAIL_DOMAIN", "farielozora.biz.id"),
).strip().lower()
MIN_PASSWORD = int(os.environ.get("WEBMAIL_MIN_PASSWORD", "8"))
REGISTER_LIMIT = int(os.environ.get("WEBMAIL_REGISTER_LIMIT", "20"))
REGISTER_WINDOW = 3600

_LOCAL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,30})$")
_REGISTER_HITS = {}



# ---------------------------------------------------------------- helpers


def _load_stars():
    try:
        with open(STARS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_stars(d):
    os.makedirs(os.path.dirname(STARS), exist_ok=True)
    tmp = STARS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, STARS)
    try:
        os.chmod(STARS, 0o600)
    except OSError:
        pass


def _star_key(user, folder, uid):
    return "%s|%s|%s" % (user, folder, uid)


def _is_star(user, folder, uid):
    return 1 if _load_stars().get(_star_key(user, folder, uid)) else 0


def _msg_path(user, folder, uid):
    base = be._folder_path(user, folder)
    for sub in ("new", "cur"):
        p = os.path.join(base, sub, uid)
        if os.path.isfile(p):
            return p, sub
    return None, None


def _raw(user, folder, uid):
    p, sub = _msg_path(user, folder, uid)
    if not p:
        return None, None
    with open(p, "rb") as f:
        return f.read(), sub


def _attachments(msg):
    out = []
    if not msg.is_multipart():
        return out
    idx = 0
    for part in msg.walk():
        fn = part.get_filename()
        if not fn:
            continue
        from email.header import decode_header

        try:
            fn = "".join(
                c.decode(e or "utf-8", "replace") if isinstance(c, bytes) else c
                for c, e in decode_header(fn)
            )
        except Exception:
            fn = str(fn)
        payload = part.get_payload(decode=True) or b""
        out.append(
            {
                "idx": idx,
                "filename": fn,
                "size": len(payload),
                "contentType": part.get_content_type(),
            }
        )
        idx += 1
    return out


def _preview(raw):
    """Ambil ~120 char teks pertama untuk snippet list."""
    try:
        msg = message_from_bytes(raw)
        text, html = be._body(msg)
        src = text or html
        src = " ".join(src.split())
        return src[:180]
    except Exception:
        return ""


def _ts(raw, mtime):
    """createTime dalam epoch ms; pakai header Date kalau ada, fallback mtime."""
    try:
        msg = message_from_bytes(raw)
        d = msg.get("Date")
        if d:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(d)
            if dt:
                return int(dt.timestamp() * 1000)
    except Exception:
        pass
    return int(mtime * 1000)


def _row(user, folder, name, path, mtime, stars):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    try:
        msg = message_from_bytes(raw)
    except Exception:
        return None
    disp, addr = parseaddr(be._hdr(msg.get("From")))
    to_disp, to_addr = parseaddr(be._hdr(msg.get("To")))
    subj = be._hdr(msg.get("Subject")) or "(tanpa subjek)"
    unread = 1 if (folder == "INBOX" and os.sep + "new" + os.sep in path) else 0
    is_star = 1 if stars.get(_star_key(user, folder, name)) else 0
    sent = folder != "INBOX"
    return {
        "emailId": name,
        "uid": name,
        "name": disp or addr or "-",
        "sendEmail": addr or disp or "-",
        "toEmail": to_addr or be._hdr(msg.get("To")),
        "subject": subj,
        "listText": _preview(raw),
        "createTime": _ts(raw, mtime),
        "unread": unread,
        "isStar": is_star,
        "type": 1 if sent else 0,
        "status": 1 if sent else 0,
        "folder": folder,
    }


def _count(user, folder):
    return len(be._message_files(user, folder))


def _unread(user, folder):
    if folder != "INBOX":
        return 0
    base = be._folder_path(user, folder)
    d = os.path.join(base, "new")
    if not os.path.isdir(d):
        return 0
    return sum(1 for n in os.listdir(d) if n.endswith(".eml"))


# ---------------------------------------------------------------- ops


def op_login(body):
    email = (body.get("email") or "").strip().lower()
    pw = body.get("password") or ""
    if not email or not pw:
        return 400, {"message": "Email dan password wajib diisi."}
    if not be.verify(email, pw):
        return 401, {"message": "Login gagal. Cek email/password."}
    users = be._load_users()
    display = (users.get(email) or {}).get("display") or email.split("@")[0]
    tok = ss.new_session(email, pw, display)
    return 200, {
        "token": tok,
        "user": {"email": email, "name": display, "display": display},
    }


def op_config():
    return 200, {
        "domain": REGISTER_DOMAIN,
        "register": REGISTER_OPEN,
        "minPassword": MIN_PASSWORD,
        "maxPerHour": REGISTER_LIMIT,
    }


def _rate_ok(ip):
    """True kalau IP masih boleh registrasi (sliding window per jam)."""
    if REGISTER_LIMIT <= 0:
        return True
    now = time.time()
    hits = [t for t in _REGISTER_HITS.get(ip, []) if now - t < REGISTER_WINDOW]
    if len(hits) >= REGISTER_LIMIT:
        _REGISTER_HITS[ip] = hits
        return False
    hits.append(now)
    _REGISTER_HITS[ip] = hits
    return True


def _welcome(addr):
    """Kirim 1 pesan sambutan ke INBOX user baru."""
    try:
        msg = EmailMessage()
        msg["From"] = "webmail@" + REGISTER_DOMAIN
        msg["To"] = addr
        msg["Subject"] = "Selamat datang di Cloud Mail %s" % REGISTER_DOMAIN
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=REGISTER_DOMAIN)
        msg.set_content(
            "Halo!\n\n"
            "Mailbox %s sudah aktif.\n\n"
            "Yang bisa kamu pakai sekarang:\n"
            "  - kirim & terima pesan antar mailbox di server ini\n"
            "  - folder Inbox, Sent, Drafts, Trash\n"
            "  - star, cari, balas, teruskan, dark mode\n\n"
            "Catatan: domain ini belum punya MTA, jadi email dari/ke internet\n"
            "(Gmail dll) belum bisa. Pesan hanya beredar di dalam server.\n\n"
            "Waktu dibuat: %s\n" % (addr, time.strftime("%Y-%m-%d %H:%M:%S"))
        )
        be.deliver(addr, msg.as_bytes())
    except Exception:
        pass


def op_register(body, ip):
    if not REGISTER_OPEN:
        return 403, {"message": "Registrasi ditutup."}
    if not _rate_ok(ip):
        return 429, {"message": "Terlalu banyak pendaftaran dari IP ini. Coba lagi nanti."}

    raw = (body.get("email") or "").strip().lower()
    pw = body.get("password") or ""
    pw2 = body.get("confirm") if body.get("confirm") is not None else pw
    display = (body.get("name") or "").strip()[:40]

    # email boleh dikirim utuh atau cuma local-part
    if "@" in raw:
        local, _, domain = raw.partition("@")
    else:
        local, domain = raw, REGISTER_DOMAIN
    local = local.strip()
    domain = (domain or REGISTER_DOMAIN).strip().lower()

    if domain != REGISTER_DOMAIN:
        return 400, {"message": "Domain harus @%s." % REGISTER_DOMAIN}
    if not local or not _LOCAL_RE.match(local):
        return 400, {
            "message": "Nama mailbox 3-31 karakter, hanya huruf kecil/angka/titik/_-."
        }
    if len(pw) < MIN_PASSWORD:
        return 400, {"message": "Password minimal %d karakter." % MIN_PASSWORD}
    if pw != pw2:
        return 400, {"message": "Konfirmasi password tidak sama."}

    addr = local + "@" + domain
    if be.user_exists(addr):
        return 409, {"message": "Mailbox %s sudah dipakai." % addr}

    try:
        be.add_user(addr, pw, display or local)
    except Exception as e:  # noqa: BLE001
        return 500, {"message": "Gagal membuat mailbox: %s" % e}

    _welcome(addr)
    tok = ss.new_session(addr, pw, display or local)
    users = be._load_users()
    name = (users.get(addr) or {}).get("display") or local
    return 200, {
        "token": tok,
        "user": {"email": addr, "name": name, "display": name},
    }


def op_me(sess):
    u = sess["user"]
    users = be._load_users()
    return 200, {
        "email": u,
        "name": (users.get(u) or {}).get("display") or u.split("@")[0],
        "display": sess.get("display") or u.split("@")[0],
        "role": {"name": "user"},
        "sendCount": None,
    }


def op_folders(sess):
    u = sess["user"]
    names = be.folders(u)
    if not names:
        names = list(FOLDERS)
    out = []
    for n in names:
        out.append(
            {"name": n, "total": _count(u, n), "unread": _unread(u, n)}
        )
    return 200, {"folders": out}


def op_emails(sess, q):
    u = sess["user"]
    folder = q.get("folder", "INBOX")
    offset = int(q.get("offset", "0") or 0)
    size = int(q.get("size", "50") or 50)
    stars = _load_stars()
    rows = []
    for name, path, mtime in be._message_files(u, folder):
        r = _row(u, folder, name, path, mtime, stars)
        if r:
            rows.append(r)
    total = len(rows)
    return 200, {
        "list": rows[offset : offset + size],
        "total": total,
        "latestEmail": rows[0] if rows else None,
    }


def op_email(sess, q):
    u = sess["user"]
    folder = q.get("folder", "INBOX")
    uid = q.get("uid", "")
    raw, sub = _raw(u, folder, uid)
    if raw is None:
        return 404, {"message": "Pesan tidak ditemukan."}
    msg = message_from_bytes(raw)
    text, html = be._body(msg)
    disp, addr = parseaddr(be._hdr(msg.get("From")))
    to_disp, to_addr = parseaddr(be._hdr(msg.get("To")))
    path, _ = _msg_path(u, folder, uid)
    mtime = os.path.getmtime(path) if path else time.time()
    return 200, {
        "emailId": uid,
        "uid": uid,
        "subject": be._hdr(msg.get("Subject")) or "(tanpa subjek)",
        "name": disp or addr or "-",
        "sendEmail": addr or disp or "-",
        "sendEmail_raw": be._hdr(msg.get("From")),
        "toEmail": to_addr,
        "recipient": json.dumps(
            [{"address": to_addr, "name": to_disp}], ensure_ascii=False
        ),
        "createTime": _ts(raw, mtime),
        "content": html,
        "text": text,
        "attList": _attachments(msg),
        "unread": 1 if sub == "new" else 0,
        "isStar": _is_star(u, folder, uid),
        "status": 1 if folder != "INBOX" else 0,
        "folder": folder,
    }


def op_attach(sess, q):
    u = sess["user"]
    folder = q.get("folder", "INBOX")
    uid = q.get("uid", "")
    idx = int(q.get("idx", "0") or 0)
    raw, _ = _raw(u, folder, uid)
    if raw is None:
        return 404, {"message": "Pesan tidak ditemukan."}
    msg = message_from_bytes(raw)
    n = 0
    for part in msg.walk():
        if not part.get_filename():
            continue
        if n == idx:
            payload = part.get_payload(decode=True) or b""
            fn = part.get_filename() or "attachment"
            return 200, {
                "__raw__": payload,
                "filename": fn,
                "contentType": part.get_content_type(),
            }
        n += 1
    return 404, {"message": "Lampiran tidak ditemukan."}


def op_search(sess, q):
    u = sess["user"]
    folder = q.get("folder", "INBOX")
    text = (q.get("q") or "").strip().lower()
    kind = q.get("type", "subject")
    stars = _load_stars()
    rows = []
    for name, path, mtime in be._message_files(u, folder):
        if not text:
            continue
        try:
            with open(path, "rb") as f:
                raw = f.read()
            msg = message_from_bytes(raw)
        except Exception:
            continue
        subject = (be._hdr(msg.get("Subject")) or "").lower()
        sender = be._hdr(msg.get("From")).lower()
        body_text, body_html = be._body(msg)
        body = (body_text or body_html).lower()
        hit = {
            "subject": text in subject,
            "content": text in body,
            "sender": text in sender,
            "senderAddress": text in sender,
            "recipientAddress": text in be._hdr(msg.get("To")).lower(),
        }.get(kind, text in subject or text in body or text in sender)
        if hit:
            r = _row(u, folder, name, path, mtime, stars)
            if r:
                rows.append(r)
    return 200, {"list": rows, "total": len(rows)}


def op_send(sess, body):
    u = sess["user"]
    to = (body.get("to") or "").strip()
    if not to:
        return 400, {"message": "Penerima kosong."}
    try:
        res = be.send(
            u,
            sess["password"],
            to,
            body.get("subject") or "(tanpa subjek)",
            body.get("body") or "",
            cc=body.get("cc") or "",
        )
    except PermissionError:
        return 401, {"message": "Sesi kedaluwarsa, login ulang."}
    except Exception as e:
        return 400, {"message": str(e)}
    return 200, {"message": "Pesan terkirim", **res}


def op_star(sess, body):
    u = sess["user"]
    folder = body.get("folder", "INBOX")
    uid = body.get("uid", "")
    star = int(body.get("star") or 0)
    d = _load_stars()
    k = _star_key(u, folder, uid)
    if star:
        d[k] = 1
    else:
        d.pop(k, None)
    _save_stars(d)
    return 200, {"message": "ok", "isStar": star}


def op_read(sess, body):
    u = sess["user"]
    folder = body.get("folder", "INBOX")
    for uid in body.get("uids") or []:
        try:
            be.mark_read(u, folder, uid)
        except Exception:
            pass
    return 200, {"message": "ok"}


def op_delete(sess, body):
    u = sess["user"]
    folder = body.get("folder", "INBOX")
    removed = 0
    for uid in body.get("uids") or []:
        p, _sub = _msg_path(u, folder, uid)
        if p and os.path.isfile(p):
            try:
                os.remove(p)
                removed += 1
            except OSError:
                pass
    return 200, {"message": "ok", "removed": removed}


# ---------------------------------------------------------------- dispatch


def handle(handler, method):
    """Return True kalau request sudah ditangani sebagai API."""
    parsed = urllib.parse.urlparse(handler.path)
    path = parsed.path.rstrip("/") or "/"
    if not path.startswith("/api"):
        return False

    q = dict(urllib.parse.parse_qsl(parsed.query))
    body = {}
    if method == "POST":
        raw = handler._raw_body() if hasattr(handler, "_raw_body") else b""
        text = raw.decode("utf-8", "replace") if raw else ""
        if text.strip().startswith("{"):
            try:
                body = json.loads(text)
            except Exception:
                body = {}
        elif text:
            body = {k: v[0] for k, v in urllib.parse.parse_qs(text).items()}

    sess = ss.get_session(handler._cookie())
    name = path[len("/api") :] or "/"
    ip = (handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or (
        handler.client_address[0] if handler.client_address else "?"
    )

    try:
        if name == "/config" and method == "GET":
            status, payload = op_config()
            handler._json(payload, status)
            return True

        if name == "/register" and method == "POST":
            status, payload = op_register(body, ip)
            if status == 200:
                tok = payload.pop("token")
                cookie = "%s=%s; HttpOnly; SameSite=Lax%s; Path=/; Max-Age=28800" % (
                    ss.COOKIE_NAME,
                    tok,
                    ss.secure_flag(handler.headers),
                )
                handler._json(payload, status, extra_headers=[("Set-Cookie", cookie)])
                return True
            handler._json(payload, status)
            return True

        if name == "/login" and method == "POST":
            status, payload = op_login(body)
            if status == 200:
                tok = payload.pop("token")
                cookie = "%s=%s; HttpOnly; SameSite=Lax%s; Path=/; Max-Age=28800" % (
                    ss.COOKIE_NAME,
                    tok,
                    ss.secure_flag(handler.headers),
                )
                handler._json(payload, status, extra_headers=[("Set-Cookie", cookie)])
                return True
            handler._json(payload, status)
            return True

        if name == "/logout":
            ss.drop_session(handler._cookie())
            cookie = "%s=; Max-Age=0; Path=/" % ss.COOKIE_NAME
            handler._json({"message": "ok"}, 200, extra_headers=[("Set-Cookie", cookie)])
            return True

        if name == "/me" and method == "GET":
            if not sess:
                handler._json({"message": "unauthorized"}, 401)
                return True
            status, payload = op_me(sess)
            handler._json(payload, status)
            return True

        if not sess:
            handler._json({"message": "unauthorized"}, 401)
            return True

        routes = {
            ("/folders", "GET"): lambda: op_folders(sess),
            ("/emails", "GET"): lambda: op_emails(sess, q),
            ("/email", "GET"): lambda: op_email(sess, q),
            ("/search", "GET"): lambda: op_search(sess, q),
            ("/send", "POST"): lambda: op_send(sess, body),
            ("/star", "POST"): lambda: op_star(sess, body),
            ("/read", "POST"): lambda: op_read(sess, body),
            ("/delete", "POST"): lambda: op_delete(sess, body),
        }

        if name == "/attach" and method == "GET":
            status, payload = op_attach(sess, q)
            if status == 200:
                handler._bytes(
                    payload["__raw__"],
                    payload["contentType"],
                    filename=payload["filename"],
                )
            else:
                handler._json(payload, status)
            return True

        fn = routes.get((name, method))
        if not fn:
            handler._json({"message": "not found"}, 404)
            return True
        status, payload = fn()
        handler._json(payload, status)
        return True
    except Exception as e:  # noqa: BLE001
        handler._json({"message": "server error: %s" % e}, 500)
        return True
