"""Loopback enforcement + authorization gate for ss7lab.

Every socket in this package binds or connects through `assert_loopback()`.
The lab speaks SCTP/Diameter to 127.0.0.1 only; there is no carrier path here
and no code path that can reach an STP, HLR or GMLC that is not this process.
"""
from __future__ import annotations

import ipaddress
import socket


class GuardrailViolation(RuntimeError):
    pass


def assert_loopback(host: str) -> str:
    if host is None or not str(host).strip():
        raise GuardrailViolation("empty host")
    h = str(host).strip()
    try:
        infos = socket.getaddrinfo(h, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise GuardrailViolation(f"{h!r} does not resolve: {e}") from e
    ips = {str(i[4][0]) for i in infos}
    for ip in ips:
        if not ipaddress.ip_address(ip.split("%")[0]).is_loopback:
            raise GuardrailViolation(
                f"{h!r} resolves to non-loopback {ip} — ss7lab is loopback only")
    return sorted(ips)[0]


def require_authorization(flag: bool, what: str) -> None:
    if not flag:
        raise GuardrailViolation(
            f"{what} refused: pass --i-have-authorization to confirm this runs "
            f"against the lab on loopback only")
