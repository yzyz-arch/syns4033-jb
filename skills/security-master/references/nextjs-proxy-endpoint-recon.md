# Next.js Proxy Endpoint Recon — Hidden Service Discovery

Session-specific patterns discovered during superjponfire.com audit (Aug 31, 2026). Target: Next.js SPA + Cloudflare + nginx backend.

## Pattern 1: Feature Flag Proxy Leak

**Discovery:** `/api/unleash` endpoint returns feature toggle JSON without authentication.

```bash
# Detect: grep JS bundles for Unleash SDK references
grep -rn 'unleash' /tmp/target/js/ | grep -v 'node_modules'

# Probe the proxy endpoint
curl -s https://target.com/api/unleash
# → {"toggles":[{"name":"release-feature-report-generator","enabled":true,...}]}

# Common feature flag proxy patterns (Unleash, LaunchDarkly, Split.io, Flagsmith)
for ep in /api/unleash /api/features /api/flags /api/toggles /api/ld /api/split; do
  curl -sI "https://target.com$ep" | head -1
done
```

**What to look for:**
- Feature names may reveal hidden admin features, beta endpoints, or disabled functionality
- `enabled: true` + `variant: disabled` = placeholder/configured but not activated
- Admin endpoints (`/api/unleash/admin/*`) usually return 404/403 (protected)
- POST to create toggles → 405 Method Not Allowed on client-only proxy
- `vary: Origin` + `access-control-allow-credentials: true` headers = CORS-enabled but origin NOT reflected (properly configured)

**Exploitation path:** If feature flags control UI elements, toggling a flag server-side could enable hidden admin panels. Requires authenticated admin access to Unleash server.

**Relevant providers:** Unleash (unleash-nextjs-sdk), LaunchDarkly, Split.io, Flagsmith, ConfigCat, GrowthBook.

## Pattern 2: Telemetry/Performance Beacon Analysis

**Discovery:** `/api/network-perf` endpoint accepts `navigator.sendBeacon()` POST with JSON payload — fire-and-forget pattern.

```bash
# Detect: grep JS for sendBeacon + /api/ pattern
grep -rn 'sendBeacon.*api' /tmp/target/js/

# Probe the endpoint
curl -sI -X POST https://target.com/api/network-perf
# → 204 No Content (fire-and-forget — no response body regardless of input)

# Test SSRF via page/hostname fields
curl -s -X POST https://target.com/api/network-perf \
  -H 'Content-Type: application/json' \
  -d '{"type":"test","page":"http://169.254.169.254/latest/meta-data/"}'
# → 204 No Content (payload stored but never processed server-side)

# Test malformed input
curl -s -X POST https://target.com/api/network-perf \
  -H 'Content-Type: application/json' \
  -d '{"type": "test", "page": "'
# → 400 Bad Request: "Invalid JSON" (proper error handling)
```

**Payload fields commonly found:**
- `type` — event category (e.g., `cdn_image_block`, `html_render`)
- `page` — current page pathname
- `hostname` — `location.hostname`
- `trace_id` — from `localStorage.getItem("TRACE_ID")` (UUID generated client-side)
- `online` — `navigator.onLine`
- `timestamp` — `new Date().toISOString()`

**SSRF test vectors:**
| Field | Payload | Expected |
|-------|---------|----------|
| `page` | `http://169.254.169.254/latest/meta-data/` | 204 (no server-side fetch) |
| `page` | `../../../etc/passwd` | 204 (path not processed) |
| `page` | `<script>alert(1)</script>` | 204 (not reflected) |
| `trace_id` | `' OR 1=1--` | 204 (not SQL-processed) |

**Key insight:** 204 No Content on ALL inputs = fire-and-forget pattern. Server stores payload as-is without processing. No SSRF/LFI/XSS vector through this endpoint. Malformed JSON → 400 is the only validation.

## Pattern 3: AMP Landing + SPA Dual-Domain Architecture

**Discovery:** Target uses separate AMP subdomain as public landing page, SPA domain requires auth.

```
Architecture:
├─ https://masuk.festivalsuperjp.com/  → AMP static page (public landing)
│   └─ <link rel="amphtml">, <link rel="alternate" hreflang="...">
└─ https://www.superjponfire.com/      → Next.js SPA (auth-gated)
    └─ /register → 404 (SPA route, not real endpoint)
    └─ /api/* → proxied through Cloudflare → nginx 403
```

**Detection:**
```bash
# Check for AMP alternate links
curl -s https://target.com | grep -i 'amphtml\|alternate.*hreflang'

# The AMP page is public; the SPA requires auth
# Useful: crawl AMP page for JS-free endpoint discovery
curl -s https://amp.target.com | grep -oE 'https?://[^"<> ]+' | sort -u
```

**Recon strategy:**
1. AMP page is static HTML — no JS execution, no API calls, no interactive elements
2. All real functionality lives on the SPA domain behind auth
3. AMP page may contain external links (social media, registration URLs) not visible in SPA source
4. SPA `/register` → 404 means registration is NOT handled by the SPA itself — likely through social channels or separate app domain

**Key takeaway:** When SPA has no forms and AMP page is static, the registration/login flow is external (social media, separate app, or invitation-only). Don't waste time brute-forcing `/register` or `/login` — they're SPA client-side routes, not server endpoints.

## Pattern 4: K8s Internal Service DNS in Client JS

**Discovery:** JS bundles contain `http://unleash.unleash.svc.cluster.local:4242/api` — Kubernetes internal service hostname leaked to public.

```bash
# Extract all internal hostnames from JS
grep -oE '[a-z-]+\.svc\.cluster\.local' *.js | sort -u

# Check DNS resolution
nslookup unleash.unleash.svc.cluster.local
# → Address: 172.21.0.1 (Docker bridge — DNS resolver, NOT the actual service)

# Test direct access
curl --connect-timeout 5 http://unleash.unleash.svc.cluster.local:4242/api
# → HTTP/000 (connection refused — not accessible externally)
```

**Why it resolves to 172.21.0.1:** The host's DNS resolver lives on the Docker bridge interface. The query goes to the resolver, which returns its own address when it can't resolve the name (misconfigured DNS). The actual K8s cluster is not accessible.

**Severity:** LOW — informational leak only. The service is not reachable from the internet. However, it reveals:
- The app runs on Kubernetes
- Unleash is the feature flag service
- The namespace is `unleash`
- The service name is `unleash`

**Remediation:** Remove internal hostnames from client-side JS bundles. Use build-time environment variables or server-side proxy paths instead.

---

*Last updated: Aug 31, 2026 — superjponfire.com audit session*