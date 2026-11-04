"""Synthetic HLR/MSC subscriber database.

Fake subscribers only. IMSIs and MSISDNs here are lab fixtures — no real
subscriber data is referenced anywhere in this module.
"""
from __future__ import annotations

import time

from . import wire


class Subscriber:
    __slots__ = ("msisdn", "imsi", "vlr", "mcc", "mnc", "lac", "ci",
                 "age_s", "_last_seen")

    def __init__(self, msisdn: str, imsi: str, vlr: str, mcc: str = "510",
                 mnc: str = "10", lac: int = 0x1A2B, ci: int = 0x0C7A,
                 age_s: int = 0):
        self.msisdn = msisdn
        self.imsi = imsi
        self.vlr = vlr
        self.mcc = mcc
        self.mnc = mnc
        self.lac = lac
        self.ci = ci
        self.age_s = age_s
        self._last_seen = time.time()

    def touch(self, *, lac: int | None = None, ci: int | None = None) -> None:
        self._last_seen = time.time()
        if lac is not None:
            self.lac = lac
        if ci is not None:
            self.ci = ci
        self.age_s = 0

    @property
    def lai_raw(self) -> bytes:
        return wire.encode_lai(self.mcc, self.mnc, self.lac)

    def describe(self) -> dict:
        return {
            "msisdn_masked": _mask(self.msisdn),
            "imsi_masked": _mask(self.imsi),
            "vlr": self.vlr,
            "mcc": self.mcc, "mnc": self.mnc,
            "lac": self.lac, "lac_hex": f"0x{self.lac:04X}",
            "ci": self.ci, "ci_hex": f"0x{self.ci:04X}",
            "age_s": int(time.time() - self._last_seen) + self.age_s,
        }


def _mask(v: str, head: int = 4, tail: int = 2) -> str:
    v = str(v)
    if len(v) <= head + tail:
        return "*" * len(v)
    return v[:head] + "*" * (len(v) - head - tail) + v[-tail:]


DEFAULT_SUBSCRIBERS = [
    Subscriber("6281100000001", "510101234567890", "6281100000101",
               mcc="510", mnc="10", lac=0x1A2B, ci=0x0C7A),
    Subscriber("6281100000002", "510101234567891", "6281100000102",
               mcc="510", mnc="10", lac=0x1A2C, ci=0x0C9B),
    Subscriber("6281100000003", "510101234567892", "6281100000103",
               mcc="510", mnc="89", lac=0x2F10, ci=0x1A03),
]


class Hlr:
    def __init__(self, subscribers: list[Subscriber] | None = None):
        self._by_msisdn: dict[str, Subscriber] = {}
        self._by_imsi: dict[str, Subscriber] = {}
        for sub in (subscribers if subscribers is not None else list(DEFAULT_SUBSCRIBERS)):
            self.add(sub)

    def add(self, sub: Subscriber) -> None:
        self._by_msisdn[_norm(sub.msisdn)] = sub
        self._by_imsi[sub.imsi] = sub

    def by_msisdn(self, msisdn: str) -> Subscriber | None:
        return self._by_msisdn.get(_norm(msisdn))

    def by_imsi(self, imsi: str) -> Subscriber | None:
        return self._by_imsi.get(imsi)

    def all(self) -> list[Subscriber]:
        return list(self._msisdn_sorted())

    def _msisdn_sorted(self):
        return [self._by_msisdn[k] for k in sorted(self._by_msisdn)]


def _norm(msisdn: str) -> str:
    d = "".join(ch for ch in str(msisdn) if ch.isdigit())
    if d.startswith("0"):
        d = "62" + d[1:]
    return d
