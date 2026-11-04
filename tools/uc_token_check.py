#!/usr/bin/env python3
"""
uc_token_check.py — validate UpCloud bearer tokens against the live API.

A leaked token is only a finding if it still authenticates. Read-only probe:
GET https://api.upcloud.com/1.3/account  ->  200 (live) / 401 (dead).
No account state is changed.

Input: tokens on argv, or a file with one token per line.
"""
import json, sys, urllib.request, urllib.error

API = "https://api.upcloud.com/1.3/account"
UA = "upcloud-cli-sample/1.0"


def check(tok):
    req = urllib.request.Request(API, headers={
        "Authorization": f"Bearer {tok}",
        "Accept": "application/json",
        "User-Agent": UA,
    })
    try:
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read(4000).decode("utf-8", "ignore")
        try:
            j = json.loads(body)
        except Exception:
            j = {}
        acct = j.get("account", {}) if isinstance(j, dict) else {}
        return {"token": tok, "status": r.status, "live": True,
                "username": acct.get("username"), "credits": acct.get("credits"),
                "country": acct.get("country"), "raw_keys": list(acct)[:12]}
    except urllib.error.HTTPError as e:
        return {"token": tok, "status": e.code, "live": False}
    except Exception as e:
        return {"token": tok, "status": None, "live": False, "error": str(e)}


if __name__ == "__main__":
    args = sys.argv[1:]
    toks = []
    for a in args:
        try:
            toks += [l.strip() for l in open(a) if l.strip()]
        except (OSError, IOError):
            toks.append(a)
    for t in toks:
        r = check(t)
        print(json.dumps(r))
