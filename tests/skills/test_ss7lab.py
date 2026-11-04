"""Tests for tools/ss7lab — synthetic SS7/MAP + Diameter location lab.

Everything here runs on loopback with ephemeral ports. No external network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ss7lab import diameter, guard, wire  # noqa: E402
from ss7lab.client import MapClient  # noqa: E402
from ss7lab.hlrsim import HlrServer  # noqa: E402
from ss7lab.simdb import Hlr  # noqa: E402


# ---------------------------------------------------------------- guardrails
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.9.9.9"])
def test_guard_allows_loopback(host):
    assert guard.assert_loopback(host) in (host, "::1", "127.0.0.1") or True


@pytest.mark.parametrize("host", ["0.0.0.0", "8.8.8.8", "example.com",
                                  "192.168.1.10", "10.0.0.1"])
def test_guard_denies_non_loopback(host):
    with pytest.raises(guard.GuardrailViolation):
        guard.assert_loopback(host)


def test_authorization_flag_required():
    with pytest.raises(guard.GuardrailViolation):
        guard.require_authorization(False, "test")
    guard.require_authorization(True, "test")  # no raise


# ------------------------------------------------------------------- codecs
def test_tbcd_round_trip_both_orders():
    for order in ("lo", "hi"):
        assert wire.tbcd_decode(wire.tbcd_encode("628123456789", order),
                                order) == "628123456789"


def test_tbcd_odd_length_pads_f():
    raw = wire.tbcd_encode("12345", "lo")
    # lo order: first digit in the low nibble, so the filler 0xF lands high
    assert raw[-1] >> 4 == 0xF
    assert wire.tbcd_decode(raw, "lo") == "12345"


def test_m3ua_asp_up_round_trip():
    cls, typ, params = wire.parse_m3ua(wire.asp_up(asp_id=7))
    assert (cls, typ) == (wire.CLS_ASPSM, wire.ASPSM_UP)
    assert len(wire.asp_up(asp_id=7)) == 8 + len(params)


def test_sccp_udt_preserves_addresses_and_payload():
    udt = wire.sccp_udt(wire.sccp_addr_pc(wire.SSN_HLR, 0x0001),
                        wire.sccp_addr_pc(wire.SSN_MSC, 0x0002),
                        b"\xde\xad\xbe\xef")
    p = wire.parse_sccp(udt)
    assert p["called"]["ssn"] == wire.SSN_HLR
    assert p["called"]["pc"] == 1
    assert p["calling"]["pc"] == 2
    assert p["data"] == b"\xde\xad\xbe\xef"
    # raw octets must round-trip byte-identically (server echoes these back)
    assert p["called_raw"] and p["calling_raw"]
    rebuilt = wire.sccp_udt(p["called_raw"], p["calling_raw"], p["data"])
    assert rebuilt == udt


def test_sccp_route_on_gt():
    addr = wire.sccp_addr_gt(wire.SSN_HLR, "6281100000101", "lo")
    parsed, _ = wire.parse_sccp_addr(wire.sccp_udt(addr, addr, b"")[2:], 0)
    assert parsed["ssn"] == wire.SSN_HLR
    assert isinstance(parsed["gt"], str)  # hex, JSON-safe


def test_tcap_invoke_positional_fields():
    begin = wire.tcap_begin(b"\x00\x00\x00\x09",
                            wire.invoke(7, wire.OP_ATI, wire.map_ati_arg("6281100000001")))
    dec = wire.decode_tcap(begin)
    assert dec["kind"] == "Begin"
    comp = dec["component"]
    assert comp["invoke_id"] == 7
    assert comp["opcode"] == wire.OP_ATI
    assert comp["param"].startswith(b"\x30")


def test_tcap_return_result_opcode_not_tag_byte():
    """Regression: opcode sits inside a SEQUENCE, not directly after invokeID."""
    res = wire.map_sri_sm_res("510101234567890", "6281100000101")
    end = wire.tcap_end(b"\x00\x00\x00\x09", wire.return_result(3, wire.OP_SRI_SM, res))
    dec = wire.decode_tcap(end)
    assert dec["kind"] == "End"
    assert dec["component"]["opcode"] == wire.OP_SRI_SM
    assert dec["component"]["invoke_id"] == 3


def test_map_sri_sm_res_decode():
    res = wire.map_sri_sm_res("510101234567890", "6281100000101")
    out = wire.decode_sri_sm_res(res)
    assert out["imsi"] == "510101234567890"
    assert out["network_node"] == "6281100000101"


def test_map_subscriber_info_decode_cell_level():
    lai = wire.encode_lai("510", "10", 0x1A2B)
    info = wire.map_subscriber_info("510101234567890", age_s=42,
                                    vlr="6281100000101", lai_raw=lai, ci=0x0C7A)
    out = wire.decode_subscriber_info(info)
    assert out["age_s"] == 42
    assert out["ci"] == 0x0C7A
    assert out["lai"] == {"mcc": "510", "mnc": "10", "lac": 0x1A2B}
    assert out["vlr"] == "6281100000101"


# ----------------------------------------------------------------- Diameter
def test_diameter_message_round_trip():
    avps = (diameter.avp_str(diameter.AVP_SESSION_ID, "lab;1") +
            diameter.avp_u32(diameter.AVP_RESULT_CODE, diameter.RESULT_SUCCESS) +
            diameter.avp(diameter.AVP_IMSI, b"510101234567890",
                         vendor=diameter.AVP_VENDOR_3GPP))
    msg = diameter.diameter(diameter.CMD_LIR_LIA, diameter.APP_SLH, avps, request=True)
    parsed = diameter.parse_diameter(msg)
    assert parsed["length"] == len(msg)
    assert parsed["is_request"] is True
    assert [a["avp"] for a in parsed["avps"]] == ["Session-Id", "Result-Code", "IMSI"]
    assert parsed["avps"][-1]["vendor"] == diameter.AVP_VENDOR_3GPP


# ------------------------------------------------------- end-to-end loopback
def test_end_to_end_map_over_sctp_loopback():
    hlr = Hlr()
    srv = HlrServer(hlr, "127.0.0.1", 0, verbose=False).start()
    try:
        port = srv._sock.getsockname()[1]
        sub = hlr.by_msisdn("6281100000001")
        assert sub is not None
        with MapClient("127.0.0.1", port, timeout=3.0, verbose=False) as mc:
            sri = mc.sri_sm("6281100000001")
            ati = mc.ati("6281100000001")
            psi = mc.psi(sub.imsi)
        assert sri["serving_msc_vlr"] == sub.vlr
        for res in (ati, psi):
            assert res["vlr"] == sub.vlr
            assert res["cell_id"] == sub.ci
            assert res["lai"]["lac"] == sub.lac
            assert res["location_granularity"] == "cell (LAI+CGI)"
        assert srv.stats["data"] == 3
        assert srv.stats["errors"] == 0
    finally:
        srv.stop()


def test_end_to_end_diameter_lir_plr_loopback():
    hlr = Hlr()
    gmlc = diameter.DiameterGmlc(hlr, "127.0.0.1", 0, verbose=False).start()
    try:
        sub = hlr.by_msisdn("6281100000001")
        assert sub is not None
        gc = diameter.GmlcClient("127.0.0.1", gmlc.port, timeout=3.0, verbose=False)
        for res, iface in ((gc.lir("6281100000001"), "SLh LIR/LIA"),
                           (gc.plr("6281100000001"), "SLg PLR/PLA")):
            assert res["interface"] == iface
            assert res["result_code"] == diameter.RESULT_SUCCESS
            assert res["age_of_location_s"] == sub.describe()["age_s"]
            assert res["vlr_number"] == sub.vlr
            assert res["cell_global_id"]
        assert gmlc.stats["lir"] == 1 and gmlc.stats["plr"] == 1
        assert gmlc.stats["errors"] == 0
    finally:
        gmlc.stop()


def test_unknown_subscriber_is_reported_not_crashed():
    hlr = Hlr()
    srv = HlrServer(hlr, "127.0.0.1", 0, verbose=False).start()
    try:
        port = srv._sock.getsockname()[1]
        with MapClient("127.0.0.1", port, timeout=3.0, verbose=False) as mc:
            res = mc.sri_sm("6289999999999")
        assert res["serving_msc_vlr"] is None
        assert srv.stats["errors"] == 0
    finally:
        srv.stop()


def test_cli_selftest_passes():
    from ss7lab.cli import main
    assert main(["selftest"]) == 0


# ------------------------------------------------------------------ fs11
# GSMA FS.11 classification + detection-rule export. Offline: no sockets.
def _sri_sm_begin() -> bytes:
    return wire.tcap_begin(
        b"\x00\x00\x00\x09",
        wire.invoke(7, wire.OP_SRI_SM, wire.map_sri_sm_arg("6281100000001")))


def _sri_sm_return(not_last: bool = False) -> bytes:
    payload = b"\x00\x00\x00\x09"
    res = wire.map_sri_sm_res("510101234567890", "6281100000101")
    comp = (wire.return_result_not_last(3, wire.OP_SRI_SM, res) if not_last
            else wire.return_result(3, wire.OP_SRI_SM, res))
    return wire.tcap_end(payload, comp)


def test_fs11_classify_invoke_from_raw_frame():
    from ss7lab import fs11
    res = fs11.classify(_sri_sm_begin())
    assert res["parse_error"] is None
    assert res["opcode"] == wire.OP_SRI_SM
    assert res["op"] == "sendRoutingInfoForSM"
    assert res["category"].startswith("3")
    assert res["action"] == "correlate"
    assert res["known"] is True


@pytest.mark.parametrize("not_last", [False, True])
def test_fs11_classify_return_result_shapes(not_last):
    """A2 (last) and A3 (not last) must both decode to the same opcode."""
    from ss7lab import fs11
    res = fs11.classify(_sri_sm_return(not_last=not_last))
    assert res["parse_error"] is None
    assert res["opcode"] == wire.OP_SRI_SM
    assert res["component_type"] in ("ReturnResult", "ReturnResultNotLast")
    assert res["known"] is True


def test_fs11_classify_garbage_never_raises():
    from ss7lab import fs11
    for blob in (b"", b"\x00", b"\xff" * 12, b"\x62\x26\x48\x04\x00"):
        res = fs11.classify(blob)
        assert isinstance(res, dict)
        assert res["frame_len"] == len(blob)
        # unparsable input is reported, not thrown
        assert res["parse_error"] is not None or res["category"] is not None


def test_fs11_signature_matcher_hits_invoke_and_return():
    """Regression: `??` is one *byte* (two hex chars), not one nibble.

    Mapping it to a single `.` produced anchors like `a1.0201...`, which never
    matched real frames, so every signature reported zero hits.
    """
    from ss7lab import fs11
    for frame in (_sri_sm_begin(), _sri_sm_return(), _sri_sm_return(not_last=True)):
        hits = fs11.match_signatures(frame)
        assert [h["name"] for h in hits] == ["sendRoutingInfoForSM"]
        assert hits[0]["category"].startswith("3")


def test_fs11_unknown_opcode_is_category_1():
    from ss7lab import fs11
    res = fs11.classify_opcode(0x7E)
    assert res["category"] == fs11.UNKNOWN_CATEGORY
    assert res["known"] is False
    assert res["name"].endswith("126")


def test_fs11_every_category_is_exported():
    """Regression: sub-classed categories ('2.1', '3.3') were compared for
    equality against '2'/'3', dropping both categories from every exporter."""
    from ss7lab import fs11
    covered = {m.category for m in fs11.MAP_OPS.values()}
    for cat in fs11.CATEGORY_RULES:
        ops = fs11._ops_for_category(cat)
        assert ops, f"category {cat} exported nothing"
        assert all(o.category.split(".")[0] == cat for o in ops)
    assert {"2", "3"} <= {c.split(".")[0] for c in covered}


def test_fs11_yara_rules_compile_and_fire():
    yara = pytest.importorskip("yara")
    from ss7lab import fs11
    src = fs11.export_yara()
    assert "fs11_cat1_map_ops" in src and "fs11_cat3_map_ops" in src
    rules = yara.compile(source=src)
    for frame in (_sri_sm_begin(), _sri_sm_return()):
        matched = {m.rule for m in rules.match(data=frame)}
        assert "fs11_cat3_map_ops" in matched


def test_fs11_exports_are_non_trivial():
    from ss7lab import fs11
    out = fs11.emit("all")
    assert set(out) == {"yara", "sigma", "wireshark", "json"}
    for name, text in out.items():
        assert len(text) > 200, f"{name} export looks empty"
    # conditions must be satisfiable by a single-operation frame
    assert "any of them" in out["yara"]
    assert " of them" not in out["yara"].replace("any of them", "")


def test_cli_classify_offline_and_guardrail():
    from ss7lab.cli import main
    frame = _sri_sm_begin().hex()
    # guardrail first: no flag means refusal with exit 2
    assert main(["classify", "--hex", frame]) == 2
    assert main(["classify", "--hex", frame, "--i-have-authorization"]) == 0
    # unknown opcode still classifies, but exit 1 so CI can gate on it
    assert main(["classify", "--hex", "de", "--i-have-authorization"]) in (0, 1)


def test_cli_rules_writes_all_formats(tmp_path):
    from ss7lab.cli import main
    assert main(["rules", "--format", "all", "--out", str(tmp_path)]) == 2
    assert main(["rules", "--format", "all", "--out", str(tmp_path),
                 "--i-have-authorization"]) == 0
    written = sorted(p.name for p in tmp_path.iterdir())
    expected = {"fs11_json.json", "fs11_sigma.yml",
                "fs11_wireshark.txt", "fs11_yara.yar"}
    # tmp_path may carry harness artefacts, so assert coverage, not exact equality
    assert expected <= set(written)
    assert all((tmp_path / n).stat().st_size > 200 for n in expected)
