"""macOS / Apple network service catalogue used for discovery + classification."""

from __future__ import annotations

# DNS-SD service type -> what it means on a Mac, and the classic TCP port.
SERVICE_TYPES: dict[str, dict] = {
    "_ssh._tcp.local.": {
        "label": "Remote Login (SSH)",
        "port": 22,
        "risk": "high",
        "notes": "Full shell. Anything other than publickey/keyboard-interactive with 2FA is creds-only access.",
    },
    "_rfb._tcp.local.": {
        "label": "Screen Sharing / VNC",
        "port": 5900,
        "risk": "critical",
        "notes": "Apple Screen Sharing daemon (screensharingd, runs as root). RFB 003.889 + security type 36 = Apple SRP. Security type 2 = VNC DES auth, password compared on first 8 chars only -> brute-forceable.",
    },
    "_eppc._tcp.local.": {
        "label": "Remote Apple Events (RAE)",
        "port": 3031,
        "risk": "high",
        "notes": "com.apple.AEServer. Valid creds + enabled service = drive any scriptable app remotely (lateral movement primitive).",
    },
    "_adisk._tcp.local.": {
        "label": "Time Machine / AFP share",
        "port": 548,
        "risk": "medium",
        "notes": "Backup volumes. Exposed backup trees leak filesystem + credentials from old snapshots.",
    },
    "_afpovertcp._tcp.local.": {
        "label": "AFP file sharing",
        "port": 548,
        "risk": "medium",
        "notes": "Legacy Apple Filing Protocol. Enumerate volumes via afp_client / nmap afp-* scripts.",
    },
    "_smb._tcp.local.": {
        "label": "SMB file sharing",
        "port": 445,
        "risk": "medium",
        "notes": "SMB signing off is common on macOS -> relay candidate.",
    },
    "_device-info._tcp.local.": {
        "label": "Device info (model identifier)",
        "port": 0,
        "risk": "info",
        "notes": "TXT record carries model= ; tells you MacBookPro18,3 vs VirtualMac etc, and OS class.",
    },
    "_companion-link._tcp.local.": {
        "label": "Continuity / Companion Link",
        "port": 0,
        "risk": "info",
        "notes": "Handoff, Universal Control, Sidecar. Identifies paired-device topology.",
    },
    "_airplay._tcp.local.": {
        "label": "AirPlay receiver",
        "port": 7000,
        "risk": "low",
        "notes": "AirPlay server; historically useful for screen mirroring abuse, also leaks model/OS in TXT.",
    },
    "_raop._tcp.local.": {
        "label": "AirTunes / RAOP",
        "port": 5000,
        "risk": "low",
        "notes": "AirPlay audio. TXT model + device id.",
    },
    "_home-sharing._tcp.local.": {
        "label": "Back to My Mac / Home Sharing",
        "port": 4488,
        "risk": "high",
        "notes": "Back to My Mac punches wide holes through NAT; historically a remote-access surface. Disable unless required (CVE-2019-8641 era).",
    },
    "_ipp._tcp.local.": {
        "label": "CUPS/IPP printer",
        "port": 631,
        "risk": "low",
        "notes": "Shared printer queues on the Mac.",
    },
    "_ipps._tcp.local.": {
        "label": "CUPS/IPPS printer (TLS)",
        "port": 631,
        "risk": "low",
        "notes": "TLS-wrapped IPP.",
    },
    "_printer._tcp.local.": {
        "label": "LPD printer",
        "port": 515,
        "risk": "low",
        "notes": "LPD queue -> job injection / file exfil via queue paths.",
    },
    "_scanner._tcp.local.": {
        "label": "eSCL / AirScan scanner",
        "port": 0,
        "risk": "low",
        "notes": "Image Capture scan surface.",
    },
    "_rdlink._tcp.local.": {
        "label": "Remote Desktop link (ARD)",
        "port": 3283,
        "risk": "critical",
        "notes": "Apple Remote Desktop management channel. kickstart-controlled privileges; admin accounts can send Unix commands as root.",
    },
    "_net-assistant._tcp.local.": {
        "label": "ARD Net Assistant",
        "port": 3283,
        "risk": "high",
        "notes": "ARD discovery/assist channel.",
    },
}

# TCP ports worth probing on any suspected Mac.
PORTS: dict[int, dict] = {
    22: {"label": "ssh", "service": "Remote Login"},
    88: {"label": "kerberos", "service": "Kerberos KDC (macOS Server / AD-joined)"},
    445: {"label": "smb", "service": "SMB"},
    548: {"label": "afp", "service": "AFP"},
    5900: {"label": "rfb", "service": "Screen Sharing / VNC"},
    3031: {"label": "eppc", "service": "Remote Apple Events"},
    3283: {"label": "ard", "service": "Apple Remote Desktop"},
    4488: {"label": "btmm", "service": "Back to My Mac"},
    5353: {"label": "mdns", "service": "mDNSResponder (UDP)"},
    631: {"label": "ipp", "service": "CUPS"},
    5000: {"label": "raop", "service": "AirPlay audio"},
    7000: {"label": "airplay", "service": "AirPlay video"},
    8188: {"label": "airplay-alt", "service": "AirPlay alternate"},
}

# RFB security type table (client-side view of what the server advertises).
RFB_SECURITY_TYPES: dict[int, dict] = {
    0: {"name": "Invalid", "note": "must fail connection"},
    1: {"name": "None", "note": "NO AUTHENTICATION - direct control", "risk": "critical"},
    2: {"name": "VNC Authentication (DES)", "note": "password compared on first 8 chars (ARD truncation) -> hydra/GoRedShell brute force, no default rate limit", "risk": "critical"},
    5: {"name": "RA2", "note": "RSA-AES challenge (RealVNC)"},
    6: {"name": "RA2ne", "note": "RSA-AES no encryption"},
    16: {"name": "Tight", "note": "TightVNC auth"},
    18: {"name": "TLS", "note": "TLS with anonymous DH"},
    19: {"name": "VeNCrypt", "note": "TLS subtypes follow"},
    22: {"name": "Ultra", "note": "UltraVNC MS Logon II"},
    30: {"name": "Apple DH", "note": "Apple's Diffie-Hellman auth variant"},
    35: {"name": "Apple SRP (36?)", "note": "Apple hybrid auth marker seen near type 36"},
    36: {"name": "Apple SRP + ChaCha20-Poly1305", "note": "RFB 003.889 Apple SRP; SRP authenticates, then ChaCha20-Poly1305 session crypto is installed only after ccsrp_server_verify_session"},
}
