"""Tests for scripts/streamflow_client.py — no network, transport stubbed.

The endpoint lives on a tailnet (*.ts.net MagicDNS), so nothing here dials
out: `socket.getaddrinfo` and `urllib.request.urlopen` are patched. These
assert the client's contract — result normalisation, error mapping, retry
policy — which is the part that can regress without a tailnet.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import socket
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

import pytest

_MOD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "streamflow_client.py"


def _load():
    spec = importlib.util.spec_from_file_location("streamflow_client", _MOD_PATH)
    assert spec and spec.loader, f"cannot load {_MOD_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sf = _load()
URL = sf.DEFAULT_URL
_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]


def _http_error(code: int, body: bytes = b"err") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(URL, code, "err", Message(), io.BytesIO(body))


class _FakeResp:
    def __init__(self, body: str, status: int = 200):
        self._buf = io.BytesIO(body.encode())
        self.status = status

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def dns_ok(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _ADDRINFO)


@pytest.fixture
def dns_dead(monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", boom)


def test_ask_normalises_first_result(monkeypatch, dns_ok):
    body = json.dumps(
        {"model": "fayoz-ds41", "results": [{"ok": True, "text": "Siap", "ms": 879}]}
    )
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(body))

    got = sf.ask("balas satu kata: siap", backoff=0)

    assert got["ok"] is True
    assert got["text"] == "Siap"
    assert got["ms"] == 879
    assert got["model"] == "fayoz-ds41"
    assert got["raw"]["results"][0]["text"] == "Siap"


def test_ask_falls_back_to_wall_clock_ms(monkeypatch, dns_ok):
    body = json.dumps({"results": [{"ok": True, "text": "x"}]})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(body))

    got = sf.ask("hi", backoff=0)

    assert got["ms"] is not None and got["ms"] >= 0
    assert got["model"] == sf.DEFAULT_MODEL


@pytest.mark.parametrize(
    "body, needle",
    [
        ("{}", "results"),
        ('{"results": []}', "results"),
        ('{"results": ["nope"]}', "object"),
        ("<html>502</html>", "JSON"),
    ],
)
def test_ask_rejects_malformed_bodies(monkeypatch, dns_ok, body, needle):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(body))

    with pytest.raises(sf.AskError) as ei:
        sf.ask("hi", retries=1, backoff=0)
    assert needle in str(ei.value)


def test_dns_failure_names_the_real_cause(monkeypatch, dns_dead):
    with pytest.raises(sf.AskError) as ei:
        sf.ask("hi", retries=1, backoff=0)
    msg = str(ei.value)
    assert "DNS gagal" in msg and "tailnet" in msg


def test_4xx_does_not_retry(monkeypatch, dns_ok):
    calls = []

    def raise_401(*a, **k):
        calls.append(1)
        raise _http_error(401, b"nope")

    monkeypatch.setattr(urllib.request, "urlopen", raise_401)

    with pytest.raises(sf.AskError) as ei:
        sf.ask("hi", retries=3, backoff=0)
    assert "HTTP 401" in str(ei.value) and "nope" in str(ei.value)
    assert len(calls) == 1


def test_5xx_retries_then_raises(monkeypatch, dns_ok):
    calls = []

    def raise_500(*a, **k):
        calls.append(1)
        raise _http_error(500, b"boom")

    monkeypatch.setattr(urllib.request, "urlopen", raise_500)

    with pytest.raises(sf.AskError) as ei:
        sf.ask("hi", retries=3, backoff=0)
    assert "HTTP 500" in str(ei.value)
    assert len(calls) == 3


def test_5xx_then_success_on_retry(monkeypatch, dns_ok):
    bodies = [None, json.dumps({"results": [{"ok": True, "text": "Siap"}]})]
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        body = bodies.pop(0)
        if body is None:
            raise _http_error(503, b"busy")
        return _FakeResp(body)

    monkeypatch.setattr(urllib.request, "urlopen", flaky)

    got = sf.ask("hi", retries=3, backoff=0)
    assert got["text"] == "Siap" and len(calls) == 2


def test_selftest_stops_at_dns(monkeypatch, dns_dead, capsys):
    assert sf.selftest() == 2
    out = capsys.readouterr().out
    assert "dns      : FAIL" in out and "tailnet" in out


def test_selftest_full_path(monkeypatch, dns_ok, capsys):
    body = json.dumps({"results": [{"ok": True, "text": "Siap", "ms": 12}]})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(body))
    # selftest juga dial TCP langsung; jangan sentuh network beneran
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: contextlib.nullcontext())

    assert sf.selftest() == 0
    out = capsys.readouterr().out
    assert "tcp      : OK" in out and "http     : OK" in out


def test_cli_reports_error_without_traceback(monkeypatch, dns_dead, capsys):
    assert sf.main(["balas satu kata: siap"]) == 1
    assert "ERROR: DNS gagal" in capsys.readouterr().err


def test_cli_prints_answer(monkeypatch, dns_ok, capsys):
    body = json.dumps({"results": [{"ok": True, "text": "Siap", "ms": 879}]})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(body))

    assert sf.main(["balas satu kata: siap"]) == 0
    out = capsys.readouterr().out
    assert "ok=True" in out and "Siap" in out


def test_cli_requires_prompt():
    with pytest.raises(SystemExit):
        sf.main([])
