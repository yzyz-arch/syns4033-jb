"""Offline self-test — no network. Validates normalisation, rendering and verdicts."""
from __future__ import annotations

import re

from .engine import BLOCKED, ERR, FAIL, OK, classify
from .phone import PhoneError, normalise, render, render_str
from .providers import BASE_HEADERS, Provider, by_name, select

CHECKS: list[tuple[str, bool]] = []


def check(label: str, cond: bool) -> None:
    CHECKS.append((label, bool(cond)))


def run() -> int:
    # --- normalisation ----------------------------------------------------
    for raw, want in [
        ("081234567890", "6281234567890"),
        ("+62 812-3456-7890", "6281234567890"),
        ("62812 3456 7890", "6281234567890"),
        ("0062 812 3456 7890", "6281234567890"),
        ("81234567890", "6281234567890"),
    ]:
        ctx = normalise(raw)
        check(f"normalise {raw!r}", ctx["digits"] == want)
        check(f"e164 {raw!r}", ctx["e164"] == "+" + want)
        check(f"local {raw!r}", ctx["local"] == "0" + want[2:])

    ctx_id = normalise("081234567890")
    for bad in ("", "   ", "abc", "123"):
        try:
            normalise(bad)
            check(f"reject {bad!r}", False)
        except PhoneError:
            check(f"reject {bad!r}", True)

    ctx_my = normalise("0123456789", cc="60")
    check("cc override 60", ctx_my["digits"] == "60123456789")

    # --- rendering --------------------------------------------------------
    check("render tokens", render_str("{e164}|{digits}", ctx_id) == "+6281234567890|6281234567890")
    check("render braces preserved",
          render_str(r"\d{2,4}", ctx_id) == r"\d{2,4}")
    check("render nested",
          render({"p": ["{local}"]}, ctx_id) == {"p": ["081234567890"]})
    check("render non-str passthrough", render(7, ctx_id) == 7)
    check("uuid fresh each call", ctx_id["uuid"] != normalise("081234567890")["uuid"])

    # --- verdicts ---------------------------------------------------------
    p = Provider(name="t", category="wa", url="https://x/y", success_contains=("otp sent",),
                 fail_contains=("captcha",))
    check("200 ok", classify(200, '{"msg":"otp sent"}', p) == OK)
    check("429 blocked", classify(429, "", p) == BLOCKED)
    check("403 blocked", classify(403, "", p) == BLOCKED)
    check("500 error", classify(500, "", p) == ERR)
    check("404 fail", classify(404, "", p) == FAIL)
    check("captcha fail", classify(200, "please solve captcha", p) == FAIL)
    check("missing marker fail", classify(200, '{"ok":true}', p) == FAIL)
    plain = Provider(name="t2", category="sms", url="https://x")
    check("no markers 200 ok", classify(200, "anything", plain) == OK)

    # --- registry ---------------------------------------------------------
    names = {p_.name for p_ in select(tier="all")}
    check("registry non-empty", len(names) > 40)
    check("live tier exists", 10 <= len(select(tier="live")) < len(names))
    check("category wa filter", all(p_.category == "wa" for p_ in select(category="wa", tier="all")))
    check("category sms filter", all(p_.category == "sms" for p_ in select(category="sms", tier="all")))
    check("only filter", {p_.name for p_ in select(only=["gojek"])} == {"gojek"})
    check("only overrides tier", [p_.name for p_ in select(only=["gojek"], tier="live")] == ["gojek"])
    check("skip filter", "gojek" not in {p_.name for p_ in select(skip=["gojek"], tier="all")})
    check("tier live only", all(p_.tier == "live" for p_ in select(tier="live")))
    check("by_name", by_name("shopee") is not None and by_name("nope") is None)
    check("unique names", len(names) == len(select(tier="all")))
    try:
        select(only=["ghost"], tier="all")
        check("unknown only raises", False)
    except KeyError:
        check("unknown only raises", True)

    # --- provider shape ---------------------------------------------------
    bad = []
    for p_ in select():
        if not p_.url.startswith(("https://", "http://")):
            bad.append(f"{p_.name}:url")
        if p_.category not in ("wa", "sms"):
            bad.append(f"{p_.name}:cat")
        if p_.json_body is None and p_.form is None and p_.method != "GET":
            bad.append(f"{p_.name}:body")
        if p_.method not in ("GET", "POST", "PUT"):
            bad.append(f"{p_.name}:method")
    check("all providers well formed: " + ", ".join(bad), not bad)

    # every extract/warmup regex must compile after rendering
    rx_bad = []
    for p_ in select():
        for pat in p_.extract.values():
            try:
                re.compile(render_str(pat, ctx_id))
            except re.error:
                rx_bad.append(p_.name)
    check("extract regexes compile: " + ", ".join(rx_bad), not rx_bad)

    # URL tokens must survive rendering
    check("url render", render_str("https://a/{digits}", ctx_id).endswith("6281234567890"))

    # --- headers ----------------------------------------------------------
    h = Provider(name="t3", category="wa", url="https://a.b/c", json_body={}).merged_headers()
    check("json forces content-type", h["content-type"] == "application/json")
    check("origin derived", h["origin"] == "https://a.b")
    check("base ua kept", "Mozilla" in BASE_HEADERS["user-agent"])

    # --- from_dict --------------------------------------------------------
    pd = Provider.from_dict({"name": "c", "category": "wa", "url": "https://c/d",
                             "success_codes": [200], "fail_contains": ["x"], "junk": 1})
    check("from_dict coerces tuples", pd.success_codes == (200,) and pd.fail_contains == ("x",))
    check("from_dict drops unknown", not hasattr(pd, "junk"))

    passed = sum(1 for _, ok in CHECKS if ok)
    for label, ok in CHECKS:
        if not ok:
            print(f"FAIL  {label}")
    print(f"\n{passed}/{len(CHECKS)} cek lulus")
    return 0 if passed == len(CHECKS) else 1
