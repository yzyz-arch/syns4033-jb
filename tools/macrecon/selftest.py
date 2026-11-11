"""Self-verification. Spins up local fakes; needs no external target.

Checks:
  1. DNS wire round-trip incl. compression pointers
  2. mDNS unicast query against a fake responder
  3. RFB 003.889 / type 36 fingerprint + auth peek
  4. RFB 003.8 / type 2 (VNC DES) fingerprint + 16-byte challenge
  5. TCP probe behaviour on open and closed ports
  6. ARD 0x22 frame encoder field layout
  7. wordlist 8-char truncation dedupe
"""

from __future__ import annotations

import socket
import struct
import threading
import time

from . import dnswire, mdns, plan, probe, services


def _record(name: bytes, rtype: int, rdata: bytes, ttl: int = 120) -> bytes:
    """Assemble one DNS answer: <name bytes><type><class><ttl><rdlen><rdata>."""
    return name + struct.pack(">HHIH", rtype, 1, ttl, len(rdata)) + rdata


def _ptr_to(offset: int) -> bytes:
    return struct.pack(">H", 0xC000 | offset)


def _dns_check() -> tuple[bool, str]:
    q = dnswire.build_query("_ssh._tcp.local.", qtype=dnswire.TYPE_PTR)
    msg = dnswire.parse_message(q)
    if msg["questions"][0]["name"] != "_ssh._tcp.local.":
        return False, f"qname mismatch: {msg['questions'][0]['name']}"
    if msg["questions"][0]["class"] & 0x8000:
        return False, "QU bit lost on parse"

    stype = dnswire.encode_name("_ssh._tcp.local.")
    inst = dnswire.encode_name("Fake-SSHD._ssh._tcp.local.")
    header = struct.pack(">HHHHHH", 0x1234, 0x8400, 0, 3, 0, 0)

    # record 1: PTR, name inline at offset 12, rdata = full instance name
    ptr = _record(stype, 12, inst)
    inst_off = 12 + len(stype) + 10          # instance name sits right here
    # record 2: SRV, name = pointer to the instance above, target = pointer to the type
    srv_rdata = struct.pack(">HHH", 0, 0, 22) + _ptr_to(12)
    srv = _record(_ptr_to(inst_off), 33, srv_rdata)
    # record 3: TXT with a compressed owner name as well
    txt = _record(_ptr_to(inst_off), 16, b"\x0dmodel=Mac14,2")

    parsed = dnswire.parse_message(header + ptr + srv + txt)
    recs = parsed["records"]
    if len(recs) != 3:
        return False, f"expected 3 records, got {len(recs)}: {recs}"
    if recs[0]["value"] != "Fake-SSHD._ssh._tcp.local.":
        return False, f"PTR decode wrong: {recs[0]['value']}"
    if recs[1]["value"]["port"] != 22 or recs[1]["value"]["target"] != "_ssh._tcp.local.":
        return False, f"SRV decode wrong: {recs[1]['value']}"
    if recs[1]["name"] != "Fake-SSHD._ssh._tcp.local.":
        return False, f"compressed owner name wrong: {recs[1]['name']}"
    if recs[2]["value"] != ["model=Mac14,2"]:
        return False, f"TXT decode wrong: {recs[2]['value']}"
    return True, (f"records={len(recs)} ptr={recs[0]['value']} srv_port={recs[1]['value']['port']} "
                  f"txt={recs[2]['value'][0]}")


def _fake_mdns_server(port: int, stop: threading.Event) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.settimeout(0.2)

    def run() -> None:
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(2048)
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                break
            try:
                q = dnswire.parse_message(data)
            except dnswire.DNSError:
                continue
            qname = q["questions"][0]["name"].lower() if q["questions"] else ""
            if "ssh" not in qname and "services._dns-sd" not in qname:
                continue
            stype = dnswire.encode_name("_ssh._tcp.local.")
            inst = dnswire.encode_name("Lab-Mac._ssh._tcp.local.")
            target = dnswire.encode_name("Lab-Mac.local.")
            resp_header = struct.pack(">HHHHHH", q["txid"], 0x8400, 0, 3, 0, 0)
            ptr = _record(stype, 12, inst)
            srv = _record(inst, 33, struct.pack(">HHH", 0, 0, 22) + target)
            arec = _record(target, 1, socket.inet_aton("127.0.0.1"))
            sock.sendto(resp_header + ptr + srv + arec, addr)
    threading.Thread(target=run, daemon=True).start()
    return sock


def _mdns_check() -> tuple[bool, str]:
    port = 15353
    stop = threading.Event()
    sock = _fake_mdns_server(port, stop)
    try:
        time.sleep(0.1)
        res = mdns.query("127.0.0.1", port=port, name="_ssh._tcp.local.",
                         qtype=dnswire.TYPE_PTR, timeout=1.5)
        rows = mdns.build_service_map(res["records"])
        if not rows:
            return False, "no DNS-SD rows from fake responder"
        row = rows[0]
        if row["port"] != 22 or row["ip"] != "127.0.0.1":
            return False, f"row wrong: {row}"
        return True, f"instance={row['instance']} port={row['port']} ip={row['ip']} label={row['label']}"
    finally:
        stop.set()
        sock.close()


def _fake_rfb_server(port: int, version: str, types: list[int],
                     challenge: bytes = b"\x11" * 16) -> tuple:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(4)
    stop = threading.Event()

    def run() -> None:
        while not stop.is_set():
            try:
                client, _ = srv.accept()
            except OSError:
                break
            with client:
                try:
                    client.settimeout(2.0)
                    client.sendall(version.encode() + b"\n")
                    client.recv(12)
                    if probe._parse_minor(version) <= 3:
                        client.sendall(struct.pack(">I", len(types))
                                       + b"".join(struct.pack(">I", t) for t in types))
                    else:
                        client.sendall(bytes([len(types)]) + bytes(types) + b"\x00" * 3)
                    chosen = client.recv(1)
                    if chosen and chosen[0] in (2, 30, 36):
                        client.sendall(challenge)
                    else:
                        client.sendall(b"\x00" * 4)
                except OSError:
                    pass
    threading.Thread(target=run, daemon=True).start()
    return srv, stop


def _rfb_check() -> tuple[bool, str]:
    srv, stop = _fake_rfb_server(15900, "RFB 003.889", [36, 30, 19])
    try:
        time.sleep(0.1)
        fp = probe.rfb_fingerprint("127.0.0.1", 15900, timeout=2.0, auth_peek=True)
        if not fp["apple_screensharing"]:
            return False, f"apple flag not set: {fp}"
        if fp["security_types"] != [36, 30, 19]:
            return False, f"types wrong: {fp['security_types']} ({fp.get('error')})"
        if "first block" not in fp["auth_peek"]:
            return False, f"auth peek missing: {fp['auth_peek']}"
        return True, f"version={fp['version']} types={fp['security_types']} peek={fp['auth_peek'][:38]}..."
    finally:
        stop.set()
        srv.close()


def _rfb_vnc_check() -> tuple[bool, str]:
    srv, stop = _fake_rfb_server(15901, "RFB 003.008", [2])
    try:
        time.sleep(0.1)
        fp = probe.rfb_fingerprint("127.0.0.1", 15901, timeout=2.0, auth_peek=True)
        if fp["security_types"] != [2]:
            return False, f"types wrong: {fp['security_types']} ({fp.get('error')})"
        if "DES challenge received" not in fp["auth_peek"]:
            return False, f"peek wrong: {fp['auth_peek']}"
        if fp["security_detail"][0]["risk"] != "critical":
            return False, "type 2 not classified critical"
        return True, f"version={fp['version']} types=[2] peek_ok detail={fp['security_detail'][0]['name']}"
    finally:
        stop.set()
        srv.close()


def _tcp_check() -> tuple[bool, str]:
    srv, stop = _fake_rfb_server(15902, "RFB 003.889", [36])
    try:
        time.sleep(0.1)
        open_res = probe.tcp_probe("127.0.0.1", 15902, timeout=1.0)
        closed_res = probe.tcp_probe("127.0.0.1", 15999, timeout=1.0)
        if open_res["state"] != "open":
            return False, f"open probe failed: {open_res}"
        if closed_res["state"] != "closed":
            return False, f"closed probe wrong: {closed_res}"
        return True, "open->open, closed->closed"
    finally:
        stop.set()
        srv.close()


def _frame_check() -> tuple[bool, str]:
    payload = plan.new_item_payload("/etc/sudoers.d/pwn", 32, 0o600)
    frame = plan.file_copy_frame(plan.KIND_NEW_ITEM, 1, 1, payload)
    if frame[0] != plan.MSG_FILE_COPY or frame[1] != 0:
        return False, f"frame prefix wrong: {frame[:3].hex()}"
    length_field = struct.unpack(">I", frame[2:6])[0]
    if length_field != 12 + len(payload):
        return False, f"L={length_field} but 12+payload={12 + len(payload)}"
    if len(frame) != 6 + length_field:
        return False, f"wire len {len(frame)} != 6+L ({6 + length_field})"
    if payload[14] != 1:
        return False, "arg[0] regular-file flag not set"
    if struct.unpack(">I", payload[42:46])[0] != 32:
        return False, "filesize field wrong"
    if struct.unpack(">H", payload[0x5A:0x5C])[0] != 0o600:
        return False, "mode field wrong"
    if b"/etc/sudoers.d/pwn" not in payload:
        return False, "path missing from payload"
    return True, (f"wire_len={len(frame)} L={length_field} payload={len(payload)} "
                  f"kind={plan.KIND_NEW_ITEM} arg0=1 size_off42=32 mode_off0x5a=0600 path_off=0x60")


def _wordlist_check() -> tuple[bool, str]:
    lines = ["password", "password1", "password2", "hunter2", "hunter22", "x" * 20]
    out = plan.truncate_wordlist(lines)
    # password/password1/password2 collapse to one 8-char prefix; hunter2 and
    # hunter22 are distinct prefixes ("hunter2" vs "hunter22") and must survive.
    if len(out) != 4:
        return False, f"expected 4 prefixes, got {len(out)}: {out}"
    if out[0] != "password":
        return False, f"first survivor wrong: {out[0]}"
    if "hunter2" not in out or "hunter22" not in out:
        return False, f"8-char boundary collapsed wrongly: {out}"
    return True, f"6 lines -> {len(out)} candidates ({', '.join(out)})"


def _plan_check() -> tuple[bool, str]:
    p = plan.plan_for("192.0.2.10", {"security_types": [2], "version": "RFB 003.8"})
    joined = " ".join(p["screen_sharing"] + p["remote_apple_events"])
    for needle in ("vnc-info", "hydra", "eppc://", "vnc://"):
        if needle not in joined:
            return False, f"missing {needle} in plan"
    p36 = plan.plan_for("192.0.2.10", {"security_types": [36], "version": "RFB 003.889"})
    if not any("type 36" in x for x in p36["screen_sharing"]):
        return False, "type 36 note missing"
    return True, f"plan lines={sum(len(v) for v in p.values() if isinstance(v, list))} catalogue={len(services.SERVICE_TYPES)} services"


CHECKS = [
    ("dns_wire", _dns_check),
    ("mdns_unicast", _mdns_check),
    ("rfb_apple_3889", _rfb_check),
    ("rfb_vnc_type2", _rfb_vnc_check),
    ("tcp_probe", _tcp_check),
    ("ard_frame_0x22", _frame_check),
    ("wordlist_trunc8", _wordlist_check),
    ("plan_generation", _plan_check),
]


def run() -> int:
    failures = 0
    print("macrecon selftest - local fakes only, no external target\n")
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001 - selftest reports any breakage
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<18} {detail}")
        failures += 0 if ok else 1
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    return 1 if failures else 0
