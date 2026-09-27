# XERXES Attack Patterns Reference

## Proven Attack: Apache 2.4.6 (CentOS) takedown

This attack was tested against `smkn11malang.sch.id/old/` (Apache/2.4.6 CentOS, PHP 7.3.33) and successfully rendered it unresponsive in ~2m45s.

### Kill Chain

```
Phase 1: Proxy HTTP Flood (0-60s)
  - 300 workers, GET requests, cache busting
  - 2,444 requests sent through proxy pool
  - 50% error rate (free proxy quality issue)
  - Target: exhaust initial Apache connection pool

Phase 2: Direct Threaded Flood (60-105s)
  - 500 threads, raw socket, sequential connections
  - 819 successful requests
  - Error rate climbs to 60% as Apache starts refusing
  - Target: push Apache past MaxRequestWorkers

Phase 3: Occupy Apache Workers (105-165s)
  - Partial GET requests, keep connections open
  - 120 Apache workers locked simultaneously
  - Prevent server from recovering worker pool
  - Target: sustain pressure, prevent recovery

Phase 4: Target DOWN (165s+)
  - 100% HTTPError (503) / Timeout
  - All Apache workers exhausted
  - Server cannot serve any content
```

### Why Apache 2.4.6 is Vulnerable

- **MPM Prefork**: Each connection = 1 process (memory heavy)
- **MaxRequestWorkers**: Default 256 (modifiable but rarely tuned higher on small VPS)
- **KeepAliveTimeout**: Default 5 seconds (short but enough for connection flood)
- **PHP 7.3**: Slow CGI processing, each PHP request holds worker longer
- **No connection pooling**: Apache creates/destroys processes per connection

### Counter-Apache Strategy

1. Open 200-300 persistent connections (keep-alive with partial reads)
2. Mix with rapid GET requests to trigger PHP processing
3. Each PHP request holds Apache worker for 100-500ms
4. 300 concurrent × 5 req/s = 1500 workers needed (impossible for default config)
5. Apache queues → timeouts → errors → collapse

## Proxy Notes

### Supabase API Format

```
POST https://vwmhbpgwhfwuwtattset.supabase.co/functions/v1/fetch-proxies
Authorization: Bearer <key>
Content-Type: application/json
Body: {"limit": 200, "minQuality": 60}
```

Response:
```json
{
  "success": true,
  "count": 200,
  "totalAvailable": 374516,
  "proxies": [
    {
      "id": "http-1",
      "type": "HTTP",
      "ip": "1.2.3.4",
      "port": 8080,
      "country": "Unknown",
      "responseTime": 309,
      "anonymity": "Elite",
      "status": "Online",
      "protocol": "HTTP/HTTPS",
      "qualityScore": 90
    }
  ]
}
```

### Proxy Quality Tips

| Quality | Type | Failure Rate | Best For |
|---------|------|-------------|----------|
| 90-100 | Elite HTTP/SOCKS5 | ~10% | Primary attack pool |
| 70-89 | Anonymous | ~30% | Volume filler |
| 50-69 | Transparent | ~60% | Only for large pools |
| < 50 | Unknown | ~90% | Skip entirely |

## Bandwidth Estimation

### Direct Attack (No Proxy)
- Single machine: ~50-200 Mbps depending on connection
- Thread limit: Windows ~16k ephemeral ports
- Socket reuse: Keep-alive increases throughput 10x

### Proxy Attack
- Free proxies: 30-50 effective req/s per 100 proxies
- Paid proxies: 200-500 req/s per 100 proxies
- Bottleneck: Proxy response time (most free proxies are slow)

### Amplification Attack (Admin required)
- DNS ANY: ~50x amplification (64 byte → ~3000 byte)
- NTP Monlist: ~200x amplification
- 10 Mbps sender → 500 Mbps - 2 Gbps target impact
