"""DNS intelligence: records, SPF/DMARC/DKIM posture, zone transfer, subdomain enum."""
from __future__ import annotations
import concurrent.futures as cf
import socket
import dns.resolver, dns.zone, dns.query, dns.exception

from . import net
from .http import get_json

RECORD_TYPES = ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME", "CAA", "SRV"]


def _resolver() -> dns.resolver.Resolver:
    r = dns.resolver.Resolver()
    r.timeout = 5
    r.lifetime = 8
    return r


def records(domain: str) -> dict:
    """Records over DoH first.

    Large TXT RRsets (SPF + dozens of verification tokens) get truncated over
    UDP/53 and dnspython then returns an empty answer — which produced false
    "no SPF" findings. DoH returns the full set, so it is the primary path and
    dnspython is only a fallback.
    """
    out: dict[str, list[str]] = {}
    try:
        a = net.a(domain)
        if a:
            out["A"] = a
        aaaa = net.aaaa(domain)
        if aaaa:
            out["AAAA"] = aaaa
        mx = net.mx(domain)
        if mx:
            out["MX"] = [f"{m['priority']} {m['host']}" for m in mx]
        ns = net.ns(domain)
        if ns:
            out["NS"] = ns
        txt = net.txt(domain)
        if txt:
            out["TXT"] = txt
        soa = net.soa(domain)
        if soa:
            out["SOA"] = [soa.get("raw") or " ".join(str(v) for v in soa.values())]
        cn = net.cname(domain)
        if cn:
            out["CNAME"] = cn
        caa = net.caa(domain)
        if caa:
            out["CAA"] = [f'{c["flags"]} {c["tag"]} "{c["value"]}"' for c in caa]
        srv = [str(x.get("data", "")) for x in net.query(domain, "SRV")]
        if srv:
            out["SRV"] = srv
    except Exception:
        pass

    missing = [rt for rt in RECORD_TYPES if rt not in out]
    if missing:
        r = _resolver()
        for rt in missing:
            try:
                ans = r.resolve(domain, rt)
                out[rt] = [x.to_text() for x in ans]
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                    dns.resolver.NoNameservers, dns.exception.Timeout):
                continue
    return out


def security_posture(domain: str) -> dict:
    """SPF / DMARC / DKIM / MTA-STS / BIMI audit (DoH first, resolver fallback)."""
    post: dict = {"spf": None, "dmarc": None, "dkim_selectors": [], "mta_sts": None,
                  "bimi": None, "source": "doh"}

    spf_candidates = [t for t in net.txt(domain) if t.lower().startswith("v=spf1")]
    if spf_candidates:
        post["spf"] = spf_candidates[0]
    else:
        try:
            for txt in _resolver().resolve(domain, "TXT"):
                t = txt.to_text().strip('"')
                if t.startswith("v=spf1"):
                    post["spf"] = t
                    post["source"] = "resolver"
                    break
        except Exception:
            pass

    for t in net.txt(f"_dmarc.{domain}"):
        if t.lower().startswith("v=dmarc1"):
            post["dmarc"] = t
            break
    if not post["dmarc"]:
        try:
            for txt in _resolver().resolve(f"_dmarc.{domain}", "TXT"):
                t = txt.to_text().strip('"')
                if t.startswith("v=DMARC1"):
                    post["dmarc"] = t
                    post["source"] = "resolver"
                    break
        except Exception:
            pass

    for sel in ("default", "google", "selector1", "selector2", "k1", "mail", "dkim",
                "s1", "s2", "mandrill", "sendgrid", "amazonses", "postmark", "resend"):
        vals = net.txt(f"{sel}._domainkey.{domain}")
        if not vals:
            try:
                vals = [ans[0].to_text() for ans in [_resolver().resolve(
                    f"{sel}._domainkey.{domain}", "TXT")]]
            except Exception:
                vals = []
        for v in vals:
            if "p=" in v or "v=DKIM1" in v:
                post["dkim_selectors"].append({"selector": sel, "value": v[:200]})
                break

    mta = net.txt(f"_mta-sts.{domain}")
    if mta:
        post["mta_sts"] = mta[0]
    bimi = net.txt(f"default._bimi.{domain}")
    if bimi:
        post["bimi"] = bimi[0][:200]
    return post


def zone_transfer(domain: str) -> dict:
    """Attempt AXFR against every authoritative NS (usually refused — noted for completeness)."""
    r = _resolver()
    try:
        ns = [str(x.target).rstrip(".") for x in r.resolve(domain, "NS")]
    except Exception:
        return {"tried": [], "success": False}
    tried = []
    for ns_host in ns:
        try:
            ip = socket.gethostbyname(ns_host)
        except socket.gaierror:
            tried.append({"ns": ns_host, "error": "no-a"}); continue
        try:
            z = dns.zone.from_xfr(dns.query.xfr(ip, domain, timeout=8, lifetime=12))
            names = sorted(str(n) for n in z.nodes.keys())
            return {"tried": tried + [{"ns": ns_host, "ip": ip}], "success": True,
                    "records": names}
        except Exception as e:
            tried.append({"ns": ns_host, "ip": ip, "refused": type(e).__name__})
    return {"tried": tried, "success": False}


def crtsh_subdomains(domain: str) -> list[str]:
    """Subdomains from certificate transparency (crt.sh)."""
    import re
    host_re = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
    data = get_json("https://crt.sh/", params={"q": f"%.{domain}", "output": "json"},
                    tries=4, timeout=45)
    subs: set[str] = set()
    if isinstance(data, list):
        for row in data:
            for nv in str(row.get("name_value", "")).splitlines():
                nv = nv.strip().lower().lstrip("*.").rstrip(".")
                if "@" in nv or not host_re.match(nv):
                    continue
                if nv == domain or nv.endswith("." + domain):
                    subs.add(nv)
    return sorted(subs)


def hackertarget_subdomains(domain: str) -> list[str]:
    txt = None
    from .http import get_text
    txt = get_text(f"https://api.hackertarget.com/hostsearch/?q={domain}", tries=2)
    subs = set()
    if txt and "error" not in txt.lower():
        for line in txt.splitlines():
            h = line.split(",")[0].strip().lower()
            if h.endswith(domain):
                subs.add(h)
    return sorted(subs)


def brute_subdomains(domain: str, wordlist: list[str], workers: int = 60) -> list[str]:
    """Resolve candidate labels concurrently; keep those that resolve."""
    found: list[str] = []

    def check(label: str):
        host = f"{label}.{domain}"
        try:
            socket.gethostbyname(host)
            return host
        except socket.gaierror:
            return None

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(check, wordlist):
            if res:
                found.append(res)
    return sorted(found)


def enumerate_subdomains(domain: str, wordlist: list[str] | None = None,
                         brute: bool = False) -> dict:
    ct = crtsh_subdomains(domain)
    ht = hackertarget_subdomains(domain)
    union = sorted(set(ct) | set(ht))
    if brute and wordlist:
        union = sorted(set(union) | set(brute_subdomains(domain, wordlist)))
    return {"crtsh": ct, "hackertarget": ht, "combined": union, "count": len(union)}


def resolve_all(hosts: list[str], workers: int = 40) -> dict[str, str]:
    out: dict[str, str] = {}

    def one(h):
        try:
            return h, socket.gethostbyname(h)
        except socket.gaierror:
            return h, None

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for h, ip in ex.map(one, hosts):
            if ip:
                out[h] = ip
    return out
