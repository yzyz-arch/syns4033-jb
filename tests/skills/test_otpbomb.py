"""Offline tests for the otpbomb skill package."""
from __future__ import annotations

import re

import pytest

from tools.otpbomb import providers as prov
from tools.otpbomb.engine import BLOCKED, ERR, FAIL, OK, Options, Stats, classify
from tools.otpbomb.phone import PhoneError, normalise, render, render_str
from tools.otpbomb.providers import Provider


@pytest.mark.parametrize("raw,want", [
    ("081234567890", "6281234567890"),
    ("+62 812-3456-7890", "6281234567890"),
    ("0062 812 3456 7890", "6281234567890"),
    ("81234567890", "6281234567890"),
])
def test_normalise_local_forms(raw, want):
    ctx = normalise(raw)
    assert ctx["digits"] == want
    assert ctx["e164"] == "+" + want
    assert ctx["local"] == "0" + want[2:]


def test_normalise_country_override():
    assert normalise("0123456789", cc="60")["digits"] == "60123456789"


@pytest.mark.parametrize("bad", ["", "   ", "abc", "123"])
def test_normalise_rejects(bad):
    with pytest.raises(PhoneError):
        normalise(bad)


def test_render_keeps_brace_quantifiers():
    ctx = normalise("081234567890")
    assert render_str(r"\d{2,4}", ctx) == r"\d{2,4}"
    assert render({"p": ["{local}"]}, ctx) == {"p": ["081234567890"]}


def test_render_str_tokens():
    ctx = normalise("081234567890")
    assert render_str("{e164}|{digits}", ctx) == "+6281234567890|6281234567890"


def test_uuid_varies():
    assert normalise("081234567890")["uuid"] != normalise("081234567890")["uuid"]


def test_classify_verdicts():
    p = Provider(name="t", category="wa", url="https://x/y",
                 success_contains=("otp sent",), fail_contains=("captcha",))
    assert classify(200, '{"m":"otp sent"}', p) == OK
    assert classify(429, "", p) == BLOCKED
    assert classify(500, "", p) == ERR
    assert classify(404, "", p) == FAIL
    assert classify(200, "solve captcha", p) == FAIL
    assert classify(200, '{"ok":1}', p) == FAIL
    assert classify(200, "apa saja", Provider(name="p", category="sms", url="https://x")) == OK


def test_registry_shape():
    pool = prov.select(tier="all")
    assert len(pool) > 40
    names = [p.name for p in pool]
    assert len(names) == len(set(names))
    for p in pool:
        assert p.url.startswith(("https://", "http://"))
        assert p.category in ("wa", "sms")
        assert p.method in ("GET", "POST", "PUT")
        assert p.tier in ("live", "guess")
        if p.method != "GET":
            assert p.form or p.json_body


def test_registry_has_live_tier():
    live = prov.select(tier="live")
    assert len(live) >= 10
    assert all(p.tier == "live" for p in live)
    assert len(live) < len(prov.select(tier="all"))


def test_select_filters():
    assert {p.name for p in prov.select(only=["gojek"], tier="all")} == {"gojek"}
    assert "gojek" not in {p.name for p in prov.select(skip=["gojek"], tier="all")}
    assert all(p.category == "wa" for p in prov.select(category="wa", tier="all"))
    with pytest.raises(KeyError):
        prov.select(only=["ghost"], tier="all")


def test_extract_regexes_compile():
    ctx = normalise("081234567890")
    for p in prov.select(tier="all"):
        for pat in p.extract.values():
            re.compile(render_str(pat, ctx))


def test_headers_derived():
    p = Provider(name="t", category="wa", url="https://a.b/c", json_body={})
    h = p.merged_headers()
    assert h["content-type"] == "application/json"
    assert h["origin"] == "https://a.b"
    assert "Mozilla" in h["user-agent"]


def test_from_dict_coercion():
    p = Provider.from_dict({"name": "c", "category": "wa", "url": "https://c/d",
                            "success_codes": [200], "fail_contains": ["x"], "junk": 1})
    assert p.success_codes == (200,)
    assert p.fail_contains == ("x",)
    assert not hasattr(p, "junk")


def test_stats_record_and_summary():
    st = Stats()
    st.record(type("R", (), {"provider": "a", "verdict": OK})())
    st.record(type("R", (), {"provider": "a", "verdict": ERR})())
    out = st.summary(2.0)
    assert out["sent"] == 2 and out["accepted"] == 1 and out["network_error"] == 1
    assert out["per_provider"]["a"]["ok"] == 1


def test_options_defaults():
    o = Options()
    assert o.concurrency >= 1 and o.timeout > 0 and o.retries >= 0


def test_cli_help_runs():
    from tools.otpbomb.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
