"""A3 farm CLI.

Subcommands:
  import-key KEY [KEY...]     store raw key(s) into the pool
  import-keys FILE            one key per line / jsonl
  verify [--gen] [--model M]  verify all keys (list-models); --gen does a real call
  test-key KEY [--model M]    single key end-to-end
  ask PROMPT [--model M]      run a prompt through the balancer (proof of throughput)
  bench N [--concurrency C]   run N generate calls, report RPM/ok/429
  health                      balancer cooldown state
  stats                       DB counters
  export [PATH]               dump keys to jsonl (default data/keys.jsonl)
  serve --port 8787           OpenAI-ish /v1/chat/completions proxy over the pool
  login-google EMAIL          open a browser to log into a Google account (manual/vault)
  make-keys --email E [--n N] browser: create up to N AI Studio projects+keys for account
  farm --accounts FILE [--n N]  bulk: one AI Studio key per account via browser
"""
from __future__ import annotations
import argparse
import json
import sys
import time

from core import config
from core.db import Store, load_accounts_jsonl
from core.balancer import KeyPool, mask
from core import apikey


def cmd_import_key(a):
    st = Store()
    for k in a.keys:
        st.add_key(k.strip())
    print(f"[+] imported {len(a.keys)} key(s); total={st.stats()['keys_total']}")


def cmd_import_keys(a):
    st = Store()
    n = 0
    with open(a.file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("{"):
                try:
                    line = json.loads(line).get("key", "")
                except json.JSONDecodeError:
                    continue
            if line:
                st.add_key(line)
                n += 1
    print(f"[+] imported {n} key(s); total={st.stats()['keys_total']}")


def cmd_verify(a):
    st = Store()
    keys = [k["key"] for k in st.keys_table()] if not a.key else [a.key]
    if not keys:
        print("[!] no keys in pool"); return
    ok = q = inv = 0
    for k in keys:
        if a.gen:
            res = apikey.probe_generate(k, a.model)
        else:
            res = apikey.list_models(k)
        cls = apikey.classify_error(res.get("status", 0), res.get("error", "")) if not res.get("ok") else "active"
        st.bump_key(k, res.get("ok", False), res.get("status", 0), res.get("error", ""))
        if cls != "active":
            st.set_key_status(k, cls, res.get("error", "")[:300])
        tag = "OK " if res.get("ok") else cls.upper()
        extra = ""
        if res.get("ok") and not a.gen:
            extra = f"models={res.get('count')}"
        elif res.get("ok"):
            extra = f"say={res.get('text','')[:40]!r}"
        print(f"  {mask(k):<20} {tag:<8} {res.get('status')} {extra} {res.get('latency_ms')}ms")
        if res.get("ok"): ok += 1
        elif cls == "quota": q += 1
        elif cls == "invalid": inv += 1
    print(f"[=] verified ok={ok} quota={q} invalid={inv} total={len(keys)}")


def cmd_test_key(a):
    res = apikey.probe_generate(a.key, a.model) if a.gen else apikey.list_models(a.key)
    print(json.dumps(res, indent=2)[:2000])


def cmd_ask(a):
    st = Store()
    pool = KeyPool(st.active_keys(), on_event=lambda e: None)
    if not pool.keys:
        print("[!] pool empty — import keys first"); return
    t0 = time.time()
    res = pool.generate(a.prompt, model=a.model)
    print(json.dumps({**res, "wall_ms": int((time.time() - t0) * 1000)}, indent=2)[:3000])
    st.log_usage(res.get("key") or "", res.get("model", ""), res["ok"], 200 if res["ok"] else 0,
                 res["latency_ms"], res.get("error", ""))


def cmd_bench(a):
    import concurrent.futures as cf
    st = Store()
    pool = KeyPool(st.active_keys())
    if not pool.keys and not a.key:
        print("[!] pool empty — import keys first"); return
    if a.key:
        pool.keys = [a.key]
        pool._stats = {a.key: {"ok": 0, "fail": 0, "429": 0}}
    prompt = a.prompt
    t0 = time.time()
    ok = fail = 0
    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = [ex.submit(pool.generate, prompt, a.model, 256) for _ in range(a.n)]
        for i, f in enumerate(cf.as_completed(futs), 1):
            r = f.result()
            if r["ok"]: ok += 1
            else: fail += 1
            if i % max(1, a.n // 10) == 0 or i == a.n:
                print(f"  [{i}/{a.n}] ok={ok} fail={fail}")
    wall = time.time() - t0
    print(json.dumps({
        "n": a.n, "ok": ok, "fail": fail,
        "wall_s": round(wall, 2),
        "throughput_rps": round(a.n / wall, 2) if wall else 0,
        "rpm_effective": round(a.n / wall * 60, 1) if wall else 0,
        "keys": len(pool.keys),
        "health": pool.health()["in_cooldown"],
    }, indent=2))


def cmd_health(a):
    st = Store()
    pool = KeyPool(st.active_keys())
    print(json.dumps(pool.health(), indent=2))


def cmd_stats(a):
    print(json.dumps(Store().stats(), indent=2))


def cmd_export(a):
    st = Store()
    n = st.export_keys_jsonl(a.path or config.KEYS_OUT)
    print(f"[+] exported {n} keys -> {a.path or config.KEYS_OUT}")


def cmd_serve(a):
    from core.server import run_server
    run_server(host=a.host, port=a.port)


def cmd_login_google(a):
    from core.google_login import login_flow
    login_flow(a.email, headless=a.headless, proxy=a.proxy)


def cmd_make_keys(a):
    from core.aistudio_ui import make_keys_for_account
    make_keys_for_account(a.email, max_keys=a.n, headless=a.headless, proxy=a.proxy,
                          model=a.model)


def cmd_farm(a):
    from core.farm import run_farm
    run_farm(a.accounts, max_keys=a.n, headless=a.headless, proxy=a.proxy, workers=a.workers)


def main(argv=None):
    p = argparse.ArgumentParser(prog="a3farm", description="A3 Gemini free-tier key farm")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("import-key"); s.add_argument("keys", nargs="+"); s.set_defaults(fn=cmd_import_key)
    s = sub.add_parser("import-keys"); s.add_argument("file"); s.set_defaults(fn=cmd_import_keys)
    s = sub.add_parser("verify"); s.add_argument("key", nargs="?"); s.add_argument("--gen", action="store_true"); s.add_argument("--model", default=config.DEFAULT_MODEL); s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("test-key"); s.add_argument("key"); s.add_argument("--gen", action="store_true"); s.add_argument("--model", default=config.DEFAULT_MODEL); s.set_defaults(fn=cmd_test_key)
    s = sub.add_parser("ask"); s.add_argument("prompt"); s.add_argument("--model", default=None); s.set_defaults(fn=cmd_ask)
    s = sub.add_parser("bench"); s.add_argument("n", type=int); s.add_argument("--prompt", default="reply with the single word: pong"); s.add_argument("--model", default=None); s.add_argument("--concurrency", type=int, default=8); s.add_argument("--key", default=None); s.set_defaults(fn=cmd_bench)
    s = sub.add_parser("health"); s.set_defaults(fn=cmd_health)
    s = sub.add_parser("stats"); s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("export"); s.add_argument("path", nargs="?"); s.set_defaults(fn=cmd_export)
    s = sub.add_parser("serve"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8787); s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("login-google"); s.add_argument("email"); s.add_argument("--headless", action="store_true"); s.add_argument("--proxy", default=None); s.set_defaults(fn=cmd_login_google)
    s = sub.add_parser("make-keys"); s.add_argument("--email", required=True); s.add_argument("--n", type=int, default=10); s.add_argument("--model", default=config.DEFAULT_MODEL); s.add_argument("--headless", action="store_true"); s.add_argument("--proxy", default=None); s.set_defaults(fn=cmd_make_keys)
    s = sub.add_parser("farm"); s.add_argument("--accounts", required=True); s.add_argument("--n", type=int, default=1); s.add_argument("--workers", type=int, default=1); s.add_argument("--headless", action="store_true"); s.add_argument("--proxy", default=None); s.set_defaults(fn=cmd_farm)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
