#!/usr/bin/env python3
"""rp — replay satu entri provider persis seperti engine: pre_url + extract +
verdict. Alat bukti (evidence), bukan pengganti blast.

    python3 -m otpbomb.rp spec.json            # dari file spec
    python3 -m otpbomb.rp --name tokopedia     # entri bawaan registry

Isi spec.json = satu objek Provider, plus opsional:
    "ctx": {"digits": "..."}       override nomor
    "extra_headers": {"x-y": "z"}  header tambahan

Kode keluar: 0 ok, 1 fail, 2 blocked, 3 error.
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx

from .engine import Engine, Options, classify, http2_ok
from .phone import PhoneError, normalise, render, render_str
from .providers import Provider, by_name
from typing import cast

VERDICT_EXIT = {"ok": 0, "fail": 1, "blocked": 2, "error": 3}


def _spec(argv: list[str]) -> tuple[Provider, dict, dict]:
    if "--name" in argv:
        name = argv[argv.index("--name") + 1]
        prov = by_name(name)
        if prov is None:
            sys.exit(f"[!] provider tidak dikenal: {name}")
        return prov, {}, {}
    path = [a for a in argv if not a.startswith("-")]
    if not path:
        sys.exit(__doc__)
    with open(path[0], encoding="utf-8") as fh:
        spec = json.load(fh)
    ctx_over = spec.pop("ctx", {}) or {}
    extra = spec.pop("extra_headers", {}) or {}
    if not spec.get("name"):
        spec["name"] = "replay"
    return Provider.from_dict(spec), ctx_over, extra


async def main(argv: list[str]) -> int:
    prov, ctx_over, extra = _spec(argv)
    phone = argv[argv.index("--phone") + 1] if "--phone" in argv else "081234567890"
    try:
        ctx = normalise(phone)
    except PhoneError as exc:
        sys.exit(f"[!] {exc}")
    ctx.update({k: str(v) for k, v in ctx_over.items()})

    opts = Options(retries=0, concurrency=1, extra_headers=extra, verbose=True)
    eng = Engine(ctx, opts)

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0,
                                 verify=not (prov.insecure or "--insecure" in argv),
                                 http2=http2_ok()) as client:
        tokens = await eng._prefetch(client, prov)
        form = cast(dict, render(prov.form, ctx)) if prov.form else None
        js = cast(dict, render(prov.json_body, ctx)) if prov.json_body else None
        headers = eng._headers(prov)
        for key, val in tokens.items():
            if key.startswith("h:"):
                headers[key[2:]] = val
            elif form is not None:
                form[key[2:]] = val
            elif js is not None:
                js[key[2:]] = val

        url = render_str(prov.url, ctx)
        print(f"REQ     {prov.method} {url}")
        print(f"HEADERS {json.dumps(headers, ensure_ascii=False)}")
        if form:
            print(f"FORM    {form}")
        if js:
            print(f"JSON    {json.dumps(js, ensure_ascii=False)}")
        if tokens:
            print(f"TOKENS  {list(tokens)}")

        from .engine import classify

        try:
            r = await client.request(prov.method, url, data=form, json=js, headers=headers)
        except Exception as exc:
            print(f"EXC     {type(exc).__name__}: {exc}")
            return 3
        body = r.text
        verdict = classify(r.status_code, body[:400], prov)
        print(f"STATUS  {r.status_code}")
        print(f"CT      {r.headers.get('content-type')}")
        print(f"BODY    {body[:1200]}")
        print(f"VERDICT {verdict}")
        return VERDICT_EXIT.get(verdict, 3)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
