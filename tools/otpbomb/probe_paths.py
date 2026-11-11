"""Path liveness probe used by discover — POST an OTP-ish body, record status."""
from __future__ import annotations

import asyncio

import httpx

BODY_FORM = {"phone": "081234567890", "msisdn": "081234567890",
             "phone_number": "081234567890", "channel": "whatsapp"}
ALIVE = (200, 201, 202, 400, 401, 403, 405, 409, 415, 422, 429, 451)


async def probe(client: httpx.AsyncClient, base: str, paths) -> list[dict]:
    async def one(path: str) -> dict:
        rec = {"path": path, "status": 0, "alive": False, "snippet": ""}
        try:
            r = await client.post(base + path, data=BODY_FORM, timeout=8.0,
                                  follow_redirects=True)
        except Exception:  # any per-path failure is just a dead path
            return rec
        rec["status"] = r.status_code
        rec["alive"] = r.status_code in ALIVE
        rec["snippet"] = r.text[:160].replace("\n", " ")
        return rec

    return list(await asyncio.gather(*(one(p) for p in paths)))


def run(base: str, paths) -> list[dict]:
    async def _go():
        async with httpx.AsyncClient() as c:
            return await probe(c, base, paths)

    return asyncio.run(_go())
