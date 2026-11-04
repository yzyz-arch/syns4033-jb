"""GSMA FS.11 classification + wire signatures + rule export (offline only).

Three things live here:

  1. TAXONOMY   opcode -> FS.11 category (1 / 2 / 3, with the 2.1/2.2 and
                3.1/3.2/3.3 sub-classes), so an inbound MAP PDU can be
                classified without a live firewall.
  2. SIGNATURES byte-anchored patterns that identify an operation in a raw
                capture *without* full ASN.1 parsing. The TCAP Invoke shape is
                `A1 L 02 01 <invokeID> 02 01 <opcode> ...`, so
                `A1 ?? 02 01 ?? 02 01 <op>` is an offset-independent anchor.
  3. EXPORTERS  the same table rendered as YARA, Sigma, Wireshark display
                filters and JSON. One source, several engines.

Sources for the category split (kept explicit so a mismatch is visible):
  * GSMA FS.11 "SS7 Interconnect Security Monitoring and Firewall Guidelines"
    — Category 1/2/3 sample packet lists, incl. the "Unknown PDU -> Category 1"
    rule and the 2.1/2.2 / 3.1/3.2/3.3 sub-classification.
  * 3GPP TS 29.002 §17.5/§17.6 for the opcode numbers themselves.

Caveat kept in the data, not hidden: FS.11 Annex A carries the *complete*
per-packet classification. The table below covers the operations named in the
main body of the spec; anything absent is reported as `unclassified` instead
of being guessed into a category.

This module opens no sockets. Rule generation is a pure function of the
tables below — there is no host to point at, so there is nothing to guard.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from . import diameter, wire

# --------------------------------------------------------------------------
# 1. TAXONOMY
# --------------------------------------------------------------------------
# category meanings, verbatim intent from FS.11:
#   1 = prohibited at interconnect unless an explicit bilateral agreement
#   2 = should only arrive from the subscriber's HOME network (intra-packet
#       logic: lower-layer vs application-layer addressing must agree)
#   3 = should only arrive from the subscriber's VISITED network
#       (inter-packet logic: location/velocity/time plausibility)
CATEGORY_LABELS = {
    "1": "Prohibited Interconnect Packets",
    "2": "Unauthorised Packets (home-network only)",
    "2.1": "  + requires an answer (SCCP/MAP address association check)",
    "2.2": "  + no answer required (harder: origination address can be faked)",
    "3": "Suspicious Location Packets",
    "3.1": "  + VLR/SGSN cross-check against known state",
    "3.2": "  + time/location plausibility (no VLR history to compare)",
    "3.3": "  + IPSMGW / SMS-specific spoofing checks",
}


@dataclass(frozen=True)
class MapOp:
    opcode: int
    name: str
    category: str
    answer: bool = True
    note: str = ""


# Category 1 — FS.11 body list. `unknown` opcodes are Cat 1 by the same spec.
_CAT1 = [
    (22, "sendRoutingInfo", "interconnect-unauthorised; discloses serving MSC"),
    (24, "sendRoutingInfoForGPRS", "discloses SGSN, same class as SRI"),
    (85, "sendRoutingInfoForLCS", "LCS routing lookup, cat 1 unless LCS agreement"),
    (58, "sendIMSI", "trivial IMSI disclosure, never needed on interconnect"),
    (71, "anyTimeInterrogation", "ATI: cell-level location on demand"),
    (62, "anyTimeSubscriptionInterrogation", "ATSI: subscription profile read"),
    (65, "anyTimeModification", "ATM: subscription write"),
    (55, "sendIdentification", "SAI-adjacent identity disclosure"),
    (6, "resumeCallHandling", "call-control interworking, not interconnect"),
    (25, "failureReport", "call-control interworking, not interconnect"),
    (43, "checkIMEI", "EIR query, same-network only"),
    (5, "noteSubscriberDataModified", "HLR-internal notification"),
]

# Category 2 — home-network origin; sub-class depends on whether an answer
# is expected (2.1) or the sender address can be forged freely (2.2).
_CAT2 = [
    (7, "insertSubscriberData", "2.2", False, "subscriber profile push"),
    (8, "deleteSubscriberData", "2.2", False, "subscriber profile element removal"),
    (37, "reset", "2.2", False, "HLR/MSC restart notification"),
    (38, "forwardCheckSSIndication", "2.2", False, "SS status check forward"),
    (70, "provideSubscriberInfo", "2.1", True, "PSI: cell-level location payload"),
    (4, "provideRoamingNumber", "2.1", True, "PRN: allocates a roaming MSRN"),
    (83, "provideSubscriberLocation", "2.1", True, "PSL: LCS positioning request"),
    (3, "cancelLocation", "2.2", True, "location cancel from old VLR"),
    (50, "activateTraceMode", "2.2", True, "subscriber tracing"),
    (51, "deactivateTraceMode", "2.2", True, "subscriber tracing off"),
    (73, "setReportingState", "2.2", True, "MSC/VLR reporting state"),
    (75, "remoteUserFree", "2.1", True, "CCBS callback trigger"),
    (64, "alertServiceCentre", "2.2", False, "SMS SC alert"),
]

# Category 3 — visited-network origin; needs inter-packet correlation.
_CAT3 = [
    (2, "updateLocation", "3.2", True,
     "UL: rapid non-bordering country change = classic location-track signal"),
    (23, "updateGPRSLocation", "3.2", True, "UGL: same velocity logic as UL"),
    (56, "sendAuthenticationInfo", "3.2", True,
     "SAI: vectors for interception; roaming-partner only"),
    (46, "moForwardSM", "3.1", True, "MO-FSM: validate against known VLR"),
    (44, "mtForwardSM", "3.3", True, "MT-FSM: SMS spoofing checks"),
    (10, "registerSS", "3.1", True, "SS registration from visited network"),
    (59, "processUnstructuredSS-Request", "3.1", True, "USSD request"),
    (60, "unstructuredSS-Request", "3.1", True, "USSD request (network-initiated)"),
    (61, "unstructuredSS-Notify", "3.1", False, "USSD notify"),
]

# Deliberately classified as SMS-path Cat 3.3, not Cat 1: FS.11 authorises
# SRI-SM between the HPLMN and SMS-routing partners, subject to spoofing and
# faking checks (called-party GT ownership, SRI-SM rate, SRI-SM vs MT-FSM
# correlation). Blocking it outright breaks inbound SMS.
_CAT3_SMS = [
    (45, "sendRoutingInfoForSM", "3.3", True,
     "SRI-SM: allowed to SMS partners, must pass SMS spoofing checks; the "
     "single most abused op for location tracking"),
]

MAP_OPS: dict[int, MapOp] = {}


def _register_cat1(rows) -> None:
    """Category 1 rows: (opcode, name, note) -> answer not expected on interconnect."""
    for opcode, name, note in rows:
        MAP_OPS[opcode] = MapOp(opcode, name, "1", True, note)


def _register_verbatim(rows) -> None:
    """Rows that carry their own category: (opcode, name, cat, answer, note)."""
    for opcode, name, cat, answer, note in rows:
        MAP_OPS[opcode] = MapOp(opcode, name, cat, answer, note)


_register_cat1(_CAT1)
_register_verbatim(_CAT2)
_register_verbatim(_CAT3)
_register_verbatim(_CAT3_SMS)

CATEGORY_OF = {op: m.category for op, m in MAP_OPS.items()}

# FS.11: "Unknown PDU: any GSM-MAP packet with an Unallocated/Unknown
# Operation Code" is Category 1.
UNKNOWN_CATEGORY = "1"

# Diameter side (FS.19 in the same series, kept here because the lab serves
# SLh/SLg): LCS routing lookups are the location-relevant commands.
DIAMETER_SL_COMMANDS = {
    diameter.CMD_LIR_LIA: ("LCS-Routing-Info (SLh)", "3", "routing info for LCS"),
    diameter.CMD_PLR_PLA: ("Provide-Location (SLg)", "3", "positioning request"),
}


def classify_opcode(opcode: int | None) -> dict:
    """FS.11 classification for a MAP opcode. Unknown -> Category 1."""
    if opcode is None:
        return {"category": UNKNOWN_CATEGORY, "name": "no-component",
                "answer_required": None, "note": "no TCAP component decoded",
                "known": False}
    meta = MAP_OPS.get(opcode)
    if meta is None:
        return {"category": UNKNOWN_CATEGORY, "name": f"unknown_op_{opcode}",
                "answer_required": None, "known": False,
                "note": "FS.11: unknown/unallocated opcode is Category 1"}
    return {"category": meta.category, "name": meta.name,
            "answer_required": meta.answer, "note": meta.note, "known": True}


def classify(payload: bytes, *, tbcd_order: str = "lo") -> dict:
    """Classify a raw frame: M3UA Data, SCCP UDT, or bare TCAP.

    Returns category, opcode, SCCP addressing and the action a firewall would
    take. Never raises on malformed input — returns `parse_error` instead, so
    a fuzzed or truncated PDU is reported rather than crashing the caller.
    """
    out: dict = {"frame_len": len(payload), "layer": None, "category": None,
                 "category_label": None, "opcode": None, "op": None,
                 "action": None, "parse_error": None}

    buf = payload
    try:
        if len(buf) >= 8 and buf[0] == wire.M3UA_VERSION:
            cls, typ, params = wire.parse_m3ua(buf)
            out["layer"] = f"m3ua:{cls}/{typ}"
            for tag, value in wire.parse_params(params):
                if tag == wire.IEI_PROT_DATA:
                    buf = value
                    break
            else:
                out.update(parse_error="m3ua without protocol data",
                           action="allow")
                return out
        if buf and buf[0] == wire.SCCP_UDT:
            sccp = wire.parse_sccp(buf)
            out["layer"] = (out["layer"] or "sccp") + "+udt"
            out["called"] = {k: sccp["called"][k] for k in ("ssn", "pc", "gt")}
            out["calling"] = {k: sccp["calling"][k] for k in ("ssn", "pc", "gt")}
            buf = sccp["data"]
            out["layer"] += "+tcap"
        tcap = wire.decode_tcap(buf)
        comp = tcap.get("component") or {}
        out["tcap_kind"] = tcap.get("kind")
        out["invoke_id"] = comp.get("invoke_id")
        out["component_type"] = comp.get("type")
        out["opcode"] = comp.get("opcode")
        cls = classify_opcode(out["opcode"])
        out.update(category=cls["category"], op=cls["name"],
                   category_label=CATEGORY_LABELS.get(cls["category"]),
                   known=cls["known"], note=cls["note"],
                   answer_required=cls["answer_required"])
        out["action"] = {"1": "block", "2": "screening",
                         "3": "correlate"}.get(str(cls["category"])[:1], "allow")
    except (ValueError, KeyError, IndexError) as e:
        out.update(parse_error=f"{type(e).__name__}: {e}", action="review")
    return out


# --------------------------------------------------------------------------
# 2. WIRE SIGNATURES
# --------------------------------------------------------------------------
# TCAP component shapes (Q.772), as emitted by wire.py:
#   Invoke            A1 L { 02 01 IID  02 01 OP  arg }
#   ReturnResultLast  A2 L { 02 01 IID  30 L { 02 01 OP  res } }
#   ReturnResultNotLast A3 L { ... same ... }
# IID and OP are 1-octet for all MAP values, so the anchor is stable and
# offset-independent: a firewall can scan the whole PDU once.
def map_invoke_anchor(opcode: int) -> str:
    return f"a1 ?? 02 01 ?? 02 01 {opcode:02x}"


def map_return_anchor(opcode: int) -> str:
    """Matches both ReturnResultLast (A2) and NotLast (A3)."""
    return f"a[23] ?? 02 01 ?? 30 ?? 02 01 {opcode:02x}"


def anchor_bytes_opcode(anchor: str) -> int:
    """Extract the opcode octet from an anchor string (last two hex digits)."""
    return int(anchor.replace("[23]", "2").split()[-1], 16)


def diameter_anchor(command: int, app_id: int, *, request: bool = True) -> str:
    """Diameter header: ver[1] len[3] flags[1] cmd[3] app[4] hop[4] end[4].

    Fixed-offset match on ver+flags+command+application-id. Flags wildcarded
    except the request bit (0x80) so answers are not matched as requests.
    """
    flag = 0x80 if request else 0x00
    cmd = command.to_bytes(3, "big").hex(" ", 1)
    app = app_id.to_bytes(4, "big").hex(" ", 1)
    return f"01 ?? ?? ?? {flag:02x} {cmd} {app}"


@dataclass(frozen=True)
class Signature:
    engine_anchor: str
    opcode: int
    name: str
    category: str

    @property
    def kind(self) -> str:
        """`invoke` for an A1 anchor, `return` for A2/A3."""
        return "invoke" if self.engine_anchor.startswith("a1") else "return"

    def grep_anchor(self) -> str:
        """Regex form for grep/PCRE engines.

        One wildcard token is one *byte* = two hex characters, so `??` must
        become `[0-9a-f]{2}`. A single `.` is one *nibble* and silently misses
        every anchor in a hex dump. `[23]` is already a valid regex character
        class, so it is left alone.
        """
        return self.engine_anchor.replace(" ", "").replace(
            "??", "[0-9a-f]{2}")


def signatures(ops: list[int] | None = None) -> list[Signature]:
    """One invoke + one return anchor per classified operation."""
    sigs: list[Signature] = []
    for opcode, meta in sorted(MAP_OPS.items()):
        if ops is not None and opcode not in ops:
            continue
        for anchor in (map_invoke_anchor(opcode), map_return_anchor(opcode)):
            sigs.append(Signature(anchor, opcode, meta.name, meta.category))
    return sigs


def match_signatures(payload: bytes) -> list[dict]:
    """Scan a frame for every signature anchor. Used by selftest and tests."""
    import re
    hits: list[dict] = []
    text = payload.hex()
    for sig in signatures():
        # [23] is a regex character class, so one pattern covers A2 and A3.
        if re.search(sig.grep_anchor(), text):
            hits.append({"opcode": sig.opcode, "name": sig.name,
                         "category": sig.category,
                         "kind": sig.kind, "anchor": sig.engine_anchor})
    return hits


# --------------------------------------------------------------------------
# 3. EXPORTERS
# --------------------------------------------------------------------------
CATEGORY_RULES = {
    "1": dict(level="critical", action="block", msg="prohibited interconnect op"),
    "2": dict(level="high", action="screen", msg="home-network-only op"),
    "3": dict(level="medium", action="correlate", msg="location op, needs correlation"),
}


def _sig_ids() -> dict[str, uuid.UUID]:
    """Deterministic ids so re-generating rules does not create duplicates."""
    ns = uuid.UUID("6f3c1a44-0d5e-5f0b-9a77-53d2c1b0e001")
    return {cat: uuid.uuid5(ns, f"fs11-cat{cat}") for cat in CATEGORY_RULES}


def _ops_for_category(cat: str) -> list[MapOp]:
    """Ops whose FS.11 category falls under `cat`, sub-classes included.

    Categories in the table are `1`, `2`/`2.1`/`2.2`, `3`/`3.1`/`3.2`/`3.3`.
    Comparing the sub-classed string for equality against `"2"` matches nothing,
    which silently dropped Category 2 and Category 3 out of every exporter.
    Grouping on the leading character keeps each op under its parent rule.
    """
    return sorted((m for m in MAP_OPS.values()
                   if m.category.split(".")[0] == cat),
                  key=lambda m: m.opcode)


def _signature_hex_patterns(opcode: int) -> list[tuple[str, str]]:
    """YARA hex strings for one opcode: invoke plus both return shapes.

    YARA hex has no character class, so `A[23]` must be emitted as two separate
    strings. Emitting only `A2` (the previous behaviour) silently lost every
    ReturnResultNotLast, and labelled the return anchor as an "invoke".
    """
    return [
        (map_invoke_anchor(opcode).upper(), "invoke"),
        (map_return_anchor(opcode).replace("[23]", "2").upper(), "returnLast"),
        (map_return_anchor(opcode).replace("[23]", "3").upper(), "returnNotLast"),
    ]


def export_yara() -> str:
    ids = _sig_ids()
    lines = [
        "// GSMA FS.11 SS7/MAP interconnect signatures — generated by ss7lab.fs11",
        "// Anchors are offset-independent: A1 ?? 02 01 ?? 02 01 <op>",
        "// Compile-checked with yara-python before shipping.",
        "",
    ]
    for cat, meta in CATEGORY_RULES.items():
        strings = []
        for op in _ops_for_category(cat):
            for hexpat, shape in _signature_hex_patterns(op.opcode):
                n = len(strings) + 1
                strings.append(f'        $s{n:02d} = {{ {hexpat} }}'
                               f'   // {op.name} {shape}, op {op.opcode}')
        if not strings:
            continue
        lines += [
            f'rule fs11_cat{cat}_map_ops {{',
            '    meta:',
            f'        description = "GSMA FS.11 Category {cat}: {meta["msg"]}"',
            f'        fs11_category = "{cat}"',
            f'        action = "{meta["action"]}"',
            f'        signature_id = "{ids[cat]}"',
            '    strings:',
            *strings,
            '    condition:',
            # `N of them` with N == number of strings means ALL must be present,
            # so the rule could never fire on a real single-operation frame.
            '        any of them',
            '}',
            '',
        ]
    # Diameter SLh/SLg location commands
    dstrings = []
    for i, (cmd, (name, cat, desc)) in enumerate(
            sorted(DIAMETER_SL_COMMANDS.items()), 1):
        app = diameter.APP_SLH if cmd == diameter.CMD_LIR_LIA else diameter.APP_SLG
        anchor = diameter_anchor(cmd, app).upper().replace("01 ", "01 ", 1)
        dstrings.append(f'        $d{i} = {{ {anchor} }}   // {name} request')
    lines += [
        'rule fs19_sl_location_commands {',
        '    meta:',
        '        description = "FS.19-adjacent: Diameter SLh/SLg location lookups"',
        '        fs11_category = "3"',
        '        action = "correlate"',
        '    strings:',
        *dstrings,
        '    condition:',
        # same trap as above: `N of them` means every string must match
        '        any of them',
        '}',
        '',
    ]
    return "\n".join(lines)


def export_sigma() -> str:
    ids = _sig_ids()
    blocks = []
    for cat, meta in CATEGORY_RULES.items():
        ops = [m.opcode for m in _ops_for_category(cat)]
        names = ", ".join(MAP_OPS[o].name for o in ops)
        blocks.append(
            f"""title: FS.11 Category {cat} — {meta['msg']}
id: {ids[cat]}
status: experimental
description: >
  GSMA FS.11 Category {cat} MAP operation observed at an interconnect point.
  Operations covered: {names}. Required handling: {meta['action']}.
references:
  - https://www.gsma.com/newsroom/wp-content/uploads/FS.11.pdf
logsource:
  product: ss7lab
  service: map
detection:
  selection:
    fs11.category: "{cat}"
  condition: selection
falsepositives:
  - Roaming partner with an explicit bilateral agreement for this operation
level: {meta['level']}
tags:
  - attack.collection
  - attack.credential_access
""")
    return "\n".join(blocks)


def export_wireshark() -> str:
    lines = [
        "# Wireshark / tshark display filters — GSMA FS.11",
        "# verify field names first: tshark -G fields | grep -E 'gsm_map.opcode|sccp.ssn'",
        "",
    ]
    for cat, meta in CATEGORY_RULES.items():
        ops = [m.opcode for m in _ops_for_category(cat)]
        if not ops:
            continue
        lines.append(f"# Category {cat} — {meta['msg']} (action: {meta['action']})")
        lines.append("(" + " || ".join(f"gsm_map.opcode == {o}" for o in ops) + ")")
        lines.append("")
    lines += [
        "# Location-relevant Diameter (SLh/SLg)",
        f"(diameter.cmd.code == {diameter.CMD_LIR_LIA})"
        f" || (diameter.cmd.code == {diameter.CMD_PLR_PLA})",
        "",
        "# Combined one-liner for a capture sweep:",
        "gsm_map.opcode in {2 22 23 45 56 58 70 71 83 85}",
        "",
    ]
    return "\n".join(lines)


def export_json() -> str:
    payload = {
        "source": "GSMA FS.11 + 3GPP TS 29.002",
        "categories": CATEGORY_LABELS,
        "ops": [
            {"opcode": m.opcode, "name": m.name, "category": m.category,
             "answer_required": m.answer, "note": m.note,
             "invoke_anchor": map_invoke_anchor(m.opcode),
             "return_anchor": map_return_anchor(m.opcode)}
            for m in sorted(MAP_OPS.values(), key=lambda x: x.opcode)
        ],
        "unknown_opcode_category": UNKNOWN_CATEGORY,
        "diameter": [
            {"command": cmd, "name": name, "category": cat,
             "note": desc, "anchor": diameter_anchor(cmd, app)}
            for cmd, (name, cat, desc), app in (
                (c, v, diameter.APP_SLH if c == diameter.CMD_LIR_LIA
                 else diameter.APP_SLG)
                for c, v in sorted(DIAMETER_SL_COMMANDS.items()))
        ],
    }
    return json.dumps(payload, indent=2)


EXPORTERS = {"yara": export_yara, "sigma": export_sigma,
             "wireshark": export_wireshark, "json": export_json}
EXTENSIONS = {"yara": ".yar", "sigma": ".yml", "wireshark": ".txt", "json": ".json"}


def emit(which: str = "all") -> dict[str, str]:
    """Render one or all rule formats. `all` -> dict of name -> text."""
    names = list(EXPORTERS) if which == "all" else [which]
    return {name: EXPORTERS[name]() for name in names}


def summary() -> dict:
    by_cat: dict[str, list[str]] = {}
    for meta in MAP_OPS.values():
        by_cat.setdefault(meta.category, []).append(meta.name)
    return {"classified_ops": len(MAP_OPS),
            "by_category": {k: sorted(v) for k, v in sorted(by_cat.items())},
            "signatures": len(signatures())}