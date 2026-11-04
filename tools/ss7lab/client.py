"""MAP client: build SRI-SM / ATI / PSI requests, send over M3UA, decode replies.

Talks to an HLR/STP on loopback only (guard.assert_loopback before connect).
"""
from __future__ import annotations

import itertools
import struct
import time

from . import guard, wire

_OTID = itertools.count(1)


class MapClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 2905, *,
                 pc: int = 0x0002, order: str = "lo", timeout: float = 5.0,
                 verbose: bool = True):
        self.host = guard.assert_loopback(host)
        self.port = int(port)
        self.pc = pc
        self.order = order
        self.timeout = timeout
        self.verbose = verbose
        self._sock = None
        self.trace: list[str] = []

    # -- transport ---------------------------------------------------------
    def __enter__(self) -> "MapClient":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def connect(self) -> None:
        self._sock = wire.open_xua(self.host, self.port, timeout=self.timeout)
        self._send(wire.asp_up(), "ASP_UP")
        cls, typ, _ = wire.parse_m3ua(self._recv())
        if not (cls == wire.CLS_ASPSM and typ == wire.ASPSM_UP_ACK):
            raise RuntimeError(f"expected ASP_UP_ACK, got cls={cls} typ={typ}")
        self._send(wire.asp_active(), "ASP_ACTIVE")
        cls, typ, _ = wire.parse_m3ua(self._recv())
        if not (cls == wire.CLS_ASPTM and typ == wire.ASPTM_ACTIVE_ACK):
            raise RuntimeError(f"expected ASP_ACTIVE_ACK, got cls={cls} typ={typ}")

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _send(self, data: bytes, label: str) -> None:
        assert self._sock is not None
        wire.send_xua(self._sock, data, (self.host, self.port))
        self._trace(label, data)

    def _recv(self) -> bytes:
        assert self._sock is not None
        data, _addr = self._sock.recvfrom(65535)
        self._trace("RX", data)
        return data

    def _trace(self, label: str, data: bytes) -> None:
        line = f"{label} {len(data)}B {data[:48].hex()}"
        self.trace.append(line)
        if self.verbose:
            print(f"[map] {line}", flush=True)

    # -- operations --------------------------------------------------------
    def _transact(self, opcode: int, arg: bytes) -> bytes:
        otid = struct.pack(">I", next(_OTID))
        payload = wire.tcap_begin(otid, wire.invoke(1, opcode, arg))
        sccp = wire.sccp_udt(
            wire.sccp_addr_pc(wire.SSN_HLR, 0x0001),
            wire.sccp_addr_pc(wire.SSN_MSC, self.pc),
            payload)
        self._send(wire.m3ua_data(sccp, orig_pc=self.pc, dest_pc=0x0001),
                   f"MAP op{opcode}")

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            cls, typ, params = wire.parse_m3ua(self._recv())
            if cls != wire.CLS_XFER or typ != wire.XFER_DATA:
                continue
            for tag, value in wire.parse_params(params):
                if tag != wire.IEI_PROT_DATA:
                    continue
                inner = wire.parse_sccp(value)
                tcap = wire.decode_tcap(inner["data"])
                comp = tcap.get("component") or {}
                if comp.get("opcode") == opcode:
                    return comp.get("param") or b""
        raise TimeoutError(f"no MAP reply for op {opcode} within {self.timeout}s")

    def sri_sm(self, msisdn: str, sc_address: str = "628110000000") -> dict:
        res = self._transact(wire.OP_SRI_SM,
                             wire.map_sri_sm_arg(msisdn, sc_address, self.order))
        out = wire.decode_sri_sm_res(res, self.order)
        return {"op": "SRI-SM", "msisdn_masked": _mask(msisdn),
                "imsi_masked": _mask(str(out["imsi"] or "")),
                "serving_msc_vlr": out["network_node"],
                "location_granularity": "serving-switch (no cell)",
                "raw_hex": res.hex()}

    def ati(self, msisdn: str, scf: str = "628110000000") -> dict:
        res = self._transact(wire.OP_ATI,
                             wire.map_ati_arg(msisdn, scf, self.order))
        out = wire.decode_subscriber_info(res, self.order)
        return _loc_payload("ATI", msisdn, out, res)

    def psi(self, imsi: str) -> dict:
        arg = wire.tlv(0x30,
                       wire.tlv(0x80, wire.tbcd_encode(imsi, self.order)) +
                       wire.tlv(0xA2, wire.tlv(0x80, b"")))
        res = self._transact(wire.OP_PSI, arg)
        out = wire.decode_subscriber_info(res, self.order)
        return _loc_payload("PSI", None, out, res, imsi=imsi)


def _loc_payload(kind: str, msisdn: str | None, out: dict, raw: bytes,
                 *, imsi: str | None = None) -> dict:
    lai = out.get("lai") or {}
    return {
        "op": kind,
        "msisdn_masked": _mask(msisdn) if msisdn else None,
        "imsi_masked": _mask(str(imsi or out.get("imsi") or "")),
        "vlr": out.get("vlr"),
        "lai": lai,
        "cell_id": out.get("ci"),
        "cell_id_hex": f"0x{out['ci']:04X}" if out.get("ci") is not None else None,
        "age_s": out.get("age_s"),
        "location_granularity": "cell (LAI+CGI)",
        "raw_hex": raw.hex(),
    }


def _mask(v: str, head: int = 4, tail: int = 2) -> str:
    v = str(v)
    if not v:
        return ""
    if len(v) <= head + tail:
        return "*" * len(v)
    return v[:head] + "*" * (len(v) - head - tail) + v[-tail:]
