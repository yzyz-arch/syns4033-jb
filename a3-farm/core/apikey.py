"""Gemini API key verification, health check, and quota probing."""
from __future__ import annotations
import time
from typing import Any

import requests

from .config import GENLANG_BASE, MODELS_URL, GENERATE_URL, DEFAULT_MODEL, REQUEST_TIMEOUT

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "a3-farm/1.0"})


def list_models(key: str) -> dict[str, Any]:
    """GET /v1beta/models — cheap, no token cost. Returns {ok, status, models|error}."""
    t0 = time.time()
    try:
        r = SESSION.get(MODELS_URL, params={"key": key}, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        return {"ok": False, "status": 0, "error": f"{type(e).__name__}: {e}",
                "latency_ms": int((time.time() - t0) * 1000)}
    lat = int((time.time() - t0) * 1000)
    if r.status_code == 200:
        data = r.json()
        names = [m.get("name", "") for m in data.get("models", [])]
        return {"ok": True, "status": 200, "models": names, "count": len(names),
                "latency_ms": lat, "raw": data}
    return {"ok": False, "status": r.status_code, "error": r.text[:800], "latency_ms": lat}


def classify_error(status: int, body: str) -> str:
    """Map HTTP status / body to a key status: active|quota|invalid|disabled|unknown."""
    b = (body or "").lower()
    if status == 200:
        return "active"
    if status == 429:
        return "quota"
    if status in (401, 403):
        if "api key not valid" in b or "invalid" in b or "api_key_invalid" in b:
            return "invalid"
        if "permission" in b or "disabled" in b or "has not been used" in b:
            return "disabled"
        return "invalid"
    if status == 400:
        if "api key not valid" in b or "invalid" in b:
            return "invalid"
        return "unknown"
    return "unknown"


def probe_generate(key: str, model: str = DEFAULT_MODEL, prompt: str = "ping") -> dict[str, Any]:
    """Minimal generateContent call. Costs a few tokens; confirms real usability."""
    url = GENERATE_URL.format(model=model)
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    t0 = time.time()
    try:
        r = SESSION.post(url, params={"key": key}, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        return {"ok": False, "status": 0, "error": f"{type(e).__name__}: {e}",
                "latency_ms": int((time.time() - t0) * 1000)}
    lat = int((time.time() - t0) * 1000)
    out: dict[str, Any] = {"status": r.status_code, "latency_ms": lat,
                           "class": classify_error(r.status_code, r.text)}
    if r.status_code == 200:
        try:
            data = r.json()
            txt = (data.get("candidates", [{}])[0]
                   .get("content", {}).get("parts", [{}])[0].get("text", ""))
            out.update(ok=True, text=txt[:200])
            um = data.get("usageMetadata", {})
            out["usage"] = {k: um.get(k) for k in
                            ("promptTokenCount", "candidatesTokenCount", "totalTokenCount")}
        except (ValueError, IndexError, KeyError) as e:
            out.update(ok=False, error=f"parse: {e}")
    else:
        out.update(ok=False, error=r.text[:800])
    return out
