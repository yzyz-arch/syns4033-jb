#!/usr/bin/env python3
"""
cf_dns.py — upsert DNS records farielozora.biz.id lewat Cloudflare API v4.
Stdlib only, idempotent (sudah ada = update, belum ada = create).

Usage:
    CF_TOKEN=xxxx python3 cf_dns.py
    CF_TOKEN=xxxx python3 cf_dns.py --zone farielozora.biz.id --ip 85.9.196.242
    CF_TOKEN=xxxx python3 cf_dns.py --dry-run

Token butuh permission:
    Zone -> DNS   -> Edit  (untuk zone farielozora.biz.id)
    Zone -> Zone  -> Read  (untuk lookup zone id)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"


def api(token, method, path, body=None, email=None, global_key=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if global_key and email:
        headers["X-Auth-Email"] = email
        headers["X-Auth-Key"] = global_key
    else:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API + path, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            return {"success": False, "errors": [{"message": str(e)}]}
    except Exception as e:
        return {"success": False, "errors": [{"message": str(e)}]}


def build_records(zone, ip):
    """Record set final untuk webmail + masa depan mail server."""
    return [
        {"type": "A", "name": zone, "content": ip, "ttl": 300, "proxied": False},
        {"type": "A", "name": "mail." + zone, "content": ip, "ttl": 300, "proxied": False},
        {"type": "CNAME", "name": "www." + zone, "content": zone, "ttl": 300, "proxied": False},
        {"type": "MX", "name": zone, "content": "mail." + zone, "priority": 10, "ttl": 300},
        {"type": "TXT", "name": zone, "content": "v=spf1 mx -all", "ttl": 300},
        {"type": "TXT", "name": "_dmarc." + zone,
         "content": "v=DMARC1; p=quarantine; rua=mailto:postmaster@" + zone, "ttl": 300},
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", default="farielozora.biz.id")
    ap.add_argument("--ip", default="85.9.196.242")
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

    v = call("GET", "/user/tokens/verify") if token else {"success": True}
    if not v.get("success"):
        print("ERROR token ditolak Cloudflare:", json.dumps(v.get("errors")))
        print("       buat token baru: My Profile -> API Tokens -> Edit zone DNS")
        print("       permission: Zone.DNS:Edit + Zone.Zone:Read, resource: farielozora.biz.id")
        return 3
    print("[ok] token valid, status:", (v.get("result") or {}).get("status", "global-key"))

    z = call("GET", "/zones?name=" + args.zone)
    if not z.get("success") or not z.get("result"):
        print("ERROR zone tidak ketemu:", json.dumps(z.get("errors")))
        return 4
    zone_id = z["result"][0]["id"]
    print("[ok] zone %s -> %s" % (args.zone, zone_id))

    existing = call("GET", "/zones/%s/dns_records?per_page=200" % zone_id)
    if not existing.get("success"):
        print("ERROR list record:", json.dumps(existing.get("errors")))
        return 5
    by_key = {}
    for r in existing.get("result") or []:
        by_key[(r["type"], r["name"])] = r

    records = build_records(args.zone, args.ip)
    print("\n%-7s %-34s %s" % ("TYPE", "NAME", "ACTION"))
    for rec in records:
        key = (rec["type"], rec["name"])
        if key in by_key:
            old = by_key[key]
            if rec["type"] == "MX" and old.get("content", "").rstrip(".") == rec["content"]:
                if old.get("priority") == rec.get("priority"):
                    print("%-7s %-34s skip (sama)" % key)
                    continue
            if args.dry_run:
                print("%-7s %-34s update (dry-run)" % key)
                continue
            r = call("PUT", "/zones/%s/dns_records/%s" % (zone_id, old["id"]), rec)
            print("%-7s %-34s %s" % (key + ("update -> ok" if r.get("success") else "update GAGAL " + json.dumps(r.get("errors")),)))
        else:
            if args.dry_run:
                print("%-7s %-34s create (dry-run)" % key)
                continue
            r = call("POST", "/zones/%s/dns_records" % zone_id, rec)
            print("%-7s %-34s %s" % (key + ("create -> ok" if r.get("success") else "create GAGAL " + json.dumps(r.get("errors")),)))

    final = call("GET", "/zones/%s/dns_records?per_page=200" % zone_id)
    print("\n=== record sekarang di %s ===" % args.zone)
    for r in sorted(final.get("result") or [], key=lambda x: (x["type"], x["name"])):
        extra = " prio=%s" % r.get("priority") if r["type"] == "MX" else ""
        prox = " proxied" if r.get("proxied") else ""
        print("  %-6s %-38s %-42s%s%s" % (r["type"], r["name"], r["content"], extra, prox))
    return 0


if __name__ == "__main__":
    sys.exit(main())
