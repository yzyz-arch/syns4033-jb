"""Geo math + offline region gazetteer for Indonesian numbering-plan and NIK work.

Everything here is offline: a curated set of province capitals and a subset of
kota/kabupaten centroids, plus distance/centroid helpers. Coordinates are
city-centre approximations, NOT device positions — `precision_km` says how
coarse each basis is so callers cannot accidentally present a province centroid
as a GPS fix.
"""
from __future__ import annotations

import math

# BPS province codes as used in the first two digits of a NIK.
# 11-92 are the long-stable set. 93/94 were created by the 2022 Papua split and
# their numbering has been reassigned more than once -> flagged, not asserted.
PROVINCES: dict[str, dict] = {
    "11": {"name": "Aceh", "capital": "Banda Aceh", "lat": 5.5483, "lon": 95.3238},
    "12": {"name": "Sumatera Utara", "capital": "Medan", "lat": 3.5952, "lon": 98.6722},
    "13": {"name": "Sumatera Barat", "capital": "Padang", "lat": -0.9471, "lon": 100.4172},
    "14": {"name": "Riau", "capital": "Pekanbaru", "lat": 0.5071, "lon": 101.4478},
    "15": {"name": "Jambi", "capital": "Jambi", "lat": -1.6101, "lon": 103.6131},
    "16": {"name": "Sumatera Selatan", "capital": "Palembang", "lat": -2.9761, "lon": 104.7754},
    "17": {"name": "Bengkulu", "capital": "Bengkulu", "lat": -3.7928, "lon": 102.2608},
    "18": {"name": "Lampung", "capital": "Bandar Lampung", "lat": -5.3971, "lon": 105.2668},
    "19": {"name": "Kepulauan Bangka Belitung", "capital": "Pangkal Pinang", "lat": -2.1316, "lon": 106.1169},
    "21": {"name": "Kepulauan Riau", "capital": "Tanjung Pinang", "lat": 0.9186, "lon": 104.4667},
    "31": {"name": "DKI Jakarta", "capital": "Jakarta", "lat": -6.2088, "lon": 106.8456},
    "32": {"name": "Jawa Barat", "capital": "Bandung", "lat": -6.9175, "lon": 107.6191},
    "33": {"name": "Jawa Tengah", "capital": "Semarang", "lat": -6.9667, "lon": 110.4167},
    "34": {"name": "DI Yogyakarta", "capital": "Yogyakarta", "lat": -7.7956, "lon": 110.3695},
    "35": {"name": "Jawa Timur", "capital": "Surabaya", "lat": -7.2575, "lon": 112.7521},
    "36": {"name": "Banten", "capital": "Serang", "lat": -6.1104, "lon": 106.1503},
    "51": {"name": "Bali", "capital": "Denpasar", "lat": -8.6705, "lon": 115.2126},
    "52": {"name": "Nusa Tenggara Barat", "capital": "Mataram", "lat": -8.5833, "lon": 116.1167},
    "53": {"name": "Nusa Tenggara Timur", "capital": "Kupang", "lat": -10.1772, "lon": 123.6070},
    "61": {"name": "Kalimantan Barat", "capital": "Pontianak", "lat": -0.0263, "lon": 109.3425},
    "62": {"name": "Kalimantan Tengah", "capital": "Palangka Raya", "lat": -2.2089, "lon": 113.9167},
    "63": {"name": "Kalimantan Selatan", "capital": "Banjarmasin", "lat": -3.3186, "lon": 114.5944},
    "64": {"name": "Kalimantan Timur", "capital": "Samarinda", "lat": -0.5022, "lon": 117.1536},
    "65": {"name": "Kalimantan Utara", "capital": "Tanjung Selor", "lat": 2.8375, "lon": 117.3667},
    "71": {"name": "Sulawesi Utara", "capital": "Manado", "lat": 1.4748, "lon": 124.8421},
    "72": {"name": "Sulawesi Tengah", "capital": "Palu", "lat": -0.8917, "lon": 119.8707},
    "73": {"name": "Sulawesi Selatan", "capital": "Makassar", "lat": -5.1477, "lon": 119.4327},
    "74": {"name": "Sulawesi Tenggara", "capital": "Kendari", "lat": -3.9450, "lon": 122.4989},
    "75": {"name": "Gorontalo", "capital": "Gorontalo", "lat": 0.5435, "lon": 123.0568},
    "76": {"name": "Sulawesi Barat", "capital": "Mamuju", "lat": -2.6748, "lon": 118.8884},
    "81": {"name": "Maluku", "capital": "Ambon", "lat": -3.6954, "lon": 128.1814},
    "82": {"name": "Maluku Utara", "capital": "Sofifi", "lat": 0.7333, "lon": 127.5667},
    "91": {"name": "Papua", "capital": "Jayapura", "lat": -2.5337, "lon": 140.7181},
    "92": {"name": "Papua Barat", "capital": "Manokwari", "lat": -0.8615, "lon": 134.0620},
    "93": {"name": "Papua (pemekaran 2022 — kode tidak stabil)", "capital": "—", "lat": -4.0, "lon": 138.0},
    "94": {"name": "Papua (pemekaran 2022 — kode tidak stabil)", "capital": "—", "lat": -5.0, "lon": 140.0},
}

# Curated subset of NIK regency/city codes (digits 3-4 + province digits 1-2).
# Unknown codes fall back to the province centroid with district_code_known=false.
CITIES: dict[str, dict] = {
    "1171": {"name": "Kota Banda Aceh", "province": "11", "lat": 5.5483, "lon": 95.3238},
    "1275": {"name": "Kota Medan", "province": "12", "lat": 3.5952, "lon": 98.6722},
    "1375": {"name": "Kota Padang", "province": "13", "lat": -0.9471, "lon": 100.4172},
    "1471": {"name": "Kota Pekanbaru", "province": "14", "lat": 0.5071, "lon": 101.4478},
    "1671": {"name": "Kota Palembang", "province": "16", "lat": -2.9761, "lon": 104.7754},
    "1871": {"name": "Kota Bandar Lampung", "province": "18", "lat": -5.3971, "lon": 105.2668},
    "3171": {"name": "Kota Jakarta Selatan", "province": "31", "lat": -6.2615, "lon": 106.8106},
    "3172": {"name": "Kota Jakarta Timur", "province": "31", "lat": -6.2250, "lon": 106.9004},
    "3173": {"name": "Kota Jakarta Pusat", "province": "31", "lat": -6.1805, "lon": 106.8284},
    "3174": {"name": "Kota Jakarta Barat", "province": "31", "lat": -6.1683, "lon": 106.7588},
    "3175": {"name": "Kota Jakarta Utara", "province": "31", "lat": -6.1214, "lon": 106.7740},
    "3176": {"name": "Kab. Kepulauan Seribu", "province": "31", "lat": -5.7500, "lon": 106.5667},
    "3271": {"name": "Kota Bogor", "province": "32", "lat": -6.5950, "lon": 106.8166},
    "3273": {"name": "Kota Bandung", "province": "32", "lat": -6.9175, "lon": 107.6191},
    "3275": {"name": "Kota Bekasi", "province": "32", "lat": -6.2383, "lon": 106.9756},
    "3276": {"name": "Kota Depok", "province": "32", "lat": -6.4025, "lon": 106.7942},
    "3374": {"name": "Kota Semarang", "province": "33", "lat": -6.9667, "lon": 110.4167},
    "3471": {"name": "Kota Yogyakarta", "province": "34", "lat": -7.7956, "lon": 110.3695},
    "3573": {"name": "Kota Malang", "province": "35", "lat": -7.9666, "lon": 112.6326},
    "3578": {"name": "Kota Surabaya", "province": "35", "lat": -7.2575, "lon": 112.7521},
    "3671": {"name": "Kota Tangerang", "province": "36", "lat": -6.1783, "lon": 106.6319},
    "3674": {"name": "Kota Tangerang Selatan", "province": "36", "lat": -6.2886, "lon": 106.7179},
    "5171": {"name": "Kota Denpasar", "province": "51", "lat": -8.6705, "lon": 115.2126},
    "6171": {"name": "Kota Pontianak", "province": "61", "lat": -0.0263, "lon": 109.3425},
    "6371": {"name": "Kota Banjarmasin", "province": "63", "lat": -3.3186, "lon": 114.5944},
    "6471": {"name": "Kota Balikpapan", "province": "64", "lat": -1.2379, "lon": 116.8529},
    "6571": {"name": "Kota Tarakan", "province": "65", "lat": 3.3273, "lon": 117.5760},
    "7171": {"name": "Kota Manado", "province": "71", "lat": 1.4748, "lon": 124.8421},
    "7371": {"name": "Kota Makassar", "province": "73", "lat": -5.1477, "lon": 119.4327},
    "8271": {"name": "Kota Ternate", "province": "82", "lat": 0.7900, "lon": 127.3800},
    "9171": {"name": "Kota Jayapura", "province": "91", "lat": -2.5337, "lon": 140.7181},
}

# Indonesian fixed-line area codes -> city key in CITIES (or province capital).
AREA_CODES: dict[str, str] = {
    "21": "3173", "22": "3273", "24": "3374", "31": "3578", "61": "1275",
    "411": "7371", "361": "5171", "274": "3471", "271": "3374", "341": "3573",
    "511": "6371", "541": "6471", "761": "1471", "711": "1671", "741": "1571",
    "751": "1375", "651": "1171", "721": "1871", "251": "3271", "561": "6171",
    "431": "7171", "911": "9171", "931": "8171", "971": "8271", "401": "7471",
    "451": "7271", "531": "5371", "5611": "6171",
}

# Extra capitals that are not in CITIES but have a stable centroid.
_EXTRA: dict[str, tuple[float, float]] = {
    "1571": (-1.6101, 103.6131),  # Jambi
    "1771": (-3.7928, 102.2608),  # Bengkulu
    "1971": (-2.1316, 106.1169),  # Pangkal Pinang
    "2171": (0.9186, 104.4667),   # Tanjung Pinang
    "5271": (-8.5833, 116.1167),  # Mataram
    "5371": (-10.1772, 123.6070), # Kupang
    "6271": (-2.2089, 113.9167),  # Palangka Raya
    "6571": (3.3273, 117.5760),   # Tarakan
    "7271": (-0.8917, 119.8707),  # Palu
    "7471": (-3.9450, 122.4989),  # Kendari
    "7571": (0.5435, 123.0568),   # Gorontalo
    "7671": (-2.6748, 118.8884),  # Mamuju
    "8171": (-3.6954, 128.1814),  # Ambon
    "9271": (-0.8615, 134.0620),  # Manokwari
}

PRECISION_PROVINCE_KM = 50.0
PRECISION_CITY_KM = 10.0
PRECISION_AREA_KM = 15.0

EARTH_R_KM = 6371.0088


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(h)))


def centroid(points: list[tuple[float, float, float]]) -> tuple[float, float]:
    """Weighted centroid from [(lat, lon, weight)]."""
    tw = sum(max(0.0, w) for _, _, w in points) or 1.0
    lat = sum(la * max(0.0, w) for la, _, w in points) / tw
    lon = sum(lo * max(0.0, w) for _, lo, w in points) / tw
    return round(lat, 6), round(lon, 6)


def bbox(lat: float, lon: float, radius_km: float) -> dict:
    """Lat/lon bounding box around a point (equirectangular approximation)."""
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(0.05, math.cos(math.radians(lat))))
    return {"min_lat": round(lat - dlat, 6), "max_lat": round(lat + dlat, 6),
            "min_lon": round(lon - dlon, 6), "max_lon": round(lon + dlon, 6)}


def city(code: str) -> dict | None:
    """Look up a NIK regency code; falls back to the extra-capital table."""
    if code in CITIES:
        return dict(CITIES[code], code=code)
    if code in _EXTRA:
        lat, lon = _EXTRA[code]
        prov = code[:2]
        name = (PROVINCES.get(prov) or {}).get("capital", code)
        return {"name": name, "province": prov, "lat": lat, "lon": lon,
                "code": code, "curated": False}
    return None


def province(code: str) -> dict | None:
    p = PROVINCES.get(code)
    if not p:
        return None
    return dict(p, code=code)


def nearest(lat: float, lon: float, limit: int = 3) -> list[dict]:
    """Nearest curated centroids — a coarse reverse-geocode, explicitly labelled."""
    out = []
    for code, p in PROVINCES.items():
        if p["lat"] == 0.0 and p["lon"] == 0.0:
            continue
        out.append({"code": code, "name": p["name"], "capital": p["capital"],
                    "lat": p["lat"], "lon": p["lon"],
                    "distance_km": round(haversine(lat, lon, p["lat"], p["lon"]), 1)})
    out.sort(key=lambda d: d["distance_km"])
    return out[:limit]


def gazetteer_summary() -> dict:
    return {"provinces": len(PROVINCES), "cities": len(CITIES),
            "area_codes": len(AREA_CODES),
            "note": "centroids are city-centre approximations, not device fixes"}
