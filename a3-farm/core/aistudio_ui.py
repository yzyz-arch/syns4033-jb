"""AI Studio UI automation: create a Cloud project + auth API key for a signed-in
Google account, then harvest the key into the DB.

Flow (as of 2026):
  1. load storage_state for the account
  2. go to https://aistudio.google.com/app/apikey
  3. accept ToS if prompted (a default project+key is auto-created)
  4. read the key from the page (data attribute / input value)
  5. repeat "Create API key in new project" up to N times (AI Studio caps ~10
     projects/keys per account at a time)
  6. store each key + project id into the DB

Key extraction is defensive across multiple DOM strategies because the UI markup
changes; every strategy is tried and any 39-char AIza.../auth-key token found in
the DOM or the network log is captured.
"""
from __future__ import annotations
import re
import time

from .config import AISTUDIO_APIKEYS, AISTUDIO_HOME, UA, LOCALES
from .db import Store
from .google_login import storage_state_path, profile_dir

# Gemini auth keys are long opaque tokens; classic keys start with AIza.
KEY_RE = re.compile(r"(AIza[0-9A-Za-z_\-]{35})")
AUTHKEY_RE = re.compile(r"\b([A-Za-z0-9_\-]{48,64})\b")


def _collect_network_keys(page, bag: set[str]):
    def on_response(resp):
        try:
            url = resp.url
        except Exception:
            return
        if "generativelanguage" in url or "aistudio" in url or "apikey" in url.lower():
            body = ""
            try:
                body = resp.text()
            except Exception:
                return
            for m in KEY_RE.findall(body):
                bag.add(m)
            if "apiKey" in body or "api_key" in body:
                for m in AUTHKEY_RE.findall(body):
                    if not m.lower().startswith(("class", "http", "script", "google")):
                        bag.add(m)
    page.on("response", on_response)


def _extract_from_dom(page) -> set[str]:
    found: set[str] = set()
    js = r"""
    () => {
      const out = [];
      document.querySelectorAll('input,textarea,[data-key],[data-api-key],code,span,div').
        forEach(el => {
          const v = el.value || el.getAttribute('data-key') || el.getAttribute('data-api-key') || el.textContent || '';
          if (v && v.length >= 35 && v.length <= 80) out.push(v.trim());
        });
      return out;
    }
    """
    try:
        vals = page.evaluate(js)
    except Exception:
        vals = []
    for v in vals:
        for m in KEY_RE.findall(v):
            found.add(m)
        if re.fullmatch(r"[A-Za-z0-9_\-]{48,64}", v):
            found.add(v)
    return found


def make_keys_for_account(email: str, max_keys: int = 10, headless: bool = True,
                          proxy: str | None = None, model: str = "") -> dict:
    """Create up to max_keys API keys for one signed-in account. Returns summary."""
    from playwright.sync_api import sync_playwright

    st = Store()
    ss = storage_state_path(email)
    if not ss.exists():
        return {"ok": False, "email": email, "error": "no storage_state — run login-google first"}

    harvested: set[str] = set()
    result = {"ok": False, "email": email, "keys": [], "error": ""}

    with sync_playwright() as p:
        locale = LOCALES[hash(email) % len(LOCALES)]
        kwargs = {
            "headless": headless,
            "user_agent": UA,
            "locale": locale["lang"],
            "timezone_id": locale["tz"],
            "viewport": {"width": 1366, "height": 768},
            "args": ["--no-sandbox", "--disable-dev-shm-usage",
                     "--disable-blink-features=AutomationControlled"],
        }
        if proxy:
            kwargs["proxy"] = {"server": proxy}
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir(email)), **kwargs)
        ctx.add_cookies(_load_cookies(ss))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _collect_network_keys(page, harvested)

        page.goto(AISTUDIO_HOME, wait_until="domcontentloaded", timeout=60000)
        _accept_tos(page)
        page.goto(AISTUDIO_APIKEYS, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        _accept_tos(page)

        harvested |= _extract_from_dom(page)

        # click "Create API key" up to N-1 more times (the first is auto-created)
        for i in range(max(0, max_keys - len(harvested))):
            clicked = _click_create_key(page)
            if not clicked:
                break
            time.sleep(3)
            _accept_tos(page)
            time.sleep(1)
            harvested |= _extract_from_dom(page)
            if len(harvested) >= max_keys:
                break

        # final DOM + network sweep
        time.sleep(2)
        harvested |= _extract_from_dom(page)

        # persistence for next run
        try:
            ctx.storage_state(path=str(ss))
        except Exception:
            pass
        ctx.close()

    for k in harvested:
        st.add_key(k, email=email, key_type="auth")
    result["keys"] = sorted(harvested)
    result["ok"] = bool(harvested)
    if not harvested:
        result["error"] = "no key token found in DOM/network"
    st.set_account_status(email, "keys_created" if result["ok"] else "error",
                          note=f"{len(harvested)} keys")
    return result


def _load_cookies(ss_path) -> list[dict]:
    import json
    try:
        state = json.loads(ss_path.read_text())
    except Exception:
        return []
    cookies = state.get("cookies", [])
    out = []
    for c in cookies:
        c = dict(c)
        c.pop("sameSite", None)
        out.append(c)
    return out


def _accept_tos(page) -> None:
    for sel in [
        "button:has-text('I agree')", "button:has-text('Accept')",
        "button:has-text('Agree')", "button:has-text('Continue')",
        "button:has-text('Got it')",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(1.5)
        except Exception:
            continue


def _click_create_key(page) -> bool:
    for sel in [
        "button:has-text('Create API key')",
        "button:has-text('Create key')",
        "button:has-text('Get API key')",
        "[aria-label*='Create API key']",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                return True
        except Exception:
            continue
    return False
