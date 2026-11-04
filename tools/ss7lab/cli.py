"""ss7lab CLI — synthetic SS7/MAP + Diameter location lab on loopback.

    python3 -m ss7lab selftest                     # codec round trips, no sockets
    python3 -m ss7lab demo                         # full end-to-end, ephemeral ports
    python3 -m ss7lab serve --port 29051           # HLR/MSC sim (blocks)
    python3 -m ss7lab sri-sm 6281100000001 --port 29051
    python3 -m ss7lab ati    6281100000001 --port 29051
    python3 -m ss7lab psi    510101234567890 --port 29051
    python3 -m ss7lab gmlc-serve --port 38681      # GMLC sim (blocks)
    python3 -m ss7lab lir    6281100000001 --port 38681
    python3 -m ss7lab plr    6281100000001 --port 38681
    python3 -m ss7lab classify --hex '62264804000000096c1e...'
    python3 -m ss7lab rules --format all --out ./fs11-rules

Every socket path is loopback: guard.assert_loopback() runs before bind/connect
and refuses anything that resolves outside 127.0.0.0/8 or ::1.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import diameter, guard, wire
from .client import MapClient
from .hlrsim import HlrServer
from .simdb import DEFAULT_SUBSCRIBERS, Hlr


def _out(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


# --------------------------------------------------------------------------
# selftest / demo
# --------------------------------------------------------------------------
def cmd_selftest(_args) -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, bool(cond), detail))

    # TBCD both orders round-trip
    for order in ("lo", "hi"):
        raw = wire.tbcd_encode("628123456789", order)
        back = wire.tbcd_decode(raw, order)
        check(f"tbcd round-trip ({order})", back == "628123456789",
              f"{raw.hex()} -> {back}")
    # odd length padding
    odd = wire.tbcd_encode("12345", "lo")
    check("tbcd odd length pads 0xF", wire.tbcd_decode(odd, "lo") == "12345",
          odd.hex())

    # M3UA header round-trip
    msg = wire.asp_up(asp_id=7)
    cls, typ, params = wire.parse_m3ua(msg)
    check("m3ua ASP_UP parse", cls == wire.CLS_ASPSM and typ == wire.ASPSM_UP,
          f"cls={cls} typ={typ} params={len(params)}B")
    check("m3ua length is 8+params", len(msg) == 8 + len(params), f"{len(msg)}B")

    # SCCP UDT round-trip
    udt = wire.sccp_udt(wire.sccp_addr_pc(wire.SSN_HLR, 0x0001),
                        wire.sccp_addr_pc(wire.SSN_MSC, 0x0002),
                        b"\xde\xad")
    parsed = wire.parse_sccp(udt)
    check("sccp called ssn/pc",
          parsed["called"]["ssn"] == wire.SSN_HLR and parsed["called"]["pc"] == 1,
          json.dumps(parsed["called"]))
    check("sccp calling pc", parsed["calling"]["pc"] == 2, json.dumps(parsed["calling"]))
    check("sccp payload intact", parsed["data"] == b"\xde\xad", parsed["data"].hex())

    # SCCP route-on-GT
    gt_addr = wire.sccp_addr_gt(wire.SSN_HLR, "6281100000101", "lo")
    gt_parsed, _ = wire.parse_sccp_addr(wire.sccp_udt(gt_addr, gt_addr, b"")[2:], 0)
    check("sccp GT ssn", gt_parsed["ssn"] == wire.SSN_HLR, json.dumps(gt_parsed))

    # TCAP positional invoke parse (invokeID and opcode share tag 0x02)
    begin = wire.tcap_begin(b"\x00\x00\x00\x09",
                            wire.invoke(7, wire.OP_ATI, wire.map_ati_arg("6281100000001")))
    dec = wire.decode_tcap(begin)
    comp = dec.get("component") or {}
    check("tcap Begin kind", dec["kind"] == "Begin", dec["kind"])
    check("tcap invoke_id != opcode (positional)",
          comp.get("invoke_id") == 7 and comp.get("opcode") == wire.OP_ATI,
          f"id={comp.get('invoke_id')} op={comp.get('opcode')}")

    # MAP SRI-SM arg/res
    res = wire.map_sri_sm_res("510101234567890", "6281100000101")
    d = wire.decode_sri_sm_res(res)
    check("map sri-sm res imsi", d["imsi"] == "510101234567890", str(d["imsi"]))
    check("map sri-sm res vlr", d["network_node"] == "6281100000101",
          str(d["network_node"]))

    # MAP subscriber info (LAI + CGI + age)
    lai = wire.encode_lai("510", "10", 0x1A2B)
    sub = wire.map_subscriber_info("510101234567890", age_s=42,
                                   vlr="6281100000101", lai_raw=lai, ci=0x0C7A)
    si = wire.decode_subscriber_info(sub)
    check("map subinfo age", si["age_s"] == 42, str(si["age_s"]))
    check("map subinfo ci", si["ci"] == 0x0C7A, str(si["ci"]))
    check("map subinfo lai", (si["lai"] or {}).get("mcc") == "510"
          and (si["lai"] or {}).get("lac") == 0x1A2B, str(si["lai"]))
    check("map subinfo vlr", si["vlr"] == "6281100000101", str(si["vlr"]))

    # Diameter message round-trip
    avps = (diameter.avp_str(diameter.AVP_SESSION_ID, "lab;1") +
            diameter.avp_u32(diameter.AVP_RESULT_CODE, diameter.RESULT_SUCCESS) +
            diameter.avp(diameter.AVP_IMSI, b"510101234567890",
                         vendor=diameter.AVP_VENDOR_3GPP))
    dm = diameter.diameter(diameter.CMD_LIR_LIA, diameter.APP_SLH, avps, request=True)
    pd = diameter.parse_diameter(dm)
    names = [a["avp"] for a in pd["avps"]]
    check("diameter length matches", pd["length"] == len(dm), f"{pd['length']}/{len(dm)}")
    check("diameter flags request", pd["is_request"] is True, str(pd["flags"]))
    check("diameter avps decoded",
          names == ["Session-Id", "Result-Code", "IMSI"], str(names))
    check("diameter vendor carried",
          [a["vendor"] for a in pd["avps"]][-1] == diameter.AVP_VENDOR_3GPP,
          str([a["vendor"] for a in pd["avps"]]))

    # guardrails
    for host in ("127.0.0.1", "localhost", "::1"):
        try:
            guard.assert_loopback(host)
            ok = True
        except guard.GuardrailViolation:
            ok = False
        check(f"guard allow {host}", ok)
    for host in ("0.0.0.0", "8.8.8.8", "example.com", "192.168.1.10"):
        try:
            guard.assert_loopback(host)
            blocked = False
        except guard.GuardrailViolation:
            blocked = True
        check(f"guard deny {host}", blocked)

    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if not ok else ""))
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


def cmd_demo(args) -> int:
    hlr = Hlr()
    hlr_srv = HlrServer(hlr, "127.0.0.1", args.port, verbose=False).start()
    gmlc = diameter.DiameterGmlc(hlr, "127.0.0.1", args.dport, verbose=False).start()
    msisdn = args.msisdn
    sub = hlr.by_msisdn(msisdn)
    imsi = sub.imsi if sub is not None else None
    results: dict[str, object] = {"hlr_bind": f"127.0.0.1:{args.port}",
                                  "gmlc_bind": f"127.0.0.1:{args.dport}"}
    try:
        with MapClient("127.0.0.1", args.port, verbose=False) as mc:
            results["sri_sm"] = mc.sri_sm(msisdn)
            results["ati"] = mc.ati(msisdn)
            if imsi:
                results["psi"] = mc.psi(imsi)
        gc = diameter.GmlcClient("127.0.0.1", args.dport, verbose=False)
        results["slh_lir"] = gc.lir(msisdn)
        results["slg_plr"] = gc.plr(msisdn)
        results["hlr_stats"] = hlr_srv.stats
        results["gmlc_stats"] = gmlc.stats
    finally:
        hlr_srv.stop()
        gmlc.stop()
    _out(results)
    return 0


# --------------------------------------------------------------------------
# server / client commands
# --------------------------------------------------------------------------
def cmd_serve(args) -> int:
    srv = HlrServer(Hlr(), args.host, args.port)
    print(json.dumps({"listening": f"{srv.host}:{srv.port}",
                      "pc": f"0x{srv.pc:04X}",
                      "subscribers": [s.describe() for s in srv.hlr.all()],
                      "socket": "SCTP/SEQPACKET one-to-one",
                      "guard": "loopback-only enforced by assert_loopback()"}),
          flush=True)
    srv.serve_forever()
    return 0


def cmd_gmlc_serve(args) -> int:
    g = diameter.DiameterGmlc(Hlr(), args.host, args.port)
    g.start(background=True)
    print(json.dumps({"listening": f"{g.host}:{g.port}",
                      "interfaces": ["SLh LIR/LIA (16777291)",
                                     "SLg PLR/PLA (16777255)"],
                      "socket": "TCP/Diameter",
                      "guard": "loopback-only enforced by assert_loopback()"}),
          flush=True)
    try:
        while True:
            import time as _t
            _t.sleep(1)
    except KeyboardInterrupt:
        g.stop()
    return 0


def _client_common(args) -> dict:
    return {"host": args.host, "port": args.port, "order": args.tbcd_order}


def cmd_sri_sm(args) -> int:
    with MapClient(args.host, args.port, order=args.tbcd_order,
                   timeout=args.timeout) as mc:
        res = mc.sri_sm(args.msisdn)
    res["trace"] = mc.trace
    _out(res)
    return 0


def cmd_ati(args) -> int:
    with MapClient(args.host, args.port, order=args.tbcd_order,
                   timeout=args.timeout) as mc:
        res = mc.ati(args.msisdn)
    res["trace"] = mc.trace
    _out(res)
    return 0


def cmd_psi(args) -> int:
    with MapClient(args.host, args.port, order=args.tbcd_order,
                   timeout=args.timeout) as mc:
        res = mc.psi(args.imsi)
    res["trace"] = mc.trace
    _out(res)
    return 0


def cmd_lir(args) -> int:
    gc = diameter.GmlcClient(args.host, args.port, timeout=args.timeout)
    res = gc.lir(args.msisdn)
    res["trace"] = gc.trace
    _out(res)
    return 0


def cmd_plr(args) -> int:
    gc = diameter.GmlcClient(args.host, args.port, timeout=args.timeout)
    res = gc.plr(args.msisdn)
    res["trace"] = gc.trace
    _out(res)
    return 0


def cmd_classify(args) -> int:
    """FS.11 classification of one raw frame, straight off the wire."""
    from . import fs11

    if args.hex:
        try:
            blob = bytes.fromhex(args.hex.replace(" ", "").replace(":", ""))
        except ValueError as e:
            raise ValueError(f"--hex is not valid hex: {e}") from e
    else:
        with open(args.file, "rb") as fh:
            blob = fh.read()
    if not blob:
        raise ValueError("empty frame: nothing to classify")

    res = fs11.classify(blob, tbcd_order=args.tbcd_order)
    res["hits"] = [{"name": h["name"], "kind": h["kind"], "category": h["category"]}
                   for h in fs11.match_signatures(blob)]
    res["input"] = {"source": "--hex" if args.hex else args.file,
                    "bytes": len(blob), "hex": blob.hex()}
    _out(res)
    # 0 when the frame is a known MAP op, 1 otherwise, so CI can gate on it
    return 0 if res.get("known") else 1


def cmd_rules(args) -> int:
    """Write the FS.11 detection rules (YARA / Sigma / display filters / JSON)."""
    from . import fs11

    payload = fs11.emit(args.format)
    written = {}
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        for name, text in payload.items():
            path = os.path.join(args.out, f"fs11_{name}{fs11.EXTENSIONS[name]}")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text if text.endswith("\n") else text + "\n")
            written[name] = path
        _out({"written": written, "summary": fs11.summary()})
    else:
        for name, text in payload.items():
            print(f"# ===== {name} =====")
            print(text)
    return 0


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m ss7lab",
        description="Synthetic SS7/MAP + Diameter SLh/SLg location lab (loopback only).")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("selftest", help="codec round trips, no sockets")
    s.set_defaults(func=cmd_selftest)

    d = sub.add_parser("demo", help="end-to-end: SCTP MAP + Diameter, ephemeral ports")
    d.add_argument("--msisdn", default="6281100000001")
    d.add_argument("--port", type=int, default=29071, help="MAP/SCTP port")
    d.add_argument("--dport", type=int, default=38691, help="Diameter port")
    d.set_defaults(func=cmd_demo)

    sv = sub.add_parser("serve", help="HLR/MSC simulator (blocks)")
    _common(sv)
    sv.set_defaults(func=cmd_serve)

    gs = sub.add_parser("gmlc-serve", help="GMLC simulator (blocks)")
    _common(gs)
    gs.set_defaults(func=cmd_gmlc_serve)

    for name, helptext, func in (
            ("sri-sm", "sendRoutingInfoForSM -> IMSI + serving MSC/VLR", cmd_sri_sm),
            ("ati", "anyTimeInterrogation -> LAI + CGI + age", cmd_ati),
            ("psi", "provideSubscriberInfo -> LAI + CGI + age", cmd_psi),
            ("lir", "SLh LCS-Routing-Info -> routing info", cmd_lir),
            ("plr", "SLg Provide-Location -> routing info", cmd_plr)):
        sp = sub.add_parser(name, help=helptext)
        _common(sp)
        if name == "psi":
            sp.add_argument("imsi")
        else:
            sp.add_argument("msisdn")
        sp.set_defaults(func=func)

    cl = sub.add_parser("classify", help="FS.11 category for one raw frame (offline)")
    cl.add_argument("--hex", default=None, help="frame as hex, e.g. '6226480400...'")
    cl.add_argument("--file", default=None, help="frame from a binary file instead")
    cl.add_argument("--tbcd-order", choices=("lo", "hi"), default="lo")
    cl.set_defaults(func=cmd_classify)

    rl = sub.add_parser("rules", help="emit YARA / Sigma / tshark / JSON rules (offline)")
    rl.add_argument("--format", default="all",
                    choices=("all", "yara", "sigma", "wireshark", "json"))
    rl.add_argument("--out", default=None, help="write files into this directory")
    rl.set_defaults(func=cmd_rules)

    for sp in [a for a in sub.choices.values() if a.prog.endswith(tuple(
            ["serve", "gmlc-serve", "sri-sm", "ati", "psi", "lir", "plr", "demo",
             "classify", "rules"]))]:
        sp.add_argument("--i-have-authorization", dest="authorized", action="store_true",
                        help="required: confirms lab-only operation on loopback")
    return p


def _common(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=2905)
    sp.add_argument("--tbcd-order", choices=("lo", "hi"), default="lo",
                    help="TBCD nibble order (3GPP TS 23.003 says 'lo')")
    sp.add_argument("--timeout", type=float, default=5.0)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "selftest":
        return cmd_selftest(args)
    try:
        # both guardrail shapes (missing flag, non-loopback host) must exit 2,
        # so the authorization check lives inside the same handler
        guard.require_authorization(getattr(args, "authorized", False),
                                    f"ss7lab {args.cmd}")
        return int(args.func(args) or 0)
    except guard.GuardrailViolation as e:
        print(f"GuardrailViolation: {e}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TimeoutError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
