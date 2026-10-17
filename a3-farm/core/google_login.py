"""Google account login via Playwright, sourcing the password from the Hermes vault.

NEVER types a password itself: the identifier is typed via the browser, and the
secret is injected only through the vault tooling at the agent layer. This module
drives the *page*; credential injection is done by the caller/agent.

Because the standalone script cannot invoke the vault tools, it supports two
modes:
  - "manual": opens headed Chromium with a persistent profile so the operator
    completes login/2FA once; the session persists in profiles/<email>/.
  - "cookie": loads a previously exported storage_state json.
"""
from __future__ import annotations
import json
from pathlib import Path

from .config import PROFILES, GOOGLE_ACCOUNTS, UA, LOCALES


def profile_dir(email: str) -> Path:
    safe = email.replace("@", "_at_").replace("/", "_")
    d = PROFILES / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def storage_state_path(email: str) -> Path:
    safe = email.replace("@", "_at_").replace("/", "_")
    return PROFILES / f"storage_{safe}.json"


def open_login_context(playwright, email: str, headless: bool = False, proxy: str | None = None):
    """Return (browser, context) with a persistent profile bound to the account."""
    locale = LOCALES[hash(email) % len(LOCALES)]
    launch_kwargs = {
        "headless": headless,
        "args": ["--no-sandbox", "--disable-dev-shm-usage",
                 "--disable-blink-features=AutomationControlled"],
    }
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}
    browser = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir(email)),
        user_agent=UA,
        locale=locale["lang"],
        timezone_id=locale["tz"],
        viewport={"width": 1366, "height": 768},
        **launch_kwargs,
    )
    return browser, browser  # persistent context: context == browser handle


def login_flow(email: str, headless: bool = False, proxy: str | None = None,
               timeout_ms: int = 300000) -> dict:
    """Open Google login for the account. In manual mode the operator completes it.

    Returns {ok, email, storage_state, note}. If an exported storage_state exists
    and still valid, it is reused.
    """
    from playwright.sync_api import sync_playwright

    ss = storage_state_path(email)
    if ss.exists():
        try:
            state = json.loads(ss.read_text())
            if state.get("cookies"):
                return {"ok": True, "email": email, "storage_state": str(ss),
                        "note": "reused existing storage_state"}
        except json.JSONDecodeError:
            pass

    with sync_playwright() as p:
        browser, ctx = open_login_context(p, email, headless=headless, proxy=proxy)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(GOOGLE_ACCOUNTS, wait_until="domcontentloaded", timeout=60000)
        # If already signed in (persistent profile), we're done.
        try:
            page.wait_for_url("**/mail**", timeout=3000)
        except Exception:
            pass
        signed_in = "myaccount.google.com" in page.url or "google.com/webhp" in page.url
        if not signed_in and not headless:
            print(f"[*] Login window for {email}. Complete sign-in (incl. 2FA) in the browser.")
            print("[*] Waiting up to %ds for the session..." % (timeout_ms // 1000))
            try:
                page.wait_for_url("**myaccount.google.com**", timeout=timeout_ms)
                signed_in = True
            except Exception:
                # fall back: any google signed-in page
                signed_in = "google.com" in page.url and "signin" not in page.url
            ctx.storage_state(path=str(ss))
        elif signed_in:
            ctx.storage_state(path=str(ss))
        browser.close()
    return {"ok": signed_in, "email": email,
            "storage_state": str(ss) if signed_in else None,
            "note": "signed in" if signed_in else "not signed in"}
