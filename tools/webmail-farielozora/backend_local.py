#!/usr/bin/env python3
"""
backend_local.py — self-contained mail store for webmail-farielozora.
Stdlib only. Maildir-style storage under ROOT/<user>/<Folder>/{new,cur,tmp}
plus a JSON user store with PBKDF2 password hashes.

Env:
    WEBMAIL_MAILDIR   default /var/lib/webmail-farielozora/mail
    WEBMAIL_USERS     default /var/lib/webmail-farielozora/users.json
"""

import hashlib
import json
import os
import secrets
import time
import uuid
from email import message_from_bytes
from email.header import decode_header
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr, parsedate_to_datetime

ROOT = os.environ.get("WEBMAIL_MAILDIR", "/var/lib/webmail-farielozora/mail")
USERS = os.environ.get("WEBMAIL_USERS", "/var/lib/webmail-farielozora/users.json")
ITERATIONS = 200_000


# ---------------------------------------------------------------- users


def _load_users():
    try:
        with open(USERS, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_users(users):
    os.makedirs(os.path.dirname(USERS), exist_ok=True)
    tmp = USERS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, sort_keys=True)
    os.replace(tmp, USERS)
    os.chmod(USERS, 0o600)


def _hash_pw(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), ITERATIONS
    ).hex()
    return salt, digest


def add_user(email_addr, password, display=None):
    email_addr = email_addr.strip().lower()
    users = _load_users()
    salt, digest = _hash_pw(password)
    users[email_addr] = {
        "salt": salt,
        "hash": digest,
        "display": display or email_addr.split("@")[0],
        "created": int(time.time()),
    }
    _save_users(users)
    for folder in ("INBOX", "Sent", "Drafts", "Trash"):
        _ensure_folder(email_addr, folder)
    return email_addr


def set_password(email_addr, password):
    users = _load_users()
    email_addr = email_addr.strip().lower()
    if email_addr not in users:
        raise KeyError("user tidak ada: %s" % email_addr)
    salt, digest = _hash_pw(password)
    users[email_addr]["salt"] = salt
    users[email_addr]["hash"] = digest
    _save_users(users)


def verify(email_addr, password):
    users = _load_users()
    u = users.get(email_addr.strip().lower())
    if not u:
        return False
    salt, digest = _hash_pw(password, u["salt"])
    return secrets.compare_digest(digest, u["hash"])


def user_exists(email_addr):
    return email_addr.strip().lower() in _load_users()


def list_users():
    return sorted(_load_users().keys())


# ---------------------------------------------------------------- storage


def _fs(email_addr):
    return email_addr.strip().lower().replace("/", "_").replace("@", "_at_")


def _folder_path(email_addr, folder):
    folder = folder or "INBOX"
    return os.path.join(ROOT, _fs(email_addr), folder)


def _ensure_folder(email_addr, folder):
    base = _folder_path(email_addr, folder)
    for sub in ("new", "cur", "tmp"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    _chown_tree(base)
    return base


# Delivery lewat Postfix pipe berjalan sebagai user `vmail`, jadi direktori
# mailbox harus bisa ditulis user itu. Service webmail tetap jalan sebagai root.
VMAIL_UID = int(os.environ.get("WEBMAIL_VMAIL_UID", "5000"))
VMAIL_GID = int(os.environ.get("WEBMAIL_VMAIL_GID", "5000"))


def _chown_tree(path):
    try:
        st = os.stat(path)
    except OSError:
        return
    if st.st_uid == VMAIL_UID:
        return  # sudah benar, tidak perlu jalan tiap delivery
    try:
        os.chown(path, VMAIL_UID, VMAIL_GID)
    except OSError:
        return
    for root, dirs, files in os.walk(path):
        for d in dirs:
            try:
                os.chown(os.path.join(root, d), VMAIL_UID, VMAIL_GID)
            except OSError:
                pass
        for f in files:
            try:
                os.chown(os.path.join(root, f), VMAIL_UID, VMAIL_GID)
            except OSError:
                pass


def folders(email_addr):
    base = os.path.join(ROOT, _fs(email_addr))
    if not os.path.isdir(base):
        return ["INBOX"]
    names = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    order = {"INBOX": 0, "Sent": 1, "Drafts": 2, "Trash": 3}
    return sorted(names, key=lambda n: (order.get(n, 9), n))


def deliver(email_addr, raw_bytes):
    """Write a raw RFC822 message into <user>/INBOX/new and return uid."""
    email_addr = email_addr.strip().lower()
    if not user_exists(email_addr):
        raise KeyError("tidak ada mailbox: %s" % email_addr)
    base = _ensure_folder(email_addr, "INBOX")
    uid = "%d_%s.eml" % (int(time.time() * 1000), uuid.uuid4().hex[:10])
    tmp = os.path.join(base, "tmp", uid)
    with open(tmp, "wb") as f:
        f.write(raw_bytes)
    os.rename(tmp, os.path.join(base, "new", uid))
    return uid


def _deliver_to(email_addr, folder, raw_bytes):
    base = _ensure_folder(email_addr, folder)
    uid = "%d_%s.eml" % (int(time.time() * 1000), uuid.uuid4().hex[:10])
    tmp = os.path.join(base, "tmp", uid)
    with open(tmp, "wb") as f:
        f.write(raw_bytes)
    os.rename(tmp, os.path.join(base, "new", uid))
    return uid


def _message_files(email_addr, folder):
    base = _folder_path(email_addr, folder)
    out = []
    for sub in ("new", "cur"):
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name.endswith(".eml"):
                path = os.path.join(d, name)
                try:
                    out.append((name, path, os.path.getmtime(path)))
                except OSError:
                    pass
    out.sort(key=lambda t: t[2], reverse=True)
    return out


def _hdr(val):
    if not val:
        return ""
    try:
        parts = []
        for chunk, enc in decode_header(val):
            parts.append(
                chunk.decode(enc or "utf-8", "replace")
                if isinstance(chunk, bytes)
                else chunk
            )
        return "".join(parts)
    except Exception:
        return str(val)


def list_messages(email_addr, folder="INBOX", limit=50):
    msgs = []
    for name, path, mtime in _message_files(email_addr, folder)[:limit]:
        try:
            with open(path, "rb") as f:
                raw = f.read()
            msg = message_from_bytes(raw)
            sender = parseaddr(_hdr(msg.get("From")))
            msgs.append(
                {
                    "uid": name,
                    "from": sender[0] or sender[1] or "-",
                    "subject": _hdr(msg.get("Subject")) or "(tanpa subjek)",
                    "date": _hdr(msg.get("Date")),
                    "_mtime": mtime,
                }
            )
        except Exception:
            continue
    return msgs


def _decode_part(part):
    try:
        raw = part.get_payload(decode=True)
        if raw is None:
            return ""
        return raw.decode(part.get_content_charset() or "utf-8", "replace")
    except Exception:
        return ""


def _body(msg):
    text = htmlp = None
    if msg.is_multipart():
        for p in msg.walk():
            if "attachment" in str(p.get("Content-Disposition", "")):
                continue
            ct = p.get_content_type()
            if ct == "text/plain" and text is None:
                text = _decode_part(p)
            elif ct == "text/html" and htmlp is None:
                htmlp = _decode_part(p)
    else:
        if msg.get_content_type() == "text/html":
            htmlp = _decode_part(msg)
        else:
            text = _decode_part(msg)
    return text or "", htmlp or ""


def get_message(email_addr, folder, uid):
    path = os.path.join(_folder_path(email_addr, folder), "new", uid)
    if not os.path.isfile(path):
        path = os.path.join(_folder_path(email_addr, folder), "cur", uid)
    if not os.path.isfile(path):
        raise FileNotFoundError("pesan tidak ditemukan")
    with open(path, "rb") as f:
        msg = message_from_bytes(f.read())
    text, htmlp = _body(msg)
    return {
        "from": _hdr(msg.get("From")),
        "to": _hdr(msg.get("To")),
        "subject": _hdr(msg.get("Subject")) or "(tanpa subjek)",
        "date": _hdr(msg.get("Date")),
        "text": text,
        "html": htmlp,
    }


def mark_read(email_addr, folder, uid):
    base = _folder_path(email_addr, folder)
    src = os.path.join(base, "new", uid)
    if os.path.isfile(src):
        os.makedirs(os.path.join(base, "cur"), exist_ok=True)
        os.replace(src, os.path.join(base, "cur", uid))


# ---------------------------------------------------------------- send


def send(email_addr, password, to, subject, body, cc=""):
    """Compose the message, submit ke MTA (Postfix) atau deliver lokal.

    WEBMAIL_RELAY (default 127.0.0.1:25) -> kirim lewat Postfix, sehingga
    pesan keluar ikut di-DKIM-sign dan bisa sampai ke internet begitu port
    25 dibuka. Set WEBMAIL_RELAY="" untuk kembali ke mode lokal murni.
    """
    email_addr = email_addr.strip().lower()
    if not verify(email_addr, password):
        raise PermissionError("autentikasi gagal")

    msg = EmailMessage()
    msg["From"] = email_addr
    recipients = [a.strip() for a in (to or "").replace(";", ",").split(",") if a.strip()]
    if not recipients:
        raise ValueError("penerima kosong")
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject or "(tanpa subjek)"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=email_addr.split("@")[-1])
    msg.set_content(body or "")

    raw = msg.as_bytes()
    relay = (os.environ.get("WEBMAIL_RELAY", "127.0.0.1:25") or "").strip()

    if relay:
        import smtplib

        host, _, port = relay.partition(":")
        delivered, refused = [], {}
        try:
            with smtplib.SMTP(host, int(port or 25), timeout=30) as s:
                s.ehlo()
                try:
                    s.starttls()
                    s.ehlo()
                except smtplib.SMTPException:
                    pass
                refused_map = s.send_message(msg, from_addr=email_addr, to_addrs=recipients)
                refused = {}
                for addr, err in (refused_map or {}).items():
                    if isinstance(err, bytes):
                        refused[addr] = err.decode("utf-8", "replace")
                    else:
                        refused[addr] = str(err)
                delivered = [r for r in recipients if r not in refused]
        except smtplib.SMTPRecipientsRefused as e:
            raise RuntimeError(
                "semua penerima ditolak: " + ", ".join(sorted(e.recipients.keys()))
            )
        except smtplib.SMTPServerDisconnected:
            raise RuntimeError("MTA lokal tidak merespons (%s)" % relay)
        except smtplib.SMTPException as e:
            raise RuntimeError("MTA menolak pesan: %s" % e)

        if not delivered:
            raise RuntimeError(
                "semua penerima ditolak MTA: " + ", ".join(sorted(refused.keys()))
            )

        _deliver_to(email_addr, "Sent", raw)
        return {
            "delivered": delivered,
            "missing": sorted(refused.keys()),
            "refused": refused,
            "via": "relay:" + relay,
        }

    delivered, missing = [], []
    for rcpt in recipients:
        if user_exists(rcpt):
            deliver(rcpt, raw)
            delivered.append(rcpt)
        else:
            missing.append(rcpt)

    _deliver_to(email_addr, "Sent", raw)
    return {"delivered": delivered, "missing": missing, "via": "local"}
