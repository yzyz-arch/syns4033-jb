"""NIK (Nomor Induk Kependudukan) parsing — deterministic, fully offline.

A NIK is 16 digits: PPRRSS-DDMMYY-NNNN

    PP    province code (BPS)
    RR    regency / city code within the province
    SS    district (kecamatan) code
    DD    day of birth, +40 for female
    MM    month of birth
    YY    two-digit year of birth
    NNNN  serial, makes the number unique within district+DOB+sex

There is no public API mapping a NIK to a name and street address; what the
digits encode is region + DOB + sex, and that is exactly what this module
returns. Anything beyond that needs an authorized dataset, not the number.
"""
from __future__ import annotations

import datetime as _dt
import re

from . import geoloc

_NIK_RE = re.compile(r"^\d{16}$")


def normalize(raw: str) -> str:
    """Strip separators/whitespace commonly pasted along with a NIK."""
    return re.sub(r"[^0-9]", "", str(raw or ""))


def _parse_dob(day_raw: int, month: int, yy: int) -> dict:
    female = day_raw > 40
    day = day_raw - 40 if female else day_raw
    # NIK has no century: assume the most recent year that does not put the
    # person in the future. A birth year > current year rolls back 100 years.
    now = _dt.date.today()
    year = 2000 + yy
    if year > now.year:
        year -= 100
    errors = []
    try:
        dob = _dt.date(year, month, day)
    except ValueError as e:
        return {"female": female, "day": day, "month": month, "year": year,
                "date": None, "age": None, "errors": [f"invalid date: {e}"]}
    if dob > now:
        errors.append("date of birth is in the future")
    age = (now - dob).days // 365
    return {"female": female, "day": day, "month": month, "year": year,
            "date": dob.isoformat(), "age": age, "errors": errors}


def parse(raw: str) -> dict:
    """Full structural parse of a NIK. Never raises on bad input."""
    nik = normalize(raw)
    out: dict = {"input": str(raw), "nik": nik, "length": len(nik),
                 "valid": False, "errors": [], "warnings": []}

    if len(nik) != 16:
        out["errors"].append(f"expected 16 digits, got {len(nik)}")
        return out

    prov_code = nik[0:2]
    reg_code = nik[0:4]
    dist_code = nik[0:6]
    dd = int(nik[6:8])
    mm = int(nik[8:10])
    yy = int(nik[10:12])
    serial = nik[12:16]

    prov = geoloc.province(prov_code)
    city = geoloc.city(reg_code)

    if prov is None:
        out["errors"].append(f"unknown province code '{prov_code}'")
    elif prov_code in ("93", "94"):
        out["warnings"].append(
            "province code from the 2022 Papua split — numbering has been "
            "reassigned more than once, treat the name as provisional")

    if city is None:
        out["warnings"].append(
            f"regency code '{reg_code}' not in the curated table; only the "
            "province can be resolved")
    elif city.get("province") and prov_code and city["province"] != prov_code:
        out["errors"].append(
            f"regency '{reg_code}' belongs to province {city['province']}, "
            f"not {prov_code}")

    dob = _parse_dob(dd, mm, yy)
    out["errors"].extend(dob.pop("errors"))
    if serial == "0000":
        out["warnings"].append("serial 0000 is unusual for an issued NIK")

    # Geo fallback chain: regency centroid -> province capital
    basis, lat, lon, precision = None, None, None, None
    if city:
        lat, lon = city["lat"], city["lon"]
        basis, precision = f"regency centroid: {city['name']}", geoloc.PRECISION_CITY_KM
    elif prov:
        lat, lon = prov["lat"], prov["lon"]
        basis, precision = f"province capital: {prov['capital']}", geoloc.PRECISION_PROVINCE_KM

    out.update({
        "valid": not out["errors"],
        "province_code": prov_code,
        "province": (prov or {}).get("name"),
        "regency_code": reg_code,
        "regency": (city or {}).get("name"),
        "district_code": dist_code,
        "district_code_known": False,  # no curated kecamatan table shipped
        "sex": "female" if dob["female"] else "male",
        "dob": dob["date"],
        "age": dob["age"],
        "serial": serial,
        "geo": ({"lat": lat, "lon": lon, "basis": basis,
                 "precision_km": precision, "is_device_fix": False}
                if lat is not None else None),
        "bbox": geoloc.bbox(lat, lon, precision) if lat is not None else None,
        "note": "region + DOB + sex only; NIK carries no name or street address",
    })
    return out


def bulk(raw_list: list[str]) -> dict:
    rows = [parse(x) for x in raw_list]
    valid = [r for r in rows if r["valid"]]
    by_prov: dict[str, int] = {}
    for r in valid:
        p = r.get("province") or "unknown"
        by_prov[p] = by_prov.get(p, 0) + 1
    return {"count": len(rows), "valid": len(valid), "invalid": len(rows) - len(valid),
            "by_province": dict(sorted(by_prov.items(), key=lambda kv: -kv[1])),
            "results": rows}


def generate(province_code: str, regency_code: str, district_code: str,
             dob: str, female: bool, serial: int = 1) -> dict:
    """Build a structurally valid NIK — for lab fixtures and validation tests.

    `dob` is ISO (YYYY-MM-DD). This does not create a real person's identity; it
    builds a checksum-plausible string for testing parsers.
    """
    try:
        d = _dt.date.fromisoformat(dob)
    except ValueError as e:
        return {"ok": False, "error": f"bad dob: {e}"}
    day = d.day + (40 if female else 0)
    nik = f"{province_code}{regency_code}{district_code}{day:02d}{d.month:02d}{d.year % 100:02d}{serial:04d}"
    parsed = parse(nik)
    return {"ok": parsed["valid"], "nik": nik, "parsed": parsed}
