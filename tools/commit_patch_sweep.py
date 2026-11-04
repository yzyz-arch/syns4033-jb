#!/usr/bin/env python3
"""
commit_patch_sweep.py — pull commit diffs as .patch and grep them for secrets.

GitHub's .patch endpoint on github.com serves a public commit diff with NO API
authentication and NO rate-limit counter (unlike api.github.com). Commit search
(api.github.com/search/commits, 10/min unauth) gives the (repo, sha) pairs;
this sweeps their diffs and mines the +/- lines.

Highest-value targets: commits whose message says a key was "removed" - the
deletion hunk still contains the secret.

Usage: python3 commit_patch_sweep.py --report grep_hunt_out/report.json --out patches_out
"""
import argparse, json, os, re, sys, time, urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

PATTERNS = {
    "upcloud_token_ucat": re.compile(r"\bucat_[A-Za-z0-9_\-]{10,}"),
    "upcloud_env":        re.compile(r"(?i)\b(UPCLOUD_[A-Z_]*(?:KEY|TOKEN|SECRET|PASS|PASSWORD|USER|USERNAME))\s*[=:]\s*[\"']?([^\s\"'#,]{6,})"),
    "upcloud_basic_url":  re.compile(r"(?i)https?://([A-Za-z0-9_.\-]{2,}):([^\s@/\"']{6,})@([A-Za-z0-9_.\-]*upcloud[A-Za-z0-9_.\-]*)"),
    "basic_auth_hdr":     re.compile(r"(?i)authorization[^\n]{0,20}basic\s+([A-Za-z0-9+/=]{20,})"),
    "aws_key":            re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key":        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "generic_pw":         re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|secret|token)\b\s*[=:]\s*[\"']([A-Za-z0-9_\-\./+=]{12,})[\"']"),
}
PLACE = re.compile(r"(?i)(your|xxx|example|placeholder|changeme|dummy|redacted|\$\{|\{\{|<|\.\.\.|"
                   r"test|foo|bar|sample|1234|abcdef|unused|secret_here|token_here|%s|sanitiz)")


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read()


def patch_for(repo, sha):
    try:
        return get(f"https://github.com/{repo}/commit/{sha}.patch").decode("utf-8", "ignore")
    except Exception as e:
        return None


def scan(text):
    out = []
    for ln, line in enumerate(text.splitlines(), 1):
        if not (line.startswith("+") or line.startswith("-")):
            continue
        if line.startswith(("+++", "---")):
            continue
        ctx = "upcloud" in line.lower()
        for name, rx in PATTERNS.items():
            for m in rx.finditer(line):
                if name == "generic_pw" and not ctx:
                    continue
                val = m.group(0)
                out.append({"pattern": name, "line_no": ln, "line": line[:300],
                            "match": val[:200],
                            "placeholder": bool(PLACE.search(val)),
                            "context_upcloud": ctx})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", default="patches_out")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--delay", type=float, default=0.7)
    ap.add_argument("--priority-first", action="store_true",
                    help="process commits mentioning removal/leak/rotate first")
    a = ap.parse_args()
    rep = json.load(open(a.report))
    commits = rep.get("commits", [])
    if a.priority_first:
        hot = re.compile(r"(?i)(remov|delet|leak|accident|revoke|rotat|scrub|secret|credential|expose)")
        commits = [c for c in commits if hot.search(c["msg"])] + \
                  [c for c in commits if not hot.search(c["msg"])]
    commits = commits[:a.limit]
    os.makedirs(a.out, exist_ok=True)
    findings, scanned, failed = [], 0, 0
    for i, c in enumerate(commits, 1):
        p = patch_for(c["repo"], c["sha"])
        if p is None:
            failed += 1
            continue
        scanned += 1
        open(f"{a.out}/{c['repo'].replace('/','_')}_{c['sha'][:8]}.patch", "w").write(p)
        hits = scan(p)
        if hits:
            for h in hits:
                h.update(repo=c["repo"], sha=c["sha"], msg=c["msg"], date=c["date"], url=c["url"])
            findings.extend(hits)
            print(f"[{i}/{len(commits)}] {c['repo']} {c['sha'][:8]} -> {len(hits)} hits")
            for h in hits[:6]:
                tag = "PLACEHOLDER" if h["placeholder"] else "CANDIDATE"
                print(f"    {tag:11} {h['pattern']:18} {h['line'][:150]}")
        if i % 25 == 0:
            print(f"   ...{i} scanned, {len(findings)} findings")
        time.sleep(a.delay)
    json.dump({"scanned": scanned, "failed": failed, "findings": findings},
              open(f"{a.out}/findings.json", "w"), indent=1)
    cand = [f for f in findings if not f["placeholder"]]
    print(f"\n[=] patches={scanned} failed={failed} raw_findings={len(findings)} candidates={len(cand)}")


if __name__ == "__main__":
    main()
