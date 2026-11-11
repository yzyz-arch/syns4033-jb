"""Probe candidates for fix_b. Reads JSON candidates from stdin, prints results as JSON."""
import asyncio, json, sys, time
import httpx

UA = ("Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")

CTX = {"local": "081234567890", "digits": "6281234567890", "e164": "+6281234567890",
       "cc": "62", "uuid": "9f1b3c5d7e9a2b4c6d8e0f1a2b3c4d5e", "ts": str(int(time.time()*1000)),
       "rand16": "a1b2c3d4e5f60718"}

BASE = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "sec-ch-ua-mobile": "?1",
    "user-agent": UA,
}

def r(s):
    for k, v in CTX.items():
        s = s.replace("{" + k + "}", v)
    return s

def rnode(n):
    if isinstance(n, str): return r(n)
    if isinstance(n, dict): return {r(k): rnode(v) for k, v in n.items()}
    return n

async def one(cl, c, sem):
    async with sem:
        url = r(c["url"])
        h = dict(BASE)
        if "://" in url:
            o = "/".join(url.split("/")[:3])
            h["origin"] = o
            h["referer"] = o + "/"
        form = c.get("form")
        jsb = c.get("json_body")
        if jsb is not None: h["content-type"] = "application/json"
        elif form is not None: h["content-type"] = "application/x-www-form-urlencoded"
        h.update({k: r(v) for k, v in c.get("headers", {}).items()})
        t0 = time.perf_counter()
        try:
            resp = await cl.request(c.get("method", "POST"), url,
                                    data=rnode(form) if form else None,
                                    json=rnode(jsb) if jsb is not None else None,
                                    headers=h, timeout=15, follow_redirects=c.get("follow", True))
            body = resp.text[:600]
            st = resp.status_code
            hdrs = {k.lower(): v for k, v in resp.headers.items() if k.lower() in
                    ("content-type", "location", "server", "cf-mitigated")}
        except Exception as e:
            st, body, hdrs = 0, f"{type(e).__name__}: {e}", {}
        return {"id": c.get("id", url), "status": st, "ms": int((time.perf_counter()-t0)*1000),
                "body": " ".join(body.split())[:400], "h": hdrs,
                "req": {"m": c.get("method", "POST"), "u": url,
                        "body": json.dumps(rnode(form) if form is not None else rnode(jsb))[:300]}}

async def main(cands):
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(http2=False, verify=False, timeout=15) as cl:
        out = await asyncio.gather(*(one(cl, c, sem) for c in cands), return_exceptions=True)
    print(json.dumps([o for o in out if isinstance(o, dict)], indent=1))

if __name__ == "__main__":
    asyncio.run(main(json.load(sys.stdin)))
