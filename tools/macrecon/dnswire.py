"""Minimal DNS wire-format encoder/decoder for mDNS / DNS-SD (stdlib only).

Only what DNS-SD needs: build a PTR/ANY question, parse A/AAAA/PTR/SRV/TXT
answers including name compression pointers.
"""

from __future__ import annotations

import struct

TYPE_A = 1
TYPE_AAAA = 28
TYPE_PTR = 12
TYPE_TXT = 16
TYPE_SRV = 33
TYPE_ANY = 255

TYPE_NAMES = {TYPE_A: "A", TYPE_AAAA: "AAAA", TYPE_PTR: "PTR", TYPE_TXT: "TXT", TYPE_SRV: "SRV", 2: "NS", 5: "CNAME", 6: "SOA", 41: "OPT"}

CLASS_IN = 1
UNICAST_RESPONSE_BIT = 0x8000

SERVICE_ENUM = "_services._dns-sd._udp.local"


class DNSError(Exception):
    pass


def encode_name(name: str) -> bytes:
    out = bytearray()
    if name.endswith("."):
        name = name[:-1]
    for label in name.split("."):
        if not label:
            continue
        raw = label.encode("utf-8")
        if len(raw) > 63:
            raise DNSError(f"label too long: {label!r}")
        out.append(len(raw))
        out.extend(raw)
    out.append(0)
    return bytes(out)


def build_query(name: str, qtype: int = TYPE_ANY, unicast: bool = True, txid: int = 0) -> bytes:
    """Build a single-question DNS query. `unicast=True` sets the mDNS QU bit."""
    qclass = CLASS_IN | (UNICAST_RESPONSE_BIT if unicast else 0)
    header = struct.pack(">HHHHHH", txid, 0, 1, 0, 0, 0)
    return header + encode_name(name) + struct.pack(">HH", qtype, qclass)


def _decode_name(data: bytes, offset: int, depth: int = 0) -> tuple[str, int]:
    """Decode a (possibly compressed) name; returns (name, offset_after_name)."""
    if depth > 10:
        raise DNSError("compression pointer loop")
    labels: list[str] = []
    jumped = False
    consumed_end = offset
    while True:
        if offset >= len(data):
            raise DNSError("truncated name")
        length = data[offset]
        if length == 0:
            offset += 1
            if not jumped:
                consumed_end = offset
            break
        if length & 0xC0 == 0xC0:  # pointer
            if offset + 1 >= len(data):
                raise DNSError("truncated pointer")
            ptr = struct.unpack(">H", data[offset:offset + 2])[0] & 0x3FFF
            if not jumped:
                consumed_end = offset + 2
            jumped = True
            offset = ptr
            continue
        offset += 1
        raw = data[offset:offset + length]
        if len(raw) != length:
            raise DNSError("truncated label")
        labels.append(raw.decode("utf-8", "replace"))
        offset += length
        if not jumped:
            consumed_end = offset
    return ".".join(labels) + ".", consumed_end


def _decode_rdata(data: bytes, rtype: int, rdlength: int, rdata_off: int):
    if rtype == TYPE_A:
        if rdlength != 4:
            return None
        return ".".join(str(b) for b in data[rdata_off:rdata_off + 4])
    if rtype == TYPE_AAAA:
        if rdlength != 16:
            return None
        chunks = [data[rdata_off + i:rdata_off + i + 2].hex() for i in range(0, 16, 2)]
        return ":".join(chunks)
    if rtype in (TYPE_PTR, 2, 5):
        name, _ = _decode_name(data, rdata_off)
        return name
    if rtype == TYPE_SRV:
        if rdlength < 7:
            return None
        prio, weight, port = struct.unpack(">HHH", data[rdata_off:rdata_off + 6])
        target, _ = _decode_name(data, rdata_off + 6)
        return {"priority": prio, "weight": weight, "port": port, "target": target}
    if rtype == TYPE_TXT:
        items: list[str] = []
        i = rdata_off
        end = rdata_off + rdlength
        while i < end:
            ln = data[i]
            i += 1
            if ln == 0:
                continue
            items.append(data[i:i + ln].decode("utf-8", "replace"))
            i += ln
        return items
    return data[rdata_off:rdata_off + rdlength].hex()


def parse_message(data: bytes) -> dict:
    """Parse a DNS response into questions + answer records."""
    if len(data) < 12:
        raise DNSError("short message")
    txid, flags, qd, an, ns, ar = struct.unpack(">HHHHHH", data[:12])
    offset = 12
    questions = []
    for _ in range(qd):
        name, offset = _decode_name(data, offset)
        if offset + 4 > len(data):
            raise DNSError("truncated question")
        qtype, qclass = struct.unpack(">HH", data[offset:offset + 4])
        offset += 4
        questions.append({"name": name, "type": qtype, "class": qclass & 0x7FFF})

    records = []
    for _ in range(an + ns + ar):
        if offset >= len(data):
            break
        name, offset = _decode_name(data, offset)
        if offset + 10 > len(data):
            raise DNSError("truncated record header")
        rtype, rclass, ttl, rdlength = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        rdata_off = offset
        value = _decode_rdata(data, rtype, rdlength, rdata_off)
        offset += rdlength
        records.append({
            "name": name,
            "type": TYPE_NAMES.get(rtype, str(rtype)),
            "type_id": rtype,
            "class": rclass & 0x7FFF,
            "ttl": ttl,
            "value": value,
        })
    return {
        "txid": txid,
        "flags": flags,
        "questions": questions,
        "records": records,
    }
