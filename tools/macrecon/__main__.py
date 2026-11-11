"""macrecon - macOS / Apple network-services discovery and fingerprinting.

Runs from Linux; no macOS host needed for discovery or fingerprinting.

  python3 -m macrecon discover [--seconds 6] [--json]
  python3 -m macrecon query <host|224.0.0.251> [--name _rfb._tcp.local.] [--port 5353]
  python3 -m macrecon probe <host> [--ports 22,3031,3283,5900] [--peek]
  python3 -m macrecon plan <host> [--rfb-types 2,36] [--json]
  python3 -m macrecon frames --path /etc/sudoers.d/x --data hello [--mode 600]
  python3 -m macrecon wordlist <file> [--width 8]
  python3 -m macrecon selftest
"""

from __future__ import annotations

import argparse
import json
import sys

from . import dnswire, mdns, plan, probe, selftest


def cmd_discover(args: argparse.Namespace) -> int:
    res = mdns.enumerate_multicast(seconds=args.seconds)
    if res.get("error"):
        print(res["error"], file=sys.stderr)
        return 2
    rows = mdns.build_service_map(res["records"])
    if args.json:
        print(json.dumps({"service_types": res["service_types"], "services": rows}, indent=2))
        return 0
    print(f"advertised service types ({len(res['service_types'])}):")
    for stype in res["service_types"]:
        print(f"  {stype}")
    print(f"\nresolved services ({len(rows)}):")
    if not rows:
        print("  none - no mDNS responder answered on this segment")
    for row in rows:
        txt = f" txt={row['txt']}" if row["txt"] else ""
        print(f"  [{row['risk']:<8}] {row['instance']:<28} {row['service_type']:<24} "
              f"{row['ip'] or '?':<16} :{row['port']}{txt}")
        print(f"             {row['label']} - {row['notes']}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    res = mdns.query(args.host, port=args.port, name=args.name,
                     qtype=dnswire.TYPE_ANY, timeout=args.timeout)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"{len(res['records'])} records from {res['target']}:{res['port']} for {res['qname']}")
    for r in res["records"]:
        print(f"  {r['type']:<5} {r['name']:<40} {r['value']}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    ports = [int(p) for p in args.ports.split(",") if p.strip()] if args.ports else None
    if args.peek and ports and 5900 in ports:
        fp = probe.rfb_fingerprint(args.host, 5900, timeout=args.timeout, auth_peek=True)
        data = fp
    else:
        data = probe.probe_host(args.host, ports=ports, timeout=args.timeout)
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    if "open" in data:
        print(f"{data['host']}: {len(data['open'])} open ports")
        for r in data["open"]:
            print(f"  {r['port']:<6} open   {r['banner'][:60]}")
        if data.get("rfb"):
            f = data["rfb"]
            print(f"  RFB {f['version']} apple={f['apple_screensharing']} "
                  f"types={f['security_types']} {f['auth_peek']}")
    else:
        print(f"{data['host']}:{data['port']} state={data['state']} rfb={data['version']} "
              f"apple={data['apple_screensharing']} types={data['security_types']}")
        for d in data.get("security_detail", []):
            print(f"  type {d['id']:<3} {d['name']:<32} [{d.get('risk', '-'):<8}] {d['note']}")
        if data.get("auth_peek"):
            print(f"  peek: {data['auth_peek']}")
        if data.get("error"):
            print(f"  error: {data['error']}", file=sys.stderr)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    rfb_json = {"security_types": [int(t) for t in args.rfb_types.split(",") if t],
                "version": args.version}
    p = plan.plan_for(args.host, rfb_json)
    if args.json:
        print(json.dumps(p, indent=2))
        return 0
    for section in ("discovery", "screen_sharing", "remote_apple_events",
                    "post_foothold", "detection", "opsec"):
        print(f"\n[{section}]")
        for line in p[section]:
            print(f"  {line}")
    return 0


def cmd_frames(args: argparse.Namespace) -> int:
    content = args.data.encode()
    frames = plan.build_writer_stream(args.path, content, int(args.mode, 8))
    print(f"path={args.path} size={len(content)} mode={args.mode} bytes={len(frames)}")
    print(frames.hex())
    return 0


def cmd_wordlist(args: argparse.Namespace) -> int:
    with open(args.file, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    out = plan.truncate_wordlist(lines, width=args.width)
    for pw in out:
        print(pw)
    print(f"# {len(lines)} input lines -> {len(out)} unique {args.width}-char prefixes",
          file=sys.stderr)
    return 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    return selftest.run()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="macrecon", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="multicast DNS-SD sweep of the local segment")
    d.add_argument("--seconds", type=float, default=6.0)
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_discover)

    q = sub.add_parser("query", help="single mDNS/DNS query (multicast or unicast)")
    q.add_argument("host")
    q.add_argument("--name", default="_services._dns-sd._udp.local.")
    q.add_argument("--port", type=int, default=5353)
    q.add_argument("--timeout", type=float, default=3.0)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_query)

    pr = sub.add_parser("probe", help="TCP probe + RFB/EPPC fingerprint")
    pr.add_argument("host")
    pr.add_argument("--ports", default="22,88,445,548,3031,3283,4488,5900")
    pr.add_argument("--timeout", type=float, default=2.0)
    pr.add_argument("--peek", action="store_true", help="pull the first auth block on 5900")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=cmd_probe)

    pl = sub.add_parser("plan", help="generate the operator command set for a host")
    pl.add_argument("host")
    pl.add_argument("--rfb-types", default="")
    pl.add_argument("--version", default="")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_plan)

    fr = sub.add_parser("frames", help="encode documented ARD 0x22 file-copy frames")
    fr.add_argument("--path", required=True)
    fr.add_argument("--data", default="")
    fr.add_argument("--mode", default="600")
    fr.set_defaults(func=cmd_frames)

    wl = sub.add_parser("wordlist", help="dedupe a wordlist by 8-char prefix")
    wl.add_argument("file")
    wl.add_argument("--width", type=int, default=8)
    wl.set_defaults(func=cmd_wordlist)

    st = sub.add_parser("selftest", help="verify everything against local fakes")
    st.set_defaults(func=cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
