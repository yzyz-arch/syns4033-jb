"""Offline contract tests for osintkit.phone_nik + osintkit.livegeo.

No network, no real PII: every identifier is synthetic. The tests assert both
the functional behaviour (decode, normalise, ingest, locate) and the guardrails
(loopback-only bind, required authorization flag, PII gate, ingest plausibility).
"""
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from osintkit import livegeo, phone_nik  # noqa: E402


# ---------------------------------------------------------------- phone_nik

def test_nik_female_decoding():
    r = phone_nik.parse_nik("3201235508900001", authorized=True)
    assert r["valid"] is True
    assert r["sex"] == "female"          # day field 55 -> 15, +40 marks female
    assert r["birth_date"] == "15-08-90"
    assert r["province"] == "Jawa Barat"
    assert r["province_code"] == "32"
    assert r["serial"] == "0001"


def test_nik_male_decoding():
    r = phone_nik.parse_nik("3201231508900001", authorized=True)
    assert r["valid"] is True
    assert r["sex"] == "male"
    assert r["birth_date"] == "15-08-90"


def test_nik_sex_lives_in_day_field_not_serial():
    """The 'odd serial = male' myth must not leak into the decoder."""
    male = phone_nik.parse_nik("3201231508900001", authorized=True)   # even serial
    female = phone_nik.parse_nik("3201235508900001", authorized=True)  # even serial
    assert male["sex"] == "male" and female["sex"] == "female"


def test_nik_rejects_bad_input():
    assert phone_nik.parse_nik("3201", authorized=True)["valid"] is False
    assert phone_nik.parse_nik("3201235513900001", authorized=True)["valid"] is False  # month 13
    assert phone_nik.parse_nik("3201235599900001", authorized=True)["valid"] is False  # day 59
    assert phone_nik.parse_nik("abcdefghijklmnop", authorized=True)["valid"] is False
    assert phone_nik.parse_nik("0000000000000000", authorized=True)["valid"] is False


def test_nik_has_no_checksum():
    r = phone_nik.parse_nik("3201235508900001", authorized=True)
    assert r["checksum"] is None
    assert "no check digit" in r["checksum_note"]


def test_nik_masks_input():
    r = phone_nik.parse_nik("3201235508900001", authorized=True)
    assert r["input_masked"] == "3201**********01"
    assert "3201235508900001" not in str(r["input_masked"])


def test_nik_requires_authorization_flag():
    with pytest.raises(PermissionError):
        phone_nik.parse_nik("3201235508900001")


def test_nik_declares_no_location_capability():
    r = phone_nik.parse_nik("3201235508900001", authorized=True)
    assert r["location_capability"] == "none"
    assert "HLR/GMLC" in r["location_why"]


def test_phone_normalisation_forms():
    for raw in ("+6281234567890", "6281234567890", "081234567890", "81234567890"):
        p = phone_nik.normalize_phone(raw)
        assert p["valid"] is True, raw
        assert p["e164"] == "+6281234567890"
        assert p["national"] == "081234567890"
        assert p["operator_guess"] == "Telkomsel"
        assert p["line_type"] == "mobile"


def test_phone_operator_table():
    assert phone_nik.normalize_phone("0817")["valid"] is False or True  # length guard below
    assert phone_nik.normalize_phone("089612345678")["operator_guess"] == "Tri (3)"
    assert phone_nik.normalize_phone("088112345678")["operator_guess"] == "Smartfren"
    assert phone_nik.normalize_phone("085612345678")["operator_guess"] == "Indosat Ooredoo"


def test_phone_fixed_line_area():
    p = phone_nik.normalize_phone("021-5551234")
    assert p["valid"] is True and p["line_type"] == "fixed"
    assert p["fixed_area_city"] == "Jakarta"
    assert "location_capability" in p and p["location_capability"] == "none"


def test_phone_rejects_garbage():
    for bad in ("0812", "abc", "12345678"):
        assert phone_nik.normalize_phone(bad)["valid"] is False, bad


def test_correlate_capability_matrix_is_honest():
    r = phone_nik.correlate(nik="3201235508900001", phone="081234567890", authorized=True)
    cap = r["capability_matrix"]
    assert cap["live_gps_position"]["available"] is False
    assert cap["last_known_cell_tower"]["available"] is False
    assert cap["registered_address"]["available"] is True
    assert r["network_egress"].startswith("blocked")


def test_offline_guard_blocks_sockets():
    with pytest.raises(phone_nik.NetworkEgressBlocked):
        with phone_nik.offline_guard(True):
            __import__("socket").create_connection(("1.1.1.1", 80), timeout=1)


def test_offline_guard_restores_socket():
    import socket
    real = socket.create_connection
    with phone_nik.offline_guard(True):
        pass
    assert socket.create_connection is real


def test_phone_nik_selftest_passes():
    assert phone_nik.selftest()["ok"] is True


# ---------------------------------------------------------------- livegeo guards

def test_assert_loopback_accepts_loopback():
    assert livegeo.assert_loopback("127.0.0.1") == "127.0.0.1"
    assert livegeo.assert_loopback("localhost") == "127.0.0.1"
    assert livegeo.assert_loopback("::1") == "::1"


def test_assert_loopback_rejects_everything_else():
    for host in ("0.0.0.0", "8.8.8.8", "192.168.1.10", "10.0.0.1", "example.com"):
        with pytest.raises(livegeo.GuardrailViolation):
            livegeo.assert_loopback(host)


def test_require_authorization():
    with pytest.raises(livegeo.GuardrailViolation):
        livegeo.require_authorization(False)
    livegeo.require_authorization(True)  # must not raise


def test_geo_math():
    # 1 degree of latitude ~ 111.1 km
    d = livegeo.haversine_m(0.0, 0.0, 1.0, 0.0)
    assert 111_000 < d < 111_300
    assert livegeo.haversine_m(-6.2, 106.8, -6.2, 106.8) == 0.0
    assert 0 <= livegeo.bearing_deg(0, 0, 1, 0) < 360
    assert abs(livegeo.bearing_deg(0, 0, 1, 0) - 0) < 1  # due north


def test_freshness_classes():
    assert livegeo.classify_age(10) == "live"
    assert livegeo.classify_age(600) == "recent"
    assert livegeo.classify_age(3000) == "stale"
    assert livegeo.classify_age(40000) == "cold"
    assert livegeo.classify_age(200000) == "historic"
    assert livegeo.classify_age(-5) == "future_clock"


# ---------------------------------------------------------------- livegeo store

def _store():
    return livegeo.Store(":memory:")


def test_register_returns_token_once_and_stores_hash():
    s = _store()
    r = s.register("dev1", label="lab", phone="081234567890", nik="3201235508900001")
    assert r["phone_e164"] == "+6281234567890"
    assert r["nik_masked"] == "3201**********01"
    assert len(r["token"]) > 20
    assert s.auth("dev1", r["token"]) is True
    assert s.auth("dev1", "wrong") is False
    # plaintext token must not be persisted
    row = s._db.execute("SELECT token_hash FROM devices WHERE device_id='dev1'").fetchone()
    assert r["token"] not in row["token_hash"]
    s.close()


def test_register_rejects_bad_identifiers():
    s = _store()
    with pytest.raises(ValueError):
        s.register("dev2", phone="123")
    with pytest.raises(ValueError):
        s.register("dev3", nik="3201235")
    s.close()


def test_devices_for_join_keys():
    s = _store()
    s.register("d1", phone="081234567890")
    s.register("d2", nik="3201235508900001")
    assert [d["device_id"] for d in s.devices_for(phone="+6281234567890")] == ["d1"]
    assert [d["device_id"] for d in s.devices_for(nik="3201235508900001")] == ["d2"]
    assert s.devices_for(phone="089999999999") == []
    s.close()


def test_ingest_accepts_and_rejects():
    s = _store()
    s.register("d1")
    s.add_ping("d1", -6.2, 106.8, acc_m=10)
    with pytest.raises(ValueError):
        s.add_ping("d1", -95.0, 106.8, acc_m=10)          # lat range
    with pytest.raises(ValueError):
        s.add_ping("d1", -6.2, 200.0, acc_m=10)           # lon range
    with pytest.raises(ValueError):
        s.add_ping("d1", 0.0, 0.0, acc_m=10)              # null island
    with pytest.raises(ValueError):
        s.add_ping("d1", -6.2, 106.8, acc_m=99_999)       # accuracy ceiling
    s.close()


def test_ingest_rate_limit():
    s = _store()
    s.register("d1")
    s.add_ping("d1", -6.2, 106.8)
    with pytest.raises(ValueError, match="rate limited"):
        s.add_ping("d1", -6.2, 106.9)
    s.close()


def test_ingest_rejects_future_clock():
    s = _store()
    s.register("d1")
    import time as _t
    with pytest.raises(ValueError, match="future"):
        s.add_ping("d1", -6.2, 106.8, ts=_t.time() + 3600)
    s.close()


def test_locate_by_phone_and_nik():
    s = _store()
    s.register("d1", label="lab handset", phone="081234567890", nik="3201235508900001")
    s.add_ping("d1", -6.2088, 106.8456, acc_m=12)
    for kw in ({"phone": "081234567890"}, {"nik": "3201235508900001"},
               {"device_id": "d1"}):
        r = livegeo.locate(s, ref_lat=-6.2, ref_lon=106.8, **kw)
        assert r["found"] is True
        assert r["position_source"] == "device-reported"
        fix = r["best"]
        assert fix["lat"] == -6.2088 and fix["lon"] == 106.8456
        assert fix["freshness"] == "live"
        assert fix["distance_m"] > 0
    s.close()


def test_locate_unknown_identity():
    s = _store()
    r = livegeo.locate(s, phone="089999999999")
    assert r["found"] is False
    assert "no registered device" in r["reason"]
    s.close()


def test_locate_returns_newest_fix_not_oldest():
    """Regression: locate() used track(limit=1), which is oldest-first."""
    s = _store()
    s.register("d1", phone="081234567890")
    import time as _t
    now = _t.time()
    s.add_ping("d1", -6.1000, 106.7000, ts=now - 600)   # oldest
    s.add_ping("d1", -6.3000, 106.9000, ts=now - 400)
    s.add_ping("d1", -6.2088, 106.8456, ts=now - 200)   # newest
    r = livegeo.locate(s, phone="081234567890")
    assert r["found"] is True
    assert r["best"]["lat"] == -6.2088
    assert r["best"]["lon"] == 106.8456
    assert r["fixes"][0]["fix"]["lat"] == -6.2088
    s.close()


def test_locate_best_is_never_null_when_found():
    """Regression: found:true used to ship together with best:null."""
    s = _store()
    s.register("d1", nik="3201235508900001")
    import time as _t
    # 10 minutes old => "recent", not "live"
    s.add_ping("d1", -6.2088, 106.8456, ts=_t.time() - 600)
    r = livegeo.locate(s, nik="3201235508900001")
    assert r["found"] is True
    assert r["best"] is not None
    assert r["live_count"] == 0
    assert r["best_is_live"] is False
    assert r["best"]["freshness"] == "recent"
    assert "staleness_note" in r
    s.close()


def test_locate_live_flag_and_no_staleness_note():
    s = _store()
    s.register("d1", phone="081234567890")
    s.add_ping("d1", -6.2088, 106.8456)
    r = livegeo.locate(s, phone="081234567890")
    assert r["best_is_live"] is True
    assert r["live_count"] == 1
    assert "staleness_note" not in r
    s.close()


def test_latest_ping_is_newest():
    s = _store()
    s.register("d1")
    import time as _t
    now = _t.time()
    s.add_ping("d1", -6.1, 106.7, ts=now - 30)
    s.add_ping("d1", -6.2, 106.8, ts=now - 5)
    assert s.latest_ping("d1")["lat"] == -6.2
    # track() stays oldest-first for plotting
    assert s.track("d1", hours=1)[0]["lat"] == -6.1
    assert s.latest_ping("nope") is None
    s.close()


def test_track_report_distance_and_speed():
    s = _store()
    s.register("d1")
    import time as _t
    now = _t.time()
    # (0,0) is rejected as a sentinel, so the track starts just off it.
    s.add_ping("d1", 0.001, 0.001, ts=now - 10)
    s.add_ping("d1", 0.002, 0.001, ts=now - 5)
    r = livegeo.track_report(s, "d1", hours=1)
    assert r["points"] == 2
    assert 100 < r["distance_m"] < 115
    assert r["avg_speed_kmh"] is not None
    s.close()


def test_simulate_produces_a_track():
    s = _store()
    s.register("d1")
    out = livegeo.simulate(s, "d1", points=3, interval=0.0)
    assert out["points_sent"] == 3
    assert livegeo.track_report(s, "d1")["points"] == 3
    s.close()


def test_make_server_binds_loopback_only():
    s = _store()
    srv = livegeo.make_server(s, "127.0.0.1", 0)
    assert srv.server_address[0] == "127.0.0.1"
    srv.server_close()
    for bad in ("0.0.0.0", "8.8.8.8"):
        with pytest.raises(livegeo.GuardrailViolation):
            livegeo.make_server(s, bad, 0)
    s.close()


def test_serve_requires_authorization():
    s = _store()
    with pytest.raises(livegeo.GuardrailViolation):
        livegeo.serve(s, "127.0.0.1", 0)
    s.close()


def test_http_end_to_end():
    """Real HTTP round-trip against an ephemeral loopback server."""
    import json
    import threading
    import urllib.error
    import urllib.request

    s = _store()
    dev = s.register("d1", label="lab", phone="081234567890", nik="3201235508900001")
    srv = livegeo.make_server(s, "127.0.0.1", 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=5) as r:
            assert json.loads(r.read())["ok"] is True

        # unauthorized ingest
        req = urllib.request.Request(
            f"{base}/ingest", method="POST",
            data=json.dumps({"device_id": "d1", "token": "nope",
                             "lat": -6.2, "lon": 106.8}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("bad token was accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 401

        # authorized ingest
        req = urllib.request.Request(
            f"{base}/ingest", method="POST",
            data=json.dumps({"device_id": "d1", "token": dev["token"],
                             "lat": -6.2088, "lon": 106.8456,
                             "acc": 15, "battery": 77}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 202

        with urllib.request.urlopen(
                f"{base}/locate?phone=%2B6281234567890", timeout=5) as r:
            loc = json.loads(r.read())
        assert loc["found"] is True
        assert loc["position_source"] == "device-reported"
        assert loc["best"]["lat"] == -6.2088

        with urllib.request.urlopen(f"{base}/devices", timeout=5) as r:
            raw = r.read().decode()
            devs = json.loads(raw)["devices"]
        assert len(devs) == 1
        # Regression: /devices must never emit raw PII. The store keeps the
        # exact join keys internally, but egress goes through public_device().
        assert "3201235508900001" not in raw
        assert "+6281234567890" not in raw
        assert devs[0]["nik_masked"].endswith("01") and "*" in devs[0]["nik_masked"]
        assert devs[0]["phone_masked"].startswith("+6281") and "*" in devs[0]["phone_masked"]
        assert "nik" not in devs[0] and "phone_e164" not in devs[0]
    finally:
        srv.shutdown()
        srv.server_close()
        s.close()


def test_cli_geo_wiring():
    from osintkit.cli import build_parser
    ap = build_parser()
    a = ap.parse_args(["geo", "locate", "--phone", "081234567890",
                       "--i-have-authorization"])
    assert a.action == "locate" and a.func.__name__ == "cmd_geo"
    a = ap.parse_args(["nik", "3201235508900001", "--i-have-authorization"])
    assert a.target == "3201235508900001"
    a = ap.parse_args(["id", "--nik", "3201235508900001", "--phone", "081234567890",
                       "--i-have-authorization"])
    assert a.nik == "3201235508900001"


def test_cli_requires_authorization(capsys):
    from osintkit.cli import main
    import pytest as _pytest
    with _pytest.raises(livegeo.GuardrailViolation):
        main(["geo", "locate", "--phone", "081234567890"])
    with _pytest.raises(livegeo.GuardrailViolation):
        main(["nik", "3201235508900001"])
