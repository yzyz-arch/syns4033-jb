#!/usr/bin/env python3
"""
sync_vmailbox.py — generate /etc/postfix/vmailbox dari users.json.

Postfix memakai file ini (texthash) untuk:
  - menolak recipient yang tidak ada di SMTP time (550), bukan bounce
  - membatasi domain yang dilayani (virtual_mailbox_domains)

Jalankan setiap kali user ditambah/dihapus:
    python3 sync_vmailbox.py
Dipanggil otomatis oleh api.py (registrasi) dan manage.py (adduser).
"""

import json
import os
import sys

USERS = os.environ.get("WEBMAIL_USERS", "/var/lib/webmail-farielozora/users.json")
TARGET = os.environ.get("WEBMAIL_VMAILBOX", "/etc/postfix/vmailbox")
DOMAIN = os.environ.get("WEBMAIL_DOMAIN", "farielozora.biz.id")


def main():
    try:
        with open(USERS, "r", encoding="utf-8") as f:
            users = json.load(f)
    except FileNotFoundError:
        users = {}

    lines = []
    for addr in sorted(users.keys()):
        addr = addr.strip().lower()
        if not addr or "@" not in addr:
            continue
        lines.append("%s\tOK" % addr)
    # alamat sistem untuk bounce / postmaster
    for extra in ("postmaster@" + DOMAIN, "abuse@" + DOMAIN, "webmail@" + DOMAIN):
        if extra not in users:
            lines.append("%s\tOK" % extra)

    body = "\n".join(lines) + "\n"
    tmp = TARGET + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, TARGET)
        os.chmod(TARGET, 0o644)
    except OSError as e:
        sys.stderr.write("gagal menulis %s: %s\n" % (TARGET, e))
        return 1
    print("vmailbox: %d entri -> %s" % (len(lines), TARGET))

    # texthash di-cache proses smtpd; reload bikin map dibaca ulang
    try:
        import subprocess

        if os.geteuid() == 0:
            subprocess.run(
                ["postfix", "reload"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
            print("postfix reload ok")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("peringatan: postfix reload gagal: %s\n" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
