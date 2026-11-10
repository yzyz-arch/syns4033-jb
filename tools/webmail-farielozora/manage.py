#!/usr/bin/env python3
"""
manage.py — CLI untuk store webmail-farielozora.

  python3 manage.py adduser  farielozora@farielozora.biz.id 'PASSWORD'
  python3 manage.py passwd   farielozora@farielozora.biz.id 'NEWPASS'
  python3 manage.py list
  python3 manage.py seed     farielozora@farielozora.biz.id
"""

import sys
import time
import uuid
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import backend_local as be


def cmd_adduser(argv):
    if len(argv) < 2:
        print("usage: adduser <email> <password> [display]")
        return 2
    email_addr = argv[0]
    if be.user_exists(email_addr):
        print("sudah ada: %s (pakai 'passwd' untuk ganti password)" % email_addr)
        return 1
    be.add_user(email_addr, argv[1], argv[2] if len(argv) > 2 else None)
    print("user dibuat: %s" % email_addr)
    return 0


def cmd_passwd(argv):
    if len(argv) < 2:
        print("usage: passwd <email> <newpassword>")
        return 2
    be.set_password(argv[0], argv[1])
    print("password diganti: %s" % argv[0])
    return 0


def cmd_list(argv):
    users = be.list_users()
    print("users (%d):" % len(users))
    for u in users:
        print("  -", u, "| folders:", ", ".join(be.folders(u)))
    return 0


def cmd_seed(argv):
    if not argv:
        print("usage: seed <email>")
        return 2
    target = argv[0]
    msg = EmailMessage()
    msg["From"] = "webmail@%s" % target.split("@")[-1]
    msg["To"] = target
    msg["Subject"] = "Selamat datang di webmail farielozora.biz.id"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=target.split("@")[-1])
    msg.set_content(
        "Halo!\n\n"
        "Mailbox %s sudah aktif dan webmail sudah berjalan.\n\n"
        "Kalau pesan ini muncul di Kotak Masuk, artinya login + IMAP store\n"
        "berfungsi penuh. Coba balas pesan ini untuk menguji pengiriman.\n\n"
        "Dikirim: %s\n" % (target, time.strftime("%Y-%m-%d %H:%M:%S"))
    )
    be.deliver(target, msg.as_bytes())
    print("seeded 1 pesan ke INBOX %s" % target)
    return 0


def main():
    cmds = {
        "adduser": cmd_adduser,
        "passwd": cmd_passwd,
        "list": cmd_list,
        "seed": cmd_seed,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        return 2
    return cmds[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
