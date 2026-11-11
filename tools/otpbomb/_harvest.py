import re, sys, asyncio, httpx, json
UA = ("Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
H = {"user-agent": UA, "accept": "text/html,application/xhtml+xml,*/*",
     "accept-language": "id-ID,id;q=0.9,en;q=0.8"}

async def main(urls):
    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=20) as cl:
        for u in urls:
            try:
                r = await cl.get(u, headers=H)
            except Exception as e:
                print(f"== {u} ERR {type(e).__name__}"); continue
            body = r.text
            print(f"== {u} -> {r.status_code} {len(body)}B")
            hosts = set(re.findall(r"https?://([a-z0-9][a-z0-9.\-]+\.[a-z]{2,})", body, re.I))
            for h in sorted(hosts):
                print("   H", h)
            srcs = re.findall(r'(?:src|href)="([^"]+\.js[^"]*)"', body)
            for s in srcs[:12]:
                print("   JS", s)
            for kw in ("otp", "sendOtp", "send-otp", "send_otp", "whatsapp"):
                for m in set(re.findall(r"[^\"' ]{0,60}" + kw + r"[^\"' ]{0,60}", body, re.I)):
                    print("   KW", m[:120])
asyncio.run(main(sys.argv[1:]))
