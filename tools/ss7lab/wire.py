"""Wire codecs: TBCD, M3UA, SCCP, TCAP, MAP.

Constants are taken from the Osmocom headers referenced in the
telecom-signaling-lab skill (m3ua.h / sccp_types.h / sccp_sap.h) and from
3GPP TS 29.002 for the MAP layer.
"""
from __future__ import annotations

import socket
import struct

# --------------------------------------------------------------------------
# transport constants
# --------------------------------------------------------------------------
SOL_SCTP = 132
SCTP_SNDINFO = 2
PPID_M3UA = 3
PPID_RAW = 0x03000000          # kernel copies snd_ppid raw -> wire PPID 0x00000003

M3UA_VERSION = 1
CLS_MGMT, CLS_XFER, CLS_SNM, CLS_ASPSM, CLS_ASPTM = 0, 1, 2, 3, 4
ASPSM_UP, ASPSM_DOWN, ASPSM_BEAT, ASPSM_UP_ACK, ASPSM_DOWN_ACK, ASPSM_BEAT_ACK = 1, 2, 3, 4, 5, 6
ASPTM_ACTIVE, ASPTM_INACTIVE, ASPTM_ACTIVE_ACK, ASPTM_INACTIVE_ACK = 1, 2, 3, 4
XFER_DATA = 1

IEI_ROUTE_CTX = 0x0006
IEI_ASP_ID = 0x0011
IEI_INFO_STRING = 0x0004
IEI_DEST_PC = 0x020B
IEI_ORIG_PC = 0x020E
IEI_PROT_DATA = 0x0210
IEI_CORR_ID = 0x0211

SSN_MAP, SSN_HLR, SSN_VLR, SSN_MSC, SSN_SGSN = 5, 6, 7, 8, 149

# --------------------------------------------------------------------------
# TBCD
# --------------------------------------------------------------------------
# 3GPP TS 23.003 §3.3: "the first digit is stored in the four least significant
# bits of the first octet" -> order="lo".
# NOTE: the telecom-signaling-lab reference page shows the opposite pairing in
# its worked example (+628123456789 -> 62 18 32 ...). Encoding is order
# sensitive, so both are implemented and the caller picks one. Round-trip is
# self-consistent either way; match your capture with --tbcd-order.


def tbcd_encode(digits: str, order: str = "lo") -> bytes:
    d = "".join(ch for ch in str(digits) if ch.isdigit() or ch.upper() in "ABCDEF")
    if not d:
        return b""
    if len(d) % 2:
        d += "F"
    out = bytearray()
    for i in range(0, len(d), 2):
        a, b = int(d[i], 16), int(d[i + 1], 16)
        out.append((a | (b << 4)) if order == "lo" else ((a << 4) | b))
    return bytes(out)


def tbcd_decode(raw: bytes, order: str = "lo") -> str:
    s = []
    for byte in raw:
        hi, lo = (byte >> 4) & 0x0F, byte & 0x0F
        first, second = (lo, hi) if order == "lo" else (hi, lo)
        for nib in (first, second):
            if nib == 0x0F:
                continue
            s.append("%X" % nib)
    return "".join(s)


# --------------------------------------------------------------------------
# M3UA (RFC 4666)
# --------------------------------------------------------------------------
def param(tag: int, value: bytes) -> bytes:
    return struct.pack(">HH", tag, 4 + len(value)) + value


def m3ua(cls: int, typ: int, params: bytes = b"") -> bytes:
    return struct.pack(">BBBBI", M3UA_VERSION, 0, cls, typ, 8 + len(params)) + params


def parse_m3ua(buf: bytes):
    if len(buf) < 8:
        raise ValueError(f"short M3UA message ({len(buf)} bytes)")
    version, _res, cls, typ, length = struct.unpack(">BBBBI", buf[:8])
    if version != M3UA_VERSION:
        raise ValueError(f"bad M3UA version {version}")
    if length < 8 or length > len(buf):
        raise ValueError(f"bad M3UA length {length} (buffer {len(buf)})")
    return cls, typ, buf[8:length]


def parse_params(buf: bytes) -> list[tuple[int, bytes]]:
    out, i = [], 0
    while i + 4 <= len(buf):
        tag, length = struct.unpack(">HH", buf[i:i + 4])
        if length < 4 or i + length > len(buf):
            break
        out.append((tag, buf[i + 4:i + length]))
        i += length
    return out


def asp_up(asp_id: int = 1) -> bytes:
    return m3ua(CLS_ASPSM, ASPSM_UP,
                param(IEI_ASP_ID, struct.pack(">I", asp_id)) +
                param(IEI_INFO_STRING, b"ss7lab"))


def asp_up_ack() -> bytes:
    return m3ua(CLS_ASPSM, ASPSM_UP_ACK, param(IEI_ASP_ID, struct.pack(">I", 1)))


def asp_active(asp_id: int = 1, rc: int = 0) -> bytes:
    return m3ua(CLS_ASPTM, ASPTM_ACTIVE,
                param(IEI_ASP_ID, struct.pack(">I", asp_id)) +
                param(IEI_ROUTE_CTX, struct.pack(">I", rc)))


def asp_active_ack() -> bytes:
    return m3ua(CLS_ASPTM, ASPTM_ACTIVE_ACK,
                param(IEI_ASP_ID, struct.pack(">I", 1)) +
                param(IEI_ROUTE_CTX, struct.pack(">I", 0)))


def m3ua_data(payload: bytes, *, rc: int = 0, orig_pc: int | None = None,
              dest_pc: int | None = None) -> bytes:
    body = param(IEI_ROUTE_CTX, struct.pack(">I", rc))
    if orig_pc is not None:
        body += param(IEI_ORIG_PC, struct.pack(">I", orig_pc))
    if dest_pc is not None:
        body += param(IEI_DEST_PC, struct.pack(">I", dest_pc))
    body += param(IEI_PROT_DATA, payload)
    return m3ua(CLS_XFER, XFER_DATA, body)


# --------------------------------------------------------------------------
# SCTP one-to-one transport
# --------------------------------------------------------------------------
def _sndinfo() -> bytes:
    return struct.pack("=HHIIi", 0, 0, PPID_RAW, 0, 0)


def open_xua(host: str, port: int, timeout: float = 5.0) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_SEQPACKET, socket.IPPROTO_SCTP)
    s.bind((host, 0))
    s.connect((host, port))
    s.settimeout(timeout)
    return s


def listen_xua(host: str, port: int, backlog: int = 8) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_SEQPACKET, socket.IPPROTO_SCTP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(backlog)
    return s


def send_xua(sock: socket.socket, data: bytes, addr) -> int:
    # send()/os.write() raise EPIPE on SEQPACKET SCTP even with the assoc up.
    return sock.sendmsg([data], [(SOL_SCTP, SCTP_SNDINFO, _sndinfo())], 0, addr)


def recv_xua(sock: socket.socket):
    return sock.recvfrom(65535)


# --------------------------------------------------------------------------
# SCCP (Q.713)
# --------------------------------------------------------------------------
SCCP_UDT = 0x09


def sccp_addr_pc(ssn: int, pc: int) -> bytes:
    """Route-on-SSN: AI=0x43, contents = PC(2, LE 14-bit) + SSN."""
    return bytes([3, 0x43, pc & 0xFF, (pc >> 8) & 0x3F, ssn])


def sccp_addr_gt(ssn: int, gt_digits: str, order: str = "lo") -> bytes:
    """Route-on-GT, GTI=4 (international): AI=0x12, contents = SSN + GT."""
    digits = tbcd_encode(gt_digits, order=order)
    gt = bytes([len(digits) + 1, 0x04]) + digits
    body = bytes([ssn]) + gt
    return bytes([len(body), 0x12]) + body


def sccp_udt(called: bytes, calling: bytes, data: bytes) -> bytes:
    return bytes([SCCP_UDT, 0x00]) + called + calling + data


def parse_sccp_addr(buf: bytes, off: int):
    ln, ai = buf[off], buf[off + 1]
    body = buf[off + 2:off + 2 + ln]
    out = {"ai": ai, "ssn": None, "pc": None, "gt": None}
    i = 0
    if ai & 0x01:                      # PC present, 2 octets, first
        out["pc"] = body[i] | ((body[i + 1] & 0x3F) << 8)
        i += 2
    if ai & 0x02:                      # SSN present, 1 octet
        out["ssn"] = body[i]
        i += 1
    if ai & 0x3C:                      # GT present, length-prefixed
        glen = body[i]
        out["gt"] = body[i + 1:i + 1 + glen].hex()
        i += 1 + glen
    return out, off + 2 + ln


def parse_sccp(buf: bytes) -> dict:
    if not buf or buf[0] != SCCP_UDT:
        raise ValueError(f"not SCCP UDT (type {buf[0] if buf else None})")
    called_start = 2
    called, off = parse_sccp_addr(buf, called_start)
    called_raw = buf[called_start:off]
    calling_start = off
    calling, off = parse_sccp_addr(buf, calling_start)
    calling_raw = buf[calling_start:off]
    # raw address octets are kept so a server can echo them back unchanged
    return {"called": called, "calling": calling,
            "called_raw": called_raw, "calling_raw": calling_raw,
            "data": buf[off:]}


# --------------------------------------------------------------------------
# TCAP (Q.771-775) -- DER-style length, positional component parse
# --------------------------------------------------------------------------
TC_BEGIN, TC_END, TC_CONTINUE, TC_ABORT = 0x62, 0x64, 0x65, 0x67
TAG_OTID, TAG_DTID, TAG_COMP_PORTION = 0x48, 0x49, 0x6C
TAG_INVOKE, TAG_RETURN_RESULT, TAG_RETURN_LAST = 0xA1, 0xA2, 0xA2
# Q.772: A2 = returnResultLast, A3 = returnResultNotLast. TAG_RETURN_RESULT and
# TAG_RETURN_LAST above are both A2, so the A3 shape needs its own constant.
TAG_RETURN_NOT_LAST = 0xA3
TAG_LOCAL = 0x02


def der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes(max(1, (n.bit_length() + 7) // 8), "big")
    return bytes([0x80 | len(b)]) + b


def tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + der_len(len(value)) + value


def parse_tlv(buf: bytes, off: int = 0):
    if off + 2 > len(buf):
        raise ValueError("truncated TLV")
    tag = buf[off]
    ln = buf[off + 1]
    off += 2
    if ln & 0x80:
        n = ln & 0x7F
        if off + n > len(buf):
            raise ValueError("truncated long-form length")
        ln = int.from_bytes(buf[off:off + n], "big")
        off += n
    if off + ln > len(buf):
        raise ValueError(f"truncated value for tag 0x{tag:02X}")
    return tag, buf[off:off + ln], off + ln


def parse_all(buf: bytes) -> list[tuple[int, bytes]]:
    out, off = [], 0
    while off < len(buf):
        tag, val, off = parse_tlv(buf, off)
        out.append((tag, val))
    return out


def unwrap_seq(buf: bytes) -> bytes:
    """Strip one outer SEQUENCE (0x30) wrapper, if present.

    MAP operation arguments/results are SEQUENCE types, so the top level on the
    wire is `30 <len> {...}`. Decoders that expect the fields directly must call
    this first, otherwise parse_all() only ever sees the single 0x30 tag.
    """
    if len(buf) >= 2 and buf[0] == 0x30:
        tag, val, end = parse_tlv(buf, 0)
        if end == len(buf):
            return val
    return buf


def tcap_begin(otid: bytes, invoke: bytes) -> bytes:
    return tlv(TC_BEGIN, tlv(TAG_OTID, otid) + tlv(TAG_COMP_PORTION, invoke))


def tcap_end(dtid: bytes, component: bytes) -> bytes:
    return tlv(TC_END, tlv(TAG_DTID, dtid) + tlv(TAG_COMP_PORTION, component))


def invoke(invoke_id: int, opcode: int, arg: bytes) -> bytes:
    # invokeID and the local opcode share tag 0x02 -> positional order matters
    return tlv(TAG_INVOKE, tlv(TAG_LOCAL, bytes([invoke_id])) +
               tlv(TAG_LOCAL, bytes([opcode])) + arg)


def return_result(invoke_id: int, opcode: int, res: bytes) -> bytes:
    return tlv(TAG_RETURN_LAST, tlv(TAG_LOCAL, bytes([invoke_id])) +
               tlv(0x30, tlv(TAG_LOCAL, bytes([opcode])) + res))


def return_result_not_last(invoke_id: int, opcode: int, res: bytes) -> bytes:
    """A3: returnResultNotLast — same body as A2, different component tag."""
    return tlv(TAG_RETURN_NOT_LAST, tlv(TAG_LOCAL, bytes([invoke_id])) +
               tlv(0x30, tlv(TAG_LOCAL, bytes([opcode])) + res))


def decode_tcap(payload: bytes) -> dict:
    tag, val, _ = parse_tlv(payload, 0)
    out = {"kind": {TC_BEGIN: "Begin", TC_END: "End",
                    TC_CONTINUE: "Continue", TC_ABORT: "Abort"}.get(tag, hex(tag)),
           "otid": None, "dtid": None, "component": None}
    comp = None
    for t, v in parse_all(val):
        if t == TAG_OTID:
            out["otid"] = v
        elif t == TAG_DTID:
            out["dtid"] = v
        elif t == TAG_COMP_PORTION:
            comp = v
    if comp:
        ctag, cval, _ = parse_tlv(comp, 0)
        if ctag in (TAG_INVOKE, TAG_RETURN_RESULT, 0xA3):
            t1, v1, off = parse_tlv(cval, 0)
            invoke_id = v1[0] if v1 else None
            opcode: int | None = None
            param = b""
            if ctag == TAG_INVOKE:
                # invoke { invokeID, opcode, arg } -- both local, positional
                t2, v2, off2 = parse_tlv(cval, off)
                opcode = int.from_bytes(v2, "big") if v2 else None
                param = cval[off2:]
            else:
                # returnResult{Last} { invokeID, SEQUENCE { opcode, result } }
                seq = unwrap_seq(cval[off:])
                fields = parse_all(seq)
                if fields:
                    opcode = int.from_bytes(fields[0][1], "big")
                    _, _, o = parse_tlv(seq, 0)
                    param = seq[o:]
            out["component"] = {
                "type": "Invoke" if ctag == TAG_INVOKE else "ReturnResult",
                "invoke_id": invoke_id,
                "opcode": opcode,
                "param": param,
            }
    return out


# --------------------------------------------------------------------------
# MAP (TS 29.002)
# --------------------------------------------------------------------------
OP_SRI_SM = 45
OP_PSI = 70
OP_ATI = 71


def map_sri_sm_arg(msisdn: str, sc_address: str = "628110000000", order: str = "lo") -> bytes:
    return tlv(0x30,
               tlv(0x80, tbcd_encode(msisdn, order)) +
               tlv(0x81, b"\xff") +
               tlv(0x82, tbcd_encode(sc_address, order)))


def map_sri_sm_res(imsi: str, network_node: str, order: str = "lo") -> bytes:
    return tlv(0x30,
               tlv(0x80, tbcd_encode(imsi, order)) +
               tlv(0xA1, tlv(0x81, tbcd_encode(network_node, order))))


def map_ati_arg(msisdn: str, scf: str = "628110000000", order: str = "lo") -> bytes:
    # AnyTimeInterrogationArg ::= SEQUENCE {
    #   subscriberIdentity [0] SubscriberIdentity,   -- CHOICE msisdn [1]
    #   requestedInfo      [1] RequestedInfo,        -- locationInformation [0] NULL
    #   gsmSCF-Address     [2] ISDN-AddressString }
    return tlv(0x30,
               tlv(0xA0, tlv(0x81, tbcd_encode(msisdn, order))) +
               tlv(0xA1, tlv(0x80, b"")) +
               tlv(0x82, tbcd_encode(scf, order)))


def encode_lai(mcc: str, mnc: str, lac: int, order: str = "lo") -> bytes:
    return tbcd_encode(mcc, order) + tbcd_encode(mnc, order) + struct.pack(">H", lac)


def decode_lai(raw: bytes, order: str = "lo") -> dict:
    mcc = tbcd_decode(raw[:2], order)
    mnc = tbcd_decode(raw[2:3], order)
    lac = struct.unpack(">H", raw[3:5])[0] if len(raw) >= 5 else None
    return {"mcc": mcc, "mnc": mnc, "lac": lac}


def map_subscriber_info(imsi: str, *, age_s: int, vlr: str, lai_raw: bytes,
                        ci: int, order: str = "lo") -> bytes:
    """SubscriberInfo block shared by ATI-res and PSI-res."""
    location = (tlv(0x80, bytes([age_s])) +
                tlv(0x82, tbcd_encode(vlr, order)) +
                tlv(0x84, lai_raw + struct.pack(">H", ci)) +
                tlv(0x85, lai_raw))
    return tlv(0x30,
               tlv(0x80, tbcd_encode(imsi, order)) +
               tlv(0xA0, tlv(0xA0, location)))


def decode_sri_sm_res(res: bytes, order: str = "lo") -> dict:
    out: dict[str, object] = {"imsi": None, "network_node": None}
    for t, v in parse_all(unwrap_seq(res)):
        if t == 0x80:
            out["imsi"] = tbcd_decode(v, order)
        elif t == 0xA1:
            for t2, v2 in parse_all(unwrap_seq(v)):
                if t2 == 0x81:
                    out["network_node"] = tbcd_decode(v2, order)
    return out


def decode_subscriber_info(res: bytes, order: str = "lo") -> dict:
    out: dict[str, object] = {"imsi": None, "age_s": None, "vlr": None,
                              "lai": None, "ci": None}
    for t, v in parse_all(unwrap_seq(res)):
        if t == 0x80:
            out["imsi"] = tbcd_decode(v, order)
        elif t == 0xA0:
            for t2, v2 in parse_all(unwrap_seq(v)):
                if t2 != 0xA0:
                    continue
                for t3, v3 in parse_all(unwrap_seq(v2)):
                    if t3 == 0x80:
                        out["age_s"] = v3[0] if v3 else None
                    elif t3 == 0x82:
                        out["vlr"] = tbcd_decode(v3, order)
                    elif t3 == 0x85:
                        out["lai"] = decode_lai(v3, order)
                    elif t3 == 0x84:
                        out["ci"] = struct.unpack(">H", v3[-2:])[0] if len(v3) >= 2 else None
                        if out["lai"] is None and len(v3) >= 5:
                            out["lai"] = decode_lai(v3[:5], order)
    return out
