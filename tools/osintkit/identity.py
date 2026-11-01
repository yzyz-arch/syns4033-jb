"""Identity OSINT: username enumeration, email account discovery, gravatar, breach lookup."""
from __future__ import annotations
import concurrent.futures as cf
import hashlib
from urllib.parse import quote

from .http import get_json, session

# username -> URL template; presence heuristic keyed by allow/deny markers
PLATFORMS = {
    "github": "https://github.com/{u}",
    "gitlab": "https://gitlab.com/{u}",
    "twitter": "https://twitter.com/{u}",
    "instagram": "https://www.instagram.com/{u}/",
    "reddit": "https://www.reddit.com/user/{u}",
    "pinterest": "https://www.pinterest.com/{u}/",
    "tiktok": "https://www.tiktok.com/@{u}",
    "medium": "https://medium.com/@{u}",
    "devto": "https://dev.to/{u}",
    "keybase": "https://keybase.io/{u}",
    "aboutme": "https://about.me/{u}",
    "behance": "https://www.behance.net/{u}",
    "dribbble": "https://dribbble.com/{u}",
    "vimeo": "https://vimeo.com/{u}",
    "soundcloud": "https://soundcloud.com/{u}",
    "twitch": "https://www.twitch.tv/{u}",
    "steam": "https://steamcommunity.com/id/{u}",
    "telegram": "https://t.me/{u}",
    "youtube": "https://www.youtube.com/@{u}",
    "hackernews": "https://news.ycombinator.com/user?id={u}",
    "stackoverflow": "https://stackoverflow.com/users/filter?search={u}",
    "codepen": "https://codepen.io/{u}",
    "replit": "https://replit.com/@{u}",
    "bitbucket": "https://bitbucket.org/{u}/",
    "npm": "https://www.npmjs.com/~{u}",
    "pypi": "https://pypi.org/user/{u}/",
    "patreon": "https://www.patreon.com/{u}",
    "flickr": "https://www.flickr.com/people/{u}",
    "mastodon.social": "https://mastodon.social/@{u}",
    "linktr.ee": "https://linktr.ee/{u}",
    "gravatar-profile": "https://gravatar.com/{u}",
}

# some sites return 200 even for missing users -> explicit miss markers
MISS_MARKERS = [
    "page not found", "not found", "doesn't exist", "does not exist",
    "sorry, nobody on reddit", "no such user", "user not found",
    "this account doesn", "couldn't find", "could not find",
    "user does not exist", "account not found", "profile not found",
    "this page isn't available", "nothing to see here", "whoops",
    "create your account", "sign up", "join now", "are you sure",
    "we couldn't find", "no longer available", "hasn't posted",
]

# platforms whose "missing" page still returns 200 — require an explicit positive marker instead
REQUIRE_POSITIVE = {
    "twitter": 'data-testid="primarycolumn"',
    "twitch": "channel-info",
    "steam": "actual_persona_name",
    "patreon": "patreon.com",
    "pinterest": "pinterestapp:pinboard",
}


def _check_username(s, name: str, url: str) -> dict:
    try:
        r = s.get(url, timeout=12, allow_redirects=True)
        body = r.text[:60000].lower()
        exists = None
        if r.status_code == 200:
            if any(m in body for m in MISS_MARKERS):
                exists = False
            elif name in REQUIRE_POSITIVE:
                exists = REQUIRE_POSITIVE[name].lower() in body
            else:
                exists = True
        elif r.status_code in (301, 302):
            exists = "login" not in r.url.lower() and "signup" not in r.url.lower()
        elif r.status_code == 404:
            exists = False
        return {"platform": name, "url": url, "status": r.status_code, "found": bool(exists)}
    except Exception as e:
        return {"platform": name, "url": url, "status": None, "found": None, "error": str(e)[:80]}


def enumerate_username(username: str, workers: int = 20) -> dict:
    s = session()
    found, checked = [], []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_check_username, s, n, t.format(u=quote(username))): n
                for n, t in PLATFORMS.items()}
        for f in cf.as_completed(futs):
            res = f.result()
            checked.append(res)
            if res.get("found"):
                found.append(res)
    found.sort(key=lambda x: x["platform"])
    return {"username": username, "found": found, "found_count": len(found),
            "checked_count": len(checked)}


def gravatar(email: str) -> dict:
    h = hashlib.md5(email.strip().lower().encode()).hexdigest()
    prof = get_json(f"https://gravatar.com/{h}.json")
    entry = None
    if isinstance(prof, dict) and prof.get("entry"):
        entry = prof["entry"][0]
    return {"email": email, "hash": h,
            "avatar": f"https://www.gravatar.com/avatar/{h}",
            "has_profile": entry is not None,
            "profile": entry}


def validate_email_syntax(email: str) -> dict:
    import re
    ok = bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email))
    return {"email": email, "syntax_ok": ok}


def account_exists_signup(email: str, platform: str = "auto") -> dict:
    """Non-destructive: hit public 'password reset' / signup-check endpoints that leak existence.
    Only endpoints that are legitimately public. Returns signals, not guarantees."""
    s = session()
    probes = {
        "github": ("https://github.com/signup_check/email", {"value": email}),
        "mastodon.social": ("https://mastodon.social/api/v1/accounts/lookup", {"acct": email}),
    }
    uname = email.split("@")[0]
    res = {"email": email, "signals": []}
    for name, (url, params) in probes.items():
        if platform != "auto" and platform != name:
            continue
        try:
            r = s.get(url, params=params, timeout=12)
            res["signals"].append({"platform": name, "status": r.status_code,
                                   "body": r.text[:200]})
        except Exception as e:
            res["signals"].append({"platform": name, "error": str(e)[:80]})
    # username derived from local part
    res["username_probe"] = enumerate_username(uname) if uname else None
    return res


def breach_lookup(email: str) -> dict:
    """Free, no-key breach signals: HIBP unauth is paywalled; use public aggregators."""
    out = {"email": email, "sources": {}}
    # Gravatar presence (often tied to public profiles)
    out["sources"]["gravatar"] = gravatar(email)["has_profile"]
    # Hudson Rock free cavalier endpoint (may rate-limit)
    hr = get_json("https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email",
                  params={"email": email}, tries=2)
    if hr:
        out["sources"]["hudsonrock"] = {
            "stealers": len(hr.get("stealers", []) or []),
            "message": hr.get("message"),
        }
    return out
