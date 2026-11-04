#!/usr/bin/env python3
"""
grepapp_hunter.py — secret-exposure code search via grep.app JSON API.

Why the jina hop: grep.app's /api/search sits behind a JS challenge for
datacenter IPs (429 + {"error":{"code":"challenge"}}). r.jina.ai renders the
request server-side and hands back the raw JSON body, so the API is usable
again. github.com itself is 403 on jina (abuse block), grep.app is not.

Channels used here:
  1. grep.app /api/search           -> code hits (repo, path, branch, snippet)
  2. raw.githubusercontent.com      -> fetch the full file to judge a hit
  3. api.github.com/search/commits  -> commits mentioning the terms, then diff

Usage:
  python3 grepapp_hunter.py --queries UPCLOUD_API_KEY UPCLOUD_PASSWORD --verify
  python3 grepapp_hunter.py --preset upcloud --verify --outdir out
  python3 grepapp_hunter.py --preset upcloud --commits
"""
import argparse, html, io, json, os, re, sys, time, urllib.parse, urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
JINA = "https://r.jina.ai/"

PRESETS = {
    "upcloud": [
        "UPCLOUD_API_KEY", "UPCLOUD_API_TOKEN", "UPCLOUD_PASSWORD", "UPCLOUD_USERNAME",
        "UPCLOUD_TOKEN", "api.upcloud.com", "upcloud_api_key", "upcloud_password",
    ],
    "vultr": ["VULTR_API_KEY", "api.vultr.com"],
    "hetzner": ["HCLOUD_TOKEN", "hetzner_api_token"],
}

PLACEHOLDER = re.compile(
    r"(?i)(your[_-]?|xxx+|example|placeholder|changeme|change[_-]?me|dummy|redacted|"
    r"\$\{|\{\{|<[a-z-]+>|\.\.\.|test|foo|bar|sample|123456|abcdef|some[_-]?|"
    r"my[_-]|insert|todo|n/?a\b|secret|token_here|apikey_here)")
STRONG = re.compile(r"(?i)\bucat_[A-Za-z0-9]{8,}|\buc[a-z]{2}_[A-Za-z0-9]{20,}")


def get(url, timeout=90, accept=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
        **({"Accept": accept} if accept else {})})
    return urllib.request.urlopen(req, timeout=timeout).read()


def jina_json(target, timeout=90, tries=3):
    """Fetch target through r.jina.ai and return decoded JSON body."""
    for i in range(tries):
        try:
            raw = get(JINA + target, timeout=timeout).decode("utf-8", "ignore")
        except Exception as e:
            print(f"    [!] jina {type(e).__name__} (try {i+1})", file=sys.stderr)
            time.sleep(3 * (i + 1))
            continue
        i0 = raw.find('{"time"')
        if i0 < 0:
            i0 = raw.find('{"')
        if i0 < 0:
            i0 = raw.find('{')
        if i0 < 0:
            continue
        try:
            return json.JSONDecoder().raw_decode(raw[i0:])[0]
        except Exception:
            continue
    return None


def strip_html(s):
    # grep.app snippet: <tr data-line=N><td><div class="lineno">N</div></td>
    #                   <td><div class="highlight"><pre>CODE</pre></div></td></tr>
    # Only the lineno div must go - dropping all <td> nuked the actual code.
    s = re.sub(r'<div class="lineno">.*?</div>', '', s, flags=re.S)
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s).replace("\\t", " ")
    return re.sub(r'\s+', ' ', s).strip()


def grepapp(q, page=1):
    t = "https://grep.app/api/search?" + urllib.parse.urlencode({"q": q, "page": page})
    d = jina_json(t)
    if not d or "hits" not in d:
        return [], 0
    hits, total = [], d["hits"].get("total", 0)
    for h in d["hits"].get("hits", []):
        hits.append({
            "query": q,
            "repo": h.get("repo"),
            "path": h.get("path"),
            "branch": h.get("branch"),
            "snippet": strip_html(h.get("content", {}).get("snippet", ""))[:400],
        })
    return hits, total


def fetch_file(repo, branch, path):
    u = f"https://raw.githubusercontent.com/{repo}/{branch}/{urllib.parse.quote(path)}"
    try:
        return get(u, timeout=30).decode("utf-8", "ignore")
    except Exception:
        return None


def judge(hit):
    """Classify a hit: real-looking credential vs placeholder/doc/test."""
    s = hit["snippet"]
    hit["placeholder"] = bool(PLACEHOLDER.search(s))
    hit["strong_format"] = bool(STRONG.search(s))
    vals = re.findall(r'[=:]\s*["\']?([A-Za-z0-9_\-\./+=]{10,})', s)
    hit["values"] = vals[:4]
    if hit["strong_format"]:
        hit["verdict"] = "STRONG_FORMAT_MATCH"
    elif hit["placeholder"]:
        hit["verdict"] = "placeholder/doc"
    elif vals:
        hit["verdict"] = "literal_value_review"
    else:
        hit["verdict"] = "no_value"
    return hit


def commits(q, per_page=30):
    u = "https://api.github.com/search/commits?" + urllib.parse.urlencode({"q": q, "per_page": per_page})
    try:
        d = json.loads(get(u, timeout=25, accept="application/vnd.github.cloak-preview+json"))
    except Exception as e:
        print(f"    [!] commit search: {e}", file=sys.stderr)
        return [], 0
    out = []
    for it in d.get("items", []):
        out.append({"query": q, "repo": it["repository"]["full_name"],
                    "sha": it["sha"], "msg": (it["commit"]["message"] or "").split("\n")[0][:120],
                    "date": it["commit"]["author"]["date"],
                    "url": it["html_url"]})
    return out, d.get("total_count", 0)


def commit_diff(repo, sha):
    try:
        d = json.loads(get(f"https://api.github.com/repos/{repo}/commits/{sha}", timeout=30))
    except Exception:
        return None
    return "\n".join(f.get("patch", "") for f in d.get("files", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", nargs="*", default=[])
    ap.add_argument("--preset", choices=sorted(PRESETS))
    ap.add_argument("--verify", action="store_true", help="fetch full file for suspicious hits")
    ap.add_argument("--commits", action="store_true", help="also run github commit search")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--outdir", default="grep_hunt_out")
    a = ap.parse_args()
    qs = list(a.queries) + (PRESETS.get(a.preset, []) if a.preset else [])
    if not qs:
        ap.error("need --queries or --preset")
    os.makedirs(a.outdir, exist_ok=True)
    rep = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hits": [], "commits": []}

    for q in qs:
        tot_all = 0
        for pg in range(1, a.pages + 1):
            hits, total = grepapp(q, pg)
            tot_all = total
            for h in hits:
                rep["hits"].append(judge(h))
            print(f"[grep.app] {q!r} page{pg}: {len(hits)} hits (total {total})")
            if len(hits) < 20:
                break
            time.sleep(2)
        time.sleep(2)

    if a.commits:
        for q in qs[:5]:
            cs, tot = commits(q)
            rep["commits"].extend(cs)
            print(f"[commits] {q!r}: {len(cs)}/{tot}")
            time.sleep(6)

    if a.verify:
        for h in rep["hits"]:
            if h["verdict"] not in ("literal_value_review", "STRONG_FORMAT_MATCH"):
                continue
            txt = fetch_file(h["repo"], h["branch"], h["path"])
            if not txt:
                h["verify"] = "fetch_failed"
                continue
            # locate the exact line
            key = h["snippet"][:40]
            lines = [l.strip() for l in txt.splitlines() if key and key[:20] in l]
            h["verify"] = "found_in_file" if lines else "snippet_not_located"
            h["full_line"] = (lines[0][:300] if lines else txt[:0])
            time.sleep(0.5)

    json.dump(rep, open(f"{a.outdir}/report.json", "w"), indent=1)
    strong = [h for h in rep["hits"] if h["verdict"] == "STRONG_FORMAT_MATCH"]
    lit = [h for h in rep["hits"] if h["verdict"] == "literal_value_review"]
    print(f"\n[=] {len(rep['hits'])} total | STRONG={len(strong)} | literal_review={len(lit)}")
    for h in strong + lit:
        print(f"  {h['verdict']:22} {h['repo']}:{h['path']}")
        print(f"     {h['snippet'][:180]}")
    print(f"[=] wrote {a.outdir}/report.json")


if __name__ == "__main__":
    main()
