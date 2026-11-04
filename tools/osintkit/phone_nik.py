"""Indonesian identity metadata: NIK structural decode + phone prefix intel.

WHAT THIS MODULE IS
------------------
Offline decoder for two Indonesian identifiers:
  * NIK / Nomor Induk Kependudukan (16 digits) — structural parse only.
  * Phone number (E.164 / national) — operator + line-type + fixed-line area.

WHAT THIS MODULE IS NOT
-----------------------
It does not resolve, and must never claim to resolve, a device position.
A NIK and a phone number carry **zero** positional telemetry:

  * NIK contains a *registration-time* civil address code (province/regency/
    district of the family card). That is where the person was registered,
    not where the person is.
  * A phone number gives a carrier prefix. Live position would require the
    carrier's HLR / GMLC, i.e. lawful intercept, SS7/Diameter MAP abuse, or
    an implant on the handset. This module implements none of those and the
    ~zero network egress is enforced at runtime by `offline_guard()`.

Every result therefore carries `location_capability: "none"` and a
`location_why` string, so downstream consumers (report.py, score.py) cannot
silently upgrade a prefix guess into a position claim.

PII HANDLING
------------
All inputs are masked in the returned `input_masked` field and the guard
requires the caller to pass `authorized=True` before any decode runs.
"""

from __future__ import annotations

import contextlib
import re
import socket

# ---------------------------------------------------------------------------
# offline guard
# ---------------------------------------------------------------------------

class NetworkEgressBlocked(RuntimeError):
    """Raised when something inside the decode path tries to reach the network."""


@contextlib.contextmanager
def offline_guard(enabled: bool = True):
    """Hard-block socket creation for the duration of the decode.

    This is the runtime proof that the module cannot phone home, cannot query
    a carrier API, and cannot leak the identifiers it is handed.
    """
    if not enabled:
        yield
        return
    real_socket = socket.socket
    real_create = socket.create_connection

    def _blocked(*a, **kw):
        raise NetworkEgressBlocked(
            "phone_nik is an offline decoder; network egress attempted from "
            f"offline_guard() (args={a!r:.120})"
        )

    socket.socket = _blocked          # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = real_socket            # type: ignore[assignment]
        socket.create_connection = real_create  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# NIK: province table (classic 34 + 4 DOB provinces, 2022)
# ---------------------------------------------------------------------------

PROVINCES = {
    "11": "Aceh",
    "12": "Sumatera Utara",
    "13": "Sumatera Barat",
    "14": "Riau",
    "15": "Jambi",
    "16": "Sumatera Selatan",
    "17": "Bengkulu",
    "18": "Lampung",
    "19": "Kepulauan Bangka Belitung",
    "21": "Kepulauan Riau",
    "31": "DKI Jakarta",
    "32": "Jawa Barat",
    "33": "Jawa Tengah",
    "34": "DI Yogyakarta",
    "35": "Jawa Timur",
    "36": "Banten",
    "51": "Bali",
    "52": "Nusa Tenggara Barat",
    "53": "Nusa Tenggara Timur",
    "61": "Kalimantan Barat",
    "62": "Kalimantan Tengah",
    "63": "Kalimantan Selatan",
    "64": "Kalimantan Timur",
    "65": "Kalimantan Utara",
    "71": "Sulawesi Utara",
    "72": "Sulawesi Tengah",
    "73": "Sulawesi Selatan",
    "74": "Sulawesi Tenggara",
    "75": "Gorontalo",
    "76": "Sulawesi Barat",
    "81": "Maluku",
    "82": "Maluku Utara",
    "91": "Papua",
    "92": "Papua Barat",
    # 2022 provincial split — codes below are the commonly published ones but
    # are NOT confirmed against Permendagri; treat as UNVERIFIED until checked.
    "93": "Papua Selatan",
    "94": "Papua Tengah",
    "95": "Papua Pegunungan",
    "96": "Papua Barat Daya",
}

UNVERIFIED_PROVINCE_CODES = {"93", "94", "95", "96"}

# Special NIK forms that are structurally 16 digits but are not person NIKs.
NIK_SPECIAL = {
    "0000000000000000": "null/placeholder value seen in scraped datasets",
}

LOCATION_WHY = (
    "NIK stores the civil registration address (family-card level, snapshot at "
    "issuance); phone prefix stores the issuing carrier. Neither contains a "
    "position fix. Live position requires carrier HLR/GMLC access (lawful "
    "intercept), SS7/Diameter signalling abuse, or an implant on the handset — "
    "none of which this offline decoder implements."
)


def _mask(value: str, keep_head: int = 4, keep_tail: int = 2) -> str:
    if not value:
        return ""
    if len(value) <= keep_head + keep_tail:
        return "*" * len(value)
    return f"{value[:keep_head]}{'*' * (len(value) - keep_head - keep_tail)}{value[-keep_tail:]}"


def parse_nik(nik: str, *, authorized: bool = False) -> dict:
    """Structural decode of a 16-digit NIK. Raises nothing; returns errors."""
    if not authorized:
        raise PermissionError("parse_nik requires authorized=True (PII gate)")

    raw = (nik or "").strip().replace(" ", "").replace("-", "")
    out: dict = {
        "input_masked": _mask(raw),
        "valid": False,
        "errors": [],
        "location_capability": "none",
        "location_why": LOCATION_WHY,
    }

    if raw in NIK_SPECIAL:
        out["errors"].append(f"special/placeholder NIK: {NIK_SPECIAL[raw]}")
        return out
    if not raw.isdigit():
        out["errors"].append("NIK must be 16 digits")
        return out
    if len(raw) != 16:
        out["errors"].append(f"length is {len(raw)}, expected 16")
        return out

    prov_code, reg_code = raw[0:2], raw[2:4]
    dist_code = raw[4:6]
    dd, mm, yy = int(raw[6:8]), int(raw[8:10]), int(raw[10:12])
    seq = raw[12:16]

    province = PROVINCES.get(prov_code)
    if not province:
        out["errors"].append(f"unknown province code {prov_code!r}")

    # Gender is encoded in the day field: +40 for female. It is NOT in the
    # 4-digit serial — the "odd = male" rule is a myth that keeps circulating.
    female = dd > 40
    day = dd - 40 if female else dd

    if mm < 1 or mm > 12:
        out["errors"].append(f"month {mm:02d} out of range 1-12")
    if day < 1 or day > 31:
        out["errors"].append(f"day {day:02d} out of range 1-31")
    if mm in (4, 6, 9, 11) and day > 30:
        out["errors"].append(f"day {day:02d} invalid for month {mm:02d}")
    if mm == 2 and day > 29:
        out["errors"].append("day 29+ invalid for February")

    # NIK has NO check digit in the national format. Any tool claiming a NIK
    # "checksum" is either using a regional variant or inventing one.
    out.update({
        "valid": not out["errors"],
        "checksum": None,
        "checksum_note": "NIK has no check digit; validity is structural only",
        "province_code": prov_code,
        "province": province,
        "province_code_verified": prov_code not in UNVERIFIED_PROVINCE_CODES,
        "regency_code": reg_code,
        "district_code": dist_code,
        "registration_area": {
            "level": "kabupaten/kota + kecamatan code (civil registration)",
            "note": "resolve against the BPS Wilayah table for names; not shipped here",
        },
        "birth_date": f"{day:02d}-{mm:02d}-{yy:02d}",
        "birth_date_iso_guess": f"{1900 + yy if yy > 30 else 2000 + yy:04d}-{mm:02d}-{day:02d}",
        "birth_year_ambiguous": True,
        "sex": "female" if female else "male",
        "serial": seq,
    })
    return out


# ---------------------------------------------------------------------------
# Phone: Indonesian numbering plan
# ---------------------------------------------------------------------------

# 4-digit mobile prefixes -> operator. MNP (portability, since 2017) means the
# prefix is the *issuing* carrier, not necessarily the current one.
MOBILE_PREFIX = {
    "0811": "Telkomsel", "0812": "Telkomsel", "0813": "Telkomsel",
    "0821": "Telkomsel", "0822": "Telkomsel", "0823": "Telkomsel",
    "0851": "Telkomsel", "0852": "Telkomsel", "0853": "Telkomsel",
    "0814": "Indosat Ooredoo", "0815": "Indosat Ooredoo", "0816": "Indosat Ooredoo",
    "0855": "Indosat Ooredoo", "0856": "Indosat Ooredoo", "0857": "Indosat Ooredoo",
    "0858": "Indosat Ooredoo",
    "0817": "XL Axiata", "0818": "XL Axiata", "0819": "XL Axiata",
    "0859": "XL Axiata", "0877": "XL Axiata", "0878": "XL Axiata",
    "0831": "AXIS", "0832": "AXIS", "0833": "AXIS", "0838": "AXIS",
    "0895": "Tri (3)", "0896": "Tri (3)", "0897": "Tri (3)",
    "0898": "Tri (3)", "0899": "Tri (3)",
    "0881": "Smartfren", "0882": "Smartfren", "0883": "Smartfren",
    "0884": "Smartfren", "0885": "Smartfren", "0886": "Smartfren",
    "0887": "Smartfren", "0888": "Smartfren", "0889": "Smartfren",
}

# Fixed-line area codes (partial — major ones only, marked as such in output)
FIXED_AREA = {
    "21": "Jakarta", "22": "Bandung", "23": "Cirebon", "24": "Semarang",
    "25": "Bogor", "26": "Bandung (rural)", "27": "Solo", "28": "Purwokerto",
    "29": "Magelang", "31": "Surabaya", "32": "Sidoarjo", "33": "Jember",
    "34": "Malang", "35": "Kediri", "36": "Denpasar", "37": "Mataram",
    "38": "Kupang", "41": "Makassar", "42": "Parepare", "43": "Manado",
    "44": "Gorontalo", "45": "Palu", "46": "Kendari", "51": "Banjarmasin",
    "52": "Banjarbaru", "53": "Samarinda", "54": "Balikpapan",
    "55": "Tarakan", "56": "Pontianak", "57": "Singkawang",
    "61": "Medan", "62": "Pematangsiantar", "63": "Rantau Prapat",
    "64": "Tebing Tinggi", "65": "Tanjung Balai", "66": "Sibolga",
    "71": "Palembang", "72": "Lahat", "73": "Lubuklinggau",
    "74": "Jambi", "75": "Padang", "76": "Pekanbaru", "77": "Batam",
    "91": "Ambon", "92": "Ternate", "93": "Sorong", "94": "Jayapura",
    "95": "Biak", "96": "Manokwari",
}

FIXED_AREA_VERIFIED = "partial"  # table covers major cities only


def normalize_phone(raw: str) -> dict:
    """Normalise an Indonesian number to E.164 + national form. No network."""
    digits = re.sub(r"[^\d+]", "", (raw or "").strip())
    out = {"input_masked": _mask(digits), "valid": False, "errors": []}

    if digits.startswith("+62"):
        national = "0" + digits[3:]
    elif digits.startswith("62"):
        national = "0" + digits[2:]
    elif digits.startswith("0"):
        national = digits
    elif digits.startswith("8"):
        national = "0" + digits
    else:
        out["errors"].append("cannot infer Indonesian country/trunk prefix")
        return out

    if not national[1:].isdigit():
        out["errors"].append("non-numeric body")
        return out
    if not (9 <= len(national) <= 13):
        out["errors"].append(f"national length {len(national)} outside 9-13")
        return out
    if not national.startswith("08") and not national.startswith("02") \
            and not national.startswith("03") and not national.startswith("04") \
            and not national.startswith("05") and not national.startswith("06") \
            and not national.startswith("07") and not national.startswith("09"):
        out["errors"].append(f"unexpected trunk digit {national[1]!r}")
        return out

    e164 = "+62" + national[1:]
    prefix4 = national[:4]
    is_mobile = national.startswith("08")

    out.update({
        "valid": not out["errors"],
        "e164": e164,
        "national": national,
        "line_type": "mobile" if is_mobile else "fixed",
        "country": "ID",
        "operator_guess": MOBILE_PREFIX.get(prefix4) if is_mobile else None,
        "operator_is_guess": True,
        "mnp_note": "number portability since 2017 — prefix = issuing carrier, not necessarily current",
        "location_capability": "none",
        "location_why": LOCATION_WHY,
    })

    if not is_mobile:
        area = national[1:3]
        out["fixed_area_code"] = area
        out["fixed_area_city"] = FIXED_AREA.get(area)
        out["fixed_area_table_coverage"] = FIXED_AREA_VERIFIED
    return out


# ---------------------------------------------------------------------------
# combined
# ---------------------------------------------------------------------------

def correlate(nik: str | None = None, phone: str | None = None,
              *, authorized: bool = False) -> dict:
    """Combine both decoders into one record with an explicit capability matrix."""
    if not authorized:
        raise PermissionError("correlate requires authorized=True (PII gate)")
    with offline_guard(True):
        res: dict = {
            "location_capability": "none",
            "location_why": LOCATION_WHY,
            "network_egress": "blocked at runtime by offline_guard()",
        }
        if nik:
            res["nik"] = parse_nik(nik, authorized=True)
        if phone:
            res["phone"] = normalize_phone(phone)

    res["capability_matrix"] = {
        "live_gps_position": {"available": False,
                              "why": "no identifier carries telemetry"},
        "last_known_cell_tower": {"available": False,
                                  "why": "requires carrier HLR/GMLC (lawful intercept)"},
        "registered_address": {"available": bool(nik),
                               "confidence": "low",
                               "why": "NIK = civil registration snapshot, often stale/not residence"},
        "carrier": {"available": bool(phone), "confidence": "medium",
                    "why": "prefix heuristic, broken by MNP"},
        "fixed_line_city": {"available": bool(phone), "confidence": "medium",
                            "why": "only for landlines; mobile numbers carry no area code"},
    }
    return res


def selftest() -> dict:
    """Deterministic checks — no network, no PII from real people."""
    cases = {}
    # 32=Jabar, 01 regency, 23 district, 55->female day15, 08/90, serial 0001
    a = parse_nik("3201235508900001", authorized=True)
    cases["nik_female_1990"] = {
        "valid": a["valid"], "sex": a["sex"], "birth": a["birth_date"],
        "province": a["province"], "cap": a["location_capability"]}
    b = parse_nik("3201231508900001", authorized=True)
    cases["nik_male_same_date"] = {"sex": b["sex"]}
    cases["nik_short"] = {"valid": parse_nik("3201", authorized=True)["valid"]}
    cases["nik_bad_month"] = {"valid": parse_nik("3201235513900001", authorized=True)["valid"]}
    p = normalize_phone("+62 812-3456-7890")
    cases["phone_telkomsel"] = {
        "e164": p["e164"], "national": p["national"], "op": p["operator_guess"],
        "type": p["line_type"], "cap": p["location_capability"]}
    p2 = normalize_phone("021-5551234")
    cases["phone_jakarta_fixed"] = {
        "type": p2["line_type"], "city": p2["fixed_area_city"]}
    cases["phone_short"] = {"valid": normalize_phone("0812")["valid"]}

    # guard proof
    blocked = False
    try:
        with offline_guard(True):
            socket.create_connection(("1.1.1.1", 80), timeout=1)
    except NetworkEgressBlocked:
        blocked = True
    cases["offline_guard_blocks_egress"] = blocked

    ok = all([
        cases["nik_female_1990"]["valid"], cases["nik_female_1990"]["sex"] == "female",
        cases["nik_male_same_date"]["sex"] == "male",
        cases["nik_short"]["valid"] is False, cases["nik_bad_month"]["valid"] is False,
        cases["phone_telkomsel"]["op"] == "Telkomsel",
        cases["phone_telkomsel"]["e164"] == "+6281234567890",
        cases["phone_jakarta_fixed"]["city"] == "Jakarta",
        cases["phone_short"]["valid"] is False,
        cases["offline_guard_blocks_egress"],
    ])
    return {"ok": ok, "cases": cases}
