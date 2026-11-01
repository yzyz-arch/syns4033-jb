"""GitHub / code-host intelligence: org and user footprint, commit-author emails,
repo secret grep, and an offline local-directory secret scanner.

Uses the public REST API; set GITHUB_TOKEN / GH_TOKEN to lift the 60 req/h limit.
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import os
import re
from pathlib import Path

from .http import session

API = "https://api.github.com"


def _hdrs() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    tok = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _get(path: str, params: dict | None = None, timeout: int = 20):
    s = session()
    s.headers.update(_hdrs())
    try:
        r = s.get(f"{API}{path}", params=params or {}, timeout=timeout)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            return {"_error": "rate-limited", "_reset": r.headers.get("X-RateLimit-Reset"),
                    "_hint": "set GITHUB_TOKEN to raise the limit"}
        if r.status_code == 404:
            return {"_error": "not-found"}
        if r.status_code >= 400:
            return {"_error": f"http-{r.status_code}"}
        return r.json()
    except Exception as e:
        return {"_error": str(e)[:120]}


def user_profile(login: str) -> dict:
    u = _get(f"/users/{login}")
    if "_error" in u:
        return {"login": login, **u}
    return {
        "login": u.get("login"), "name": u.get("name"), "company": u.get("company"),
        "blog": u.get("blog"), "location": u.get("location"), "email": u.get("email"),
        "bio": u.get("bio"), "twitter": u.get("twitter_username"),
        "public_repos": u.get("public_repos"), "public_gists": u.get("public_gists"),
        "followers": u.get("followers"), "following": u.get("following"),
        "created_at": u.get("created_at"), "updated_at": u.get("updated_at"),
        "type": u.get("type"), "avatar": u.get("avatar_url"),
    }


def repos(login: str, limit: int = 100) -> list[dict]:
    r = _get(f"/users/{login}/repos", {"per_page": min(100, limit), "sort": "updated"})
    if not isinstance(r, list):
        return []
    return [{"name": x.get("name"), "full_name": x.get("full_name"),
             "description": x.get("description"), "language": x.get("language"),
             "stars": x.get("stargazers_count"), "forks": x.get("forks_count"),
             "private": x.get("private"), "fork": x.get("fork"),
             "updated": x.get("updated_at"), "url": x.get("html_url"),
             "size_kb": x.get("size")} for x in r]


def org_members(org: str, limit: int = 100) -> list[dict]:
    r = _get(f"/orgs/{org}/public_members", {"per_page": min(100, limit)})
    if not isinstance(r, list):
        return []
    return [{"login": x.get("login"), "url": x.get("html_url")} for x in r]


def commit_emails(login: str, repo: str, limit: int = 100) -> list[str]:
    r = _get(f"/repos/{login}/{repo}/commits", {"per_page": min(100, limit)})
    if not isinstance(r, list):
        return []
    out = set()
    for c in r:
        for key in ("author", "committer"):
            e = ((c.get("commit") or {}).get(key) or {}).get("email")
            if e and "users.noreply.github.com" not in e:
                out.add(e)
        gh = (c.get("author") or {}).get("login")
        if gh:
            out.add(f"{gh} (github-login)")
    return sorted(out)


SECRET_RE = [
    ("aws_key", r"\b(AKIA|ASIA)[0-9A-Z]{12,20}\b"),
    ("private_key", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ("generic_secret", r"(?i)(?:api[_-]?key|secret|passwd|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
    ("db_uri", r"(?i)(?:postgres|mysql|mongodb(?:\+srv)?|redis)://[^\s'\"<>]{10,}"),
    ("slack", r"xox[abprs]-[0-9A-Za-z\-]{10,}"),
    ("sendgrid", r"SG\.[0-9A-Za-z\-_]{22}\.[0-9A-Za-z\-_]{43}"),
    ("github_pat", r"gh[pousr]_[0-9A-Za-z]{36,255}"),
    ("stripe", r"\bsk_(?:live|test)_[0-9a-zA-Z]{20,}"),
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
]


def repo_secret_scan(owner: str, repo: str) -> dict:
    """Fetch the repo tree and grep text files for secret patterns (public repos)."""
    info = _get(f"/repos/{owner}/{repo}")
    if "_error" in info:
        return {"repo": f"{owner}/{repo}", "error": info["_error"]}
    branch = info.get("default_branch") or "main"
    tree = _get(f"/repos/{owner}/{repo}/git/trees/{branch}", {"recursive": "1"})
    if "_error" in tree or not isinstance(tree, dict):
        return {"repo": f"{owner}/{repo}", "error": "tree unavailable"}
    files = [t for t in tree.get("tree", [])
             if t.get("type") == "blob" and re.search(
                 r"\.(env|json|ya?ml|js|ts|py|php|rb|go|java|properties|conf|ini|txt|md|sh|sql)$",
                 t.get("path", ""), re.I)]
    files = files[:80]
    hits = []

    def scan_file(node):
        path = node["path"]
        raw = _get(f"/repos/{owner}/{repo}/contents/{path}")
        if not isinstance(raw, dict) or raw.get("encoding") != "base64":
            return []
        try:
            text = base64.b64decode(raw.get("content", "")).decode("utf-8", "replace")
        except Exception:
            return []
        out = []
        for name, pat in SECRET_RE:
            m = re.search(pat, text)
            if m:
                val = m.group(0)
                out.append({"file": path, "type": name,
                            "match": val[:12] + "..." + val[-4:] if len(val) > 20 else val})
        return out

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(scan_file, files):
            hits.extend(res)
    return {"repo": f"{owner}/{repo}", "branch": branch, "files_scanned": len(files),
            "findings": hits[:100], "finding_count": len(hits)}


def footprint(login: str, deep: bool = False) -> dict:
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        f_u = ex.submit(user_profile, login)
        f_r = ex.submit(repos, login, 100)
        f_m = ex.submit(org_members, login, 100)
        prof, rp, mem = f_u.result(), f_r.result(), f_m.result()
    out = {"login": login, "profile": prof, "repos": rp, "repo_count": len(rp),
           "org_members": mem}
    if deep and rp:
        emails = set()
        with cf.ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(commit_emails, login, r["name"], 100) for r in rp[:10]]
            for f in futs:
                emails.update(f.result())
        out["commit_emails"] = sorted(emails)
    return out


# ---------------- offline: local directory scan ----------------

SCAN_EXT = re.compile(r"\.(env|env\.local|json|ya?ml|toml|ini|conf|cfg|properties|"
                      r"js|ts|jsx|tsx|py|rb|php|go|java|kt|sh|bash|zsh|ps1|sql|tf|"
                      r"md|txt|pem|key|p12|jks|dockerfile)$", re.I)
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             ".next", "target", "vendor", "site-packages"}
MAX_FILE = 2_000_000


def scan_local(root: str, limit_files: int = 5000) -> dict:
    rootp = Path(root).expanduser().resolve()
    findings: list[dict] = []
    scanned = 0
    for p in rootp.rglob("*"):
        if scanned >= limit_files:
            break
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if not SCAN_EXT.search(p.name) and not p.name.lower().startswith("dockerfile"):
            continue
        try:
            if p.stat().st_size > MAX_FILE:
                continue
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        scanned += 1
        for name, pat in SECRET_RE:
            for m in re.finditer(pat, text):
                line = text[:m.start()].count("\n") + 1
                val = m.group(0)
                findings.append({
                    "file": str(p.relative_to(rootp)), "line": line, "type": name,
                    "value": val if len(val) <= 80 else val[:77] + "...",
                })
                break  # one hit per pattern per file keeps output readable
    seen = set()
    uniq = []
    for f in findings:
        k = (f["file"], f["type"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return {"root": str(rootp), "files_scanned": scanned,
            "finding_count": len(uniq), "findings": uniq[:500]}
