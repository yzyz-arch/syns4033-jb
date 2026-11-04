"""Synthetic HLR/MSC over M3UA -> SCCP -> TCAP -> MAP on SCTP loopback.

Handles the three ops that carry location in MAP:
  * sendRoutingInfoForSM (45)  -> IMSI + serving MSC/VLR number (coarse)
  * anyTimeInterrogation  (71) -> LAI + CGI + VLR + age (cell-level)
  * provideSubscriberInfo (70) -> same payload, PSI shape (LCS client path)

Server binds loopback only; guard.assert_loopback() runs before bind().
"""
from __future__ import annotations

import json
import socket
import struct
import threading
import time

from . import guard, wire
from .simdb import Hlr

DEFAULT_SSN_CALLING = wire.SSN_MSC
DEFAULT_SSN_CALLED = wire.SSN_HLR
DEFAULT_PC_HLR = 0x0001
DEFAULT_PC_MSC = 0x0002


class HlrServer:
    """One ASP, one route context, one MAP dispatcher."""

    def __init__(self, hlr: Hlr, host: str = "127.0.0.1", port: int = 2905,
                 *, pc: int = DEFAULT_PC_HLR, order: str = "lo",
                 verbose: bool = True):
        self.hlr = hlr
        self.host = guard.assert_loopback(host)
        self.port = int(port)
        self.pc = pc
        self.order = order
        self.verbose = verbose
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.stats = {"asp_up": 0, "asp_active": 0, "data": 0,
                      "sri_sm": 0, "ati": 0, "psi": 0, "errors": 0,
                      "unknown_op": 0}
        self.log: list[dict] = []

    # -- lifecycle ---------------------------------------------------------
    def start(self, *, background: bool = True) -> "HlrServer":
        self._sock = wire.listen_xua(self.host, self.port)
        if background:
            self._thread = threading.Thread(target=self._serve, daemon=True,
                                            name="ss7lab-hlr")
            self._thread.start()
        return self

    def serve_forever(self) -> None:
        if self._sock is None:
            self._sock = wire.listen_xua(self.host, self.port)
        self._serve()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _serve(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                payload, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                reply = self._dispatch(payload, addr)
            except Exception as e:                       # keep the lab alive
                self.stats["errors"] += 1
                self._log({"error": f"{type(e).__name__}: {e}"})
                continue
            if reply:
                try:
                    wire.send_xua(self._sock, reply, addr)
                except OSError as e:
                    self._log({"error": f"send failed: {e}"})

    # -- M3UA/SCCP/TCAP ----------------------------------------------------
    def _dispatch(self, payload: bytes, addr) -> bytes | None:
        cls, typ, params = wire.parse_m3ua(payload)
        if cls == wire.CLS_ASPSM and typ == wire.ASPSM_UP:
            self.stats["asp_up"] += 1
            self._log({"m3ua": "ASP_UP", "peer": f"{addr[0]}:{addr[1]}"})
            return wire.asp_up_ack()
        if cls == wire.CLS_ASPTM and typ == wire.ASPTM_ACTIVE:
            self.stats["asp_active"] += 1
            self._log({"m3ua": "ASP_ACTIVE"})
            return wire.asp_active_ack()
        if cls == wire.CLS_XFER and typ == wire.XFER_DATA:
            self.stats["data"] += 1
            for tag, value in wire.parse_params(params):
                if tag == wire.IEI_PROT_DATA:
                    sccp = wire.parse_sccp(value)
                    reply = self._handle_map(sccp)
                    if reply:
                        return wire.m3ua_data(reply, rc=0, orig_pc=self.pc)
            return None
        if cls == wire.CLS_ASPSM and typ == wire.ASPSM_DOWN:
            return wire.m3ua(wire.CLS_ASPSM, wire.ASPSM_DOWN_ACK)
        return None

    def _handle_map(self, sccp: dict) -> bytes | None:
        tcap = wire.decode_tcap(sccp["data"])
        comp = tcap.get("component") or {}
        op = comp.get("opcode")
        inv = comp.get("invoke_id")
        arg = comp.get("param") or b""

        if op == wire.OP_SRI_SM:
            self.stats["sri_sm"] += 1
            res, meta = self._sri_sm(arg)
        elif op == wire.OP_ATI:
            self.stats["ati"] += 1
            res, meta = self._subscriber_info(arg, kind="ATI")
        elif op == wire.OP_PSI:
            self.stats["psi"] += 1
            res, meta = self._subscriber_info(arg, kind="PSI")
        else:
            self.stats["unknown_op"] += 1
            self._log({"unknown_op": op})
            return None

        self._log({"op": {45: "SRI-SM", 71: "ATI", 70: "PSI"}.get(op, op),
                   "invoke_id": inv, **meta})
        component = wire.return_result(inv or 0, op, res)
        return wire.sccp_udt(sccp["calling_raw"], sccp["called_raw"],
                             wire.tcap_end(tcap.get("otid") or b"\x00", component))

    # -- MAP operation bodies ---------------------------------------------
    def _sri_sm(self, arg: bytes):
        msisdn = None
        # arg arrives as the full SEQUENCE wrapper: 30 <len> { 80 <msisdn> ... }
        for tag, value in wire.parse_all(wire.unwrap_seq(arg)):
            if tag == 0x80:
                msisdn = wire.tbcd_decode(value, self.order)
                break
        sub = self.hlr.by_msisdn(msisdn or "")
        if sub is None:
            return (wire.tlv(0x30, wire.tlv(0x80, b"")), {"msisdn": msisdn,
                                                         "result": "unknown_subscriber"})
        res = wire.map_sri_sm_res(sub.imsi, sub.vlr, self.order)
        return (res, {"msisdn": msisdn, "imsi": sub.imsi, "vlr": sub.vlr})

    def _subscriber_info(self, arg: bytes, *, kind: str):
        imsi = msisdn = None
        for tag, value in wire.parse_all(wire.unwrap_seq(arg)):
            if tag == 0x80:                     # PSI: imsi at [0]
                imsi = wire.tbcd_decode(value, self.order)
            elif tag == 0xA0:                   # ATI: subscriberIdentity [0] -> msisdn [1]
                for t2, v2 in wire.parse_all(wire.unwrap_seq(value)):
                    if t2 == 0x81:
                        msisdn = wire.tbcd_decode(v2, self.order)
        sub = self.hlr.by_msisdn(msisdn) if msisdn else self.hlr.by_imsi(imsi or "")
        if sub is None:
            return (wire.tlv(0x30, b""), {"imsi": imsi, "msisdn": msisdn,
                                          "result": "unknown_subscriber"})
        sub.touch()
        res = wire.map_subscriber_info(
            sub.imsi, age_s=sub.describe()["age_s"], vlr=sub.vlr,
            lai_raw=sub.lai_raw, ci=sub.ci, order=self.order)
        return (res, {"kind": kind, "imsi": sub.imsi, "msisdn": msisdn,
                      "lai": f"{sub.mcc}-{sub.mnc}-{sub.lac}",
                      "ci": sub.ci})

    # -- logging -----------------------------------------------------------
    def _log(self, entry: dict) -> None:
        entry = {"t": round(time.time(), 3), **entry}
        self.log.append(entry)
        if self.verbose:
            print("[hlr] " + json.dumps(entry, default=str), flush=True)

    def summary(self) -> dict:
        return {"pc": f"0x{self.pc:04X}", "ssn": DEFAULT_SSN_CALLED,
                "bind": f"{self.host}:{self.port}", "stats": dict(self.stats)}
