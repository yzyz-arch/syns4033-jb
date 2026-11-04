#!/usr/bin/env python3
"""
upcloud_hunter.py — credential-exposure harvester for UpCloud (OSINT).

Why this shape: from a datacenter IP the usual code-search endpoints are shut
(grep.app -> JS challenge, Sourcegraph -> Cloudflare, GitLab/GitHub code-search
-> 401, Google/DDG/Mojeek -> CAPTCHA). Two channels do work unauthenticated:
  * Bing organic HTML search  (dork surface: gists, pastes, leaked .env)
  * api.github.com/search/repositories (repo discovery) + codeload tarballs
    (code content grep without the code-search API)

No API keys required. Rate-limit friendly: sleeps between calls, size caps.

Usage:
  python3 upcloud_hunter.py bing                 # run dork set
  python3 upcloud_hunter.py repos --limit 25     # discover repos
  python3 upcloud_hunter.py scan --limit 25      # discover + grep tarballs
  python3 upcloud_hunter.py all --limit 25
Output: JSON file in --outdir (default ./uc_hunt_out)
"""
import argparse, base64, io, json, os, re, sys, tarfile, time, urllib.parse, urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# ---------------------------------------------------------------- credentials
# UpCloud API auth = HTTP Basic with account API username/password; newer
# accounts also issue API tokens (Authorization: Bearer <token>).
PATTERNS = {
    "env_var_upcloud":   re.compile(r"(?i)\b(UPCLOUD_(?:API_)?(?:KEY|TOKEN|SECRET|PASSWORD|USERNAME|USER|PASS))\b\s*[:=]\s*[\"']?([^\s\"'#,]{4,})"),
    "api_upcloud_url":   re.compile(r"(?i)\b(https?://)([A-Za-z0-9_.\-]{2,}):([^\s@/\"']{4,})@([A-Za-z0-9_.\-]*upcloud[A-Za-z0-9_.\-]*)"),
    "bearer_upcloud":    re.compile(r"(?i)(?:bearer|token)\s*[:=]?\s*[\"'](uc[a-z0-9_\-]{20,})[\"']"),
    "basic_auth_hdr":    re.compile(r"(?i)authorization\s*[:=]\s*[\"']?basic\s+([A-Za-z0-9+/=]{16,})"),
    "generic_secret":    re.compile(r"(?i)\b(?:api[_-]?key|apikey|secret|password|passwd|pwd|token)\b\s*[:=]\s*[\"']([A-Za-z0-9_\-\./+=]{12,})[\"']"),
    "private_key":       re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "aws_key":           re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
# generic hits only count as noise unless the file also mentions upcloud
CONTEXT = re.compile(r"(?i)upcloud")

SCAN_EXT = {".env", ".tf", ".tfvars", ".yml", ".yaml", ".json", ".py", ".sh", ".cfg",
            ".ini", ".conf", ".txt", ".md", ".js", ".ts", ".go", ".rb", ".php", ".properties"}
MAX_FILE = 512 * 1024
MAX_REPO_BYTES = 40 * 1024 * 1024

DORKS = [
    '"UPCLOUD_API_KEY"',
    '"UPCLOUD_PASSWORD" "UPCLOUD_USERNAME"',
    'site:gist.github.com upcloud password',
    'site:gist.github.com "upcloud" "api"',
    '"api.upcloud.com" "Authorization: Basic"',
    '"upcloud" "password" filetype:env',
    'site:pastebin.com upcloud',
    '"upcloud" "@api.upcloud.com" password',
    '"UPCLOUD_TOKEN"',
    '"upcloud" terraform "password" "username"',
]


def _get(url, timeout=25, accept=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        **({"Accept": accept} if accept else {}),
    })
    return urllib.request.urlopen(req, timeout=timeout).read()


def _decode_bing(url):
    """Bing wraps results: /ck/a?...&u=a1<base64url>"""
    m = re.search(r"[?&]u=a1([A-Za-z0-9_\-]+)", url)
    if not m:
        return url
    s = m.group(1).replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        return base64.b64decode(s).decode("utf-8", "ignore")
    except Exception:
        return url


def bing(q, pages=2):
    """Bing organic scraping. Works from datacenter IPs where Google/DDG block."""
    hits = []
    for p in range(pages):
        first = p * 10 + 1
        u = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": q, "first": first, "count": 30})
        try:
            html = _get(u, accept="text/html").decode("utf-8", "ignore")
        except Exception as e:
            print(f"  [!] bing error {q}: {e}", file=sys.stderr)
            break
        for b in re.findall(r'<li class="b_algo".*?</li>', html, re.S):
            m = re.search(r'<h2>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
            if not m:
                continue
            link = _decode_bing(m.group(1))
            title = re.sub(r"<[^>]+>", "", m.group(2))
            snip = re.search(r"<p[^>]*>(.*?)</p>", b, re.S)
            snip = re.sub(r"<[^>]+>", "", snip.group(1)) if snip else ""
            if "bing.com/ck/a" in link:
                continue
            hits.append({"dork": q, "title": title.strip(), "url": link,
                         "snippet": re.sub(r"\s+", " ", snip).strip()[:300]})
        time.sleep(1.2)
    return hits


def gh_repos(queries, limit=60):
    seen, repos = set(), []
    for q in queries:
        u = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
            {"q": q, "per_page": 50, "sort": "updated"})
        try:
            data = json.loads(_get(u, accept="application/vnd.github+json"))
        except Exception as e:
            print(f"  [!] repo search {q}: {e}", file=sys.stderr)
            continue
        for it in data.get("items", []):
            fn = it["full_name"]
            if fn in seen or it.get("fork"):
                continue
            seen.add(fn)
            repos.append({"repo": fn, "size_kb": it["size"], "pushed": it["pushed_at"],
                          "desc": (it.get("description") or "")[:160],
                          "default_branch": it.get("default_branch", "main")})
            if len(repos) >= limit:
                return repos
        time.sleep(2.2)
    return repos


def _scan_text(text, where):
    found = []
    ctx = bool(CONTEXT.search(text))
    for name, rx in PATTERNS.items():
        for m in rx.finditer(text):
            if name == "generic_secret" and not ctx:
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            line = text.splitlines()[line_no - 1].strip() if line_no - 1 < len(text.splitlines()) else ""
            if name == "generic_secret" and "upcloud" not in line.lower() and not ctx:
                continue
            found.append({"pattern": name, "file": where, "line": line_no,
                          "match": m.group(0)[:200]})
            if len(found) > 60:
                return found
    return found


def scan_repo(repo, branch="main"):
    url = f"https://codeload.github.com/{repo}/tar.gz/refs/heads/{branch}"
    try:
        blob = _get(url, timeout=90, accept="application/gzip")
    except Exception as e:
        return [], f"download failed: {e}"
    if len(blob) > MAX_REPO_BYTES:
        return [], f"too large ({len(blob)//1024}kb)"
    findings = []
    try:
        tf = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
    except Exception as e:
        return [], f"untar failed: {e}"
    for mem in tf:
        if not mem.isfile() or mem.size > MAX_FILE:
            continue
        ext = os.path.splitext(mem.name)[1].lower()
        base = os.path.basename(mem.name).lower()
        if ext not in SCAN_EXT and not base.startswith(".env"):
            continue
        try:
            text = tf.extractfile(mem).read().decode("utf-8", "ignore")
        except Exception:
            continue
        findings.extend(_scan_text(text, mem.name))
    return findings, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["bing", "repos", "scan", "all"])
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--outdir", default="uc_hunt_out")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    report = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    if a.mode in ("bing", "all"):
        print("[*] bing dork sweep")
        allh, seend = [], set()
        for d in DORKS:
            print(f"  -> {d}")
            for h in bing(d):
                if h["url"] in seend:
                    continue
                seend.add(h["url"])
                allh.append(h)
        report["dork_hits"] = allh
        print(f"[+] {len(allh)} unique URLs from dorks")
        json.dump(report, open(f"{a.outdir}/dorks.json", "w"), indent=1)

    if a.mode in ("repos", "scan", "all"):
        queries = ["upcloud", "upcloud api", "upcloud terraform", "upcloud deploy script",
                   "upcloud ansible", "upcloud backup", "upcloud in:readme api"]
        print("[*] github repo discovery")
        repos = gh_repos(queries, a.limit)
        report["repos"] = repos
        print(f"[+] {len(repos)} repos")

    if a.mode in ("scan", "all"):
        print("[*] tarball grep")
        hits = []
        for r in report.get("repos", []):
            print(f"  -> {r['repo']} ({r['size_kb']}kb)")
            f, err = scan_repo(r["repo"], r["default_branch"])
            if err:
                print(f"     [!] {err}")
            for x in f:
                x["repo"] = r["repo"]
                hits.append(x)
                print(f"     [!] {x['pattern']} {x['repo']}:{x['file']}:{x['line']}")
        report["code_findings"] = hits
        print(f"[+] {len(hits)} raw findings (review before believing)")

    json.dump(report, open(f"{a.outdir}/report.json", "w"), indent=1)
    print(f"[=] wrote {a.outdir}/report.json")


if __name__ == "__main__":
    main()
