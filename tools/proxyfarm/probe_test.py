import asyncio, json, random, re, sys
import aiohttp
from pathlib import Path

BASE = Path(__file__).parent
cands = [l.split("\t")[0] for l in (BASE / "state/candidates.tsv").read_text().splitlines() if l]
random.shuffle(cands)
sample = [c for c in cands if ":3" in c or ":8" in c][:150]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/133.0.0.0"

async def hit(sess, proxy, url):
    ip, _, port = proxy.partition(":")
    try:
        async with sess.get(url, proxy=f"http://{ip}:{port}", headers={"User-Agent": UA},
                            timeout=aiohttp.ClientTimeout(total=6), ssl=False) as r:
            if r.status == 200:
                return (await r.text(errors="ignore"))[:40].strip()
    except Exception:
        return None

async def main():
    conn = aiohttp.TCPConnector(limit=200, force_close=True)
    async with aiohttp.ClientSession(connector=conn) as sess:
        h = await asyncio.gather(*(hit(sess, c, "http://api.ipify.org?format=json") for c in sample))
        await asyncio.sleep(1)
        s = await asyncio.gather(*(hit(sess, c, "https://api.ipify.org?format=json") for c in sample))
    ph = [(c, r) for c, r in zip(sample, h) if r and re.search(r"\d+\.\d+\.\d+\.\d+", r)]
    ps = [(c, r) for c, r in zip(sample, s) if r and re.search(r"\d+\.\d+\.\d+\.\d+", r)]
    print(f"plain-http alive {len(ph)}/{len(sample)}   https-connect alive {len(ps)}/{len(sample)}")
    print("http sample:", ph[:5])

asyncio.run(main())
