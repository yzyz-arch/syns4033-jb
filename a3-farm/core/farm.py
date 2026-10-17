"""Bulk farm orchestrator: run make_keys_for_account across many accounts in
parallel browser workers, append per-account results to data/claim_results.jsonl.
"""
from __future__ import annotations
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import RESULTS
from .db import Store, load_accounts_jsonl
from .aistudio_ui import make_keys_for_account


def _one(acc: dict, max_keys: int, headless: bool, proxy: str | None) -> dict:
    email = acc.get("email")
    if not email:
        return {"ok": False, "email": "", "error": "missing email"}
    t0 = time.time()
    try:
        res = make_keys_for_account(email, max_keys=max_keys, headless=headless,
                                    proxy=proxy or acc.get("proxy"))
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "email": email, "error": f"{type(e).__name__}: {e}", "keys": []}
    res["wall_s"] = round(time.time() - t0, 1)
    return res


def run_farm(accounts_file: str, max_keys: int = 1, headless: bool = True,
             proxy: str | None = None, workers: int = 1) -> dict:
    accounts = load_accounts_jsonl(accounts_file)
    if not accounts:
        print(f"[!] no accounts in {accounts_file}")
        return {"ok": False, "error": "no accounts"}
    st = Store()
    for a in accounts:
        st.upsert_account(a.get("email", ""), a.get("password_ref", ""),
                          a.get("recovery", ""), status=a.get("status", "new"))
    print(f"[*] farming {len(accounts)} account(s), max_keys={max_keys}, workers={workers}")

    ok = fail = 0
    total_keys = 0
    with open(RESULTS, "a", encoding="utf-8") as out, ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one, a, max_keys, headless, proxy): a for a in accounts}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            out.write(json.dumps(r) + "\n")
            out.flush()
            total_keys += len(r.get("keys", []))
            if r.get("ok"):
                ok += 1
            else:
                fail += 1
            print(f"  [{i}/{len(accounts)}] {r.get('email')} "
                  f"{'OK' if r.get('ok') else 'FAIL'} keys={len(r.get('keys', []))} "
                  f"{r.get('error','')[:60]}")
    summary = {"accounts": len(accounts), "ok": ok, "fail": fail, "keys_total": total_keys,
               "results_file": str(RESULTS), "db": st.stats()}
    print(json.dumps(summary, indent=2))
    return summary
