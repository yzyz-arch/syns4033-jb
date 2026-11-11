"""Offline tests for the otpbomb skill package."""
from __future__ import annotations

import asyncio
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


# --- soft markers -----------------------------------------------------------
def test_soft_contains_is_ok():
    p = Provider(name="s", category="wa", url="https://x/y", soft_contains=("sudah terdaftar",))
    assert classify(200, '{"m":"nomor sudah terdaftar"}', p) == OK


def test_fail_beats_soft():
    p = Provider(name="s", category="wa", url="https://x/y",
                 soft_contains=("captcha",), fail_contains=("captcha",))
    assert classify(200, "solve captcha", p) == FAIL


def test_soft_ignored_on_server_error():
    p = Provider(name="s", category="wa", url="https://x/y", soft_contains=("sudah terdaftar",))
    assert classify(500, "sudah terdaftar", p) == ERR


def test_from_dict_coerces_soft():
    p = Provider.from_dict({"name": "c", "category": "wa", "url": "https://c/d",
                            "soft_contains": ["a"]})
    assert p.soft_contains == ("a",)


# --- prefetch / headers (offline via MockTransport) -------------------------
def _mock_provider() -> Provider:
    return Provider(
        name="mock", category="wa", url="https://mock.test/send", tier="live",
        pre_url="https://mock.test/warm",
        extract={"field:tk": r'id="Token"\s+value="([^"]+)"',
                 "header:x-tok": r"x-csrf:? (HDRVAL)",
                 "cookie:cs": r"cs=([A-Za-z0-9]+)"},
        form={"phone": "{digits}", "tk": ""},
    )


def _client(seen: dict):
    import httpx

    def handler(request):
        if request.url.path == "/warm":
            seen["warm"] = request.headers.get("x-from-flag")
            return httpx.Response(
                200, text='<input id="Token" value="abc123">',
                headers={"x-csrf": "HDRVAL", "set-cookie": "cs=COOKIEVAL; Path=/",
                         "content-type": "text/html"})
        seen["post"] = request.headers.get("x-from-flag")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_prefetch_scrapes_tokens():
    from tools.otpbomb.engine import Engine, Options

    async def go():
        seen: dict = {}
        eng = Engine(normalise("081234567890"), Options(retries=0))
        async with _client(seen) as c:
            return await eng._prefetch(c, _mock_provider())

    tokens = asyncio.run(go())
    assert tokens["f:tk"] == "abc123"
    assert tokens["h:x-tok"] == "HDRVAL"


def test_prefetch_without_pre_url_is_empty():
    from tools.otpbomb.engine import Engine, Options

    async def go():
        eng = Engine(normalise("081234567890"), Options())
        async with _client({}) as c:
            return await eng._prefetch(c, Provider(name="n", category="sms", url="https://m.test/x"))

    assert asyncio.run(go()) == {}


def test_attempt_injects_token_and_extra_header():
    from tools.otpbomb.engine import Engine, Options

    async def go():
        seen: dict = {}
        eng = Engine(normalise("081234567890"),
                     Options(retries=0, extra_headers={"x-from-flag": "yes"}))
        async with _client(seen) as c:
            return await eng.attempt(c, _mock_provider(), 1), seen

    res, seen = asyncio.run(go())
    assert res.verdict == OK
    assert seen["warm"] == "yes" and seen["post"] == "yes"
    assert "tk=abc123" in seen["body"]


def test_attempt_records_error_without_raising():
    import httpx

    from tools.otpbomb.engine import Engine, Options

    def boom(_request):
        raise RuntimeError("dns mati")

    async def go():
        eng = Engine(normalise("081234567890"), Options(retries=0))
        async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as c:
            return await eng.attempt(c, _mock_provider(), 1)

    res = asyncio.run(go())
    assert res.verdict == ERR and "RuntimeError" in res.error


# --- discover helpers -------------------------------------------------------
def test_registrable_and_same_site():
    from tools.otpbomb.discover import _keep, _registrable, _same_site

    assert _registrable("api.shopee.co.id") == "shopee.co.id"
    assert _same_site("https://shopee.co.id/x", "shopee.co.id")
    assert not _same_site("https://evil.test/x", "shopee.co.id")
    assert _keep("/api/v1/otp/send") and not _keep("/img/otp.png")


# --- cli glue ---------------------------------------------------------------
def test_cli_headers_and_clamps():
    from tools.otpbomb.cli import _base_parser, _opts

    args = _base_parser().parse_args(
        ["blast", "081234567890", "-H", "x-a: 1", "--cookie", "k=v",
         "--concurrency", "0", "--rounds", "0", "-k"])
    opts = _opts(args)
    assert opts.extra_headers == {"x-a": "1"}
    assert opts.cookies == "k=v"
    assert opts.concurrency == 1 and opts.rounds == 1 and opts.insecure


def test_cli_bad_header_exits():
    from tools.otpbomb.cli import _base_parser, _opts

    args = _base_parser().parse_args(["blast", "081234567890", "-H", "noheader"])
    with pytest.raises(SystemExit):
        _opts(args)


def test_load_rejects_garbage(tmp_path):
    from tools.otpbomb.cli import _load

    bad = tmp_path / "p.json"
    bad.write_text("{not json")
    with pytest.raises(SystemExit):
        _load(str(bad))
    bad.write_text('{"a":1}')
    with pytest.raises(SystemExit):
        _load(str(bad))
    bad.write_text('[{"name":"x","category":"wa","method":"POST"}]')
    with pytest.raises(SystemExit):  # tanpa url
        _load(str(bad))


def test_load_is_idempotent(tmp_path):
    from tools.otpbomb import providers as prov
    from tools.otpbomb.cli import _load

    p = tmp_path / "ok.json"
    p.write_text('[{"name":"uniku","category":"wa","url":"https://u.test/a","json_body":{"a":1}}]')
    _load(str(p))
    _load(str(p))
    assert [x.name for x in prov.REGISTRY].count("uniku") == 1
