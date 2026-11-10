#!/usr/bin/env python3
"""
setup_postfix_transport.py — tambah transport `webmail-deliver` ke master.cf
secara idempotent. Aman dijalankan berulang.
"""

import re
import sys

MASTER = "/etc/postfix/master.cf"
BLOCK = """
# --- webmail-farielozora: kirim pesan ke maildir lewat script sendiri ---
webmail-deliver unix  -       n       n       -       -       pipe
  flags=DRhu user=root argv=/usr/local/bin/webmail-deliver ${recipient}
"""


def main():
    with open(MASTER, "r", encoding="utf-8") as f:
        src = f.read()

    if re.search(r"^webmail-deliver\s", src, re.M):
        print("transport webmail-deliver sudah ada, skip")
        return 0

    if not src.endswith("\n"):
        src += "\n"
    src += BLOCK
    with open(MASTER, "w", encoding="utf-8") as f:
        f.write(src)
    print("transport webmail-deliver ditambahkan ke %s" % MASTER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
