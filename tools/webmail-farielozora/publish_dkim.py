#!/usr/bin/env python3
"""
publish_dkim.py — ambil kunci DKIM lokal, publikasikan TXT record ke Cloudflare.

    CF_TOKEN=xxx python3 publish_dkim.py
    CF_TOKEN=xxx python3 publish_dkim.py --dry-run

Membaca /etc/opendkim/keys/<domain>/<selector>.txt (format opendkim-genkey),
menggabungkan baris yang dipotong, lalu upsert TXT
<selector>._domainkey.<domain> supaya Postfix bisa menandatangani dan
penerima bisa memverifikasi.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cf_dns import api  # reuse helper HTTP Cloudflare

KEYDIR = "/etc/opendkim/keys"


def load_txt_record(domain, selector):
    path = os.path.join(KEYDIR, domain, selector + ".txt")
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    # buang komentar setelah ';' di luar tanda kutip
    body = raw.split("-----")[0]
    parts = re.findall(r'"([^"]*)"', body)
    if not parts:
        raise ValueError("tidak bisa parse %s" % path)
    value = "".join(parts).strip()
    value = re.sub(r"\s+", " ", value)
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", default="farielozora.biz.id")
    ap.add_argument("--selector", default="default")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("CF_TOKEN", "").strip()
    email = os.environ.get("CF_EMAIL", "").strip()
    gkey = os.environ.get("CF_GLOBAL_KEY", "").strip()
    if not token and not (email and gkey):
        print("ERROR: set CF_TOKEN, atau CF_EMAIL + CF_GLOBAL_KEY")
        return 2

    def call(method, path, body=None):
        return api(token, method, path, body, email=email, global_key=gkey)

    value = load_txt_record(args.zone, args.selector)
    name = "%s._domainkey.%s" % (args.selector, args.zone)
    print("[i] %s" % name)
    print("[i] panjang value: %d char" % len(value))
    print("[i] head: %s..." % value[:60])

    if args.dry_run:
        print("[dry-run] tidak menulis apa pun")
        return 0

    if token:
        v = call("GET", "/user/tokens/verify")
        if not v.get("success"):
            print("ERROR token ditolak:", json.dumps(v.get("errors")))
            return 3

    z = call("GET", "/zones?name=" + args.zone)
    if not z.get("success") or not z.get("result"):
        print("ERROR zone tidak ketemu:", json.dumps(z.get("errors")))
        return 4
    zone_id = z["result"][0]["id"]

    existing = call("GET", "/zones/%s/dns_records?type=TXT&name=%s" % (zone_id, name))
    rec = {"type": "TXT", "name": name, "content": value, "ttl": 300}

    if existing.get("success") and existing.get("result"):
        old = existing["result"][0]
        r = call("PUT", "/zones/%s/dns_records/%s" % (zone_id, old["id"]), rec)
        action = "update"
    else:
        r = call("POST", "/zones/%s/dns_records" % zone_id, rec)
        action = "create"

    if not r.get("success"):
        print("ERROR %s:" % action, json.dumps(r.get("errors")))
        return 5
    print("[ok] %s TXT %s" % (action, name))

    check = call("GET", "/zones/%s/dns_records?type=TXT&name=%s" % (zone_id, name))
    for row in check.get("result") or []:
        print("  sekarang: %s" % row["content"][:70])
    return 0


if __name__ == "__main__":
    sys.exit(main())
