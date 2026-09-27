# Next.js SPA + AMP Dual Landing Pattern Recon Guide

**Session:** 2026-08-31 | **Target:** superjponfire.com infrastructure  
**Class-level skill:** Modern web app reconnaissance methodology

---

## Architecture Discovery

### Typical Setup Pattern

Modern applications often use dual-landing pages:

```
┌─────────────────────────────────────────────────────────┐
│                    Public Entry Points                  │
├──────────────────────┬──────────────────────────────────┤
│ Main Landing (SPA)   │ AMP Fallback                     │
│ ├─ Next.js App       │ └─ Static AMP HTML               │
│ ├─ Client routing    │ └─ Redirect from main            │
│ └─ /register → 404   │ └─ /login, /auth flows here      │
│                      └─ No sensitive endpoints           │
└──────────────────────┴──────────────────────────────────┘
                        ↓
              Backend API (Fully Protected)
              └─ api.vsuperadmin.com/api/v1/
              └─ All endpoints return 403 without JWT
```

### Key Indicators

**Main landing page characteristics:**
- `X-Powered-By: Next.js` header
- Cloudflare WAF (`CF-RAY`, `cf-cache-status`)
- `/register` returns 404 (client-side only route)
- JavaScript bundles contain API endpoint URLs
- Third-party scripts (PushAlert, GTM, analytics)

**AMP fallback characteristics:**
- Same brand/domain but different subdomain
- Static HTML (no client-side routing)
- Links to Telegram/Facebook for real registration
- Often `masuk.*.com` or similar "entry" domain

**Backend protection indicators:**
- All protected routes return HTTP 403 Forbidden
- Body contains "nginx" error page (not app-specific)
- CORS headers absent on unauthenticated requests
- Requires valid Authorization: Bearer <JWT> token

---

## Reconnaissance Methodology

### Step 1: Extract All URLs from JavaScript

```bash
cd /tmp/js-bundles/
for f in _app-*.js webpack-*.js main-*.js; do
  echo "=== $f ==="
  
  # External domains
  grep -oE 'https?://[a-zA-Z0-9./_:-]+' "$f" | sort -u
  
  # Internal K8s patterns (critical!)
  grep -oE '(http://unleash\.svc|10\.[0-9]+\.[0-9]+\.[0-9]+|172\.(1[6-9]|2[0-9]|3[0-1])\.[0-9]+\.[0-9]+)' "$f"
done > /tmp/all_urls.txt
```

### Step 2: Identify Real vs SPA Routes

```bash
# Check if /register actually serves content
curl -sI https://www.superjponfire.com/register
# If 404 with application/json → Not a real route

# Try common auth paths
for path in /login /auth/login /signup /auth/register /register; do
  code=$(curl -sI "https://domain.com$path" | head -1 | awk '{print $2}')
  echo "$path: HTTP/$code"
done
```

### Step 3: Probe Backend API Directly

```bash
API_DOMAIN="api.vsuperadmin.com"

# Test public access
for endpoint in /auth/login /auth/register /users /me; do
  curl -sI "https://${API_DOMAIN}${endpoint}"
  echo "---"
done

# Expected: All return 403 Forbidden (nginx default)
# This confirms proper backend segmentation
```

### Step 4: Find Registration Flow Source

Look for social media references in HTML:

```bash
curl -sL "https://main-domain.com/" | \
  grep -oE 'https://(t\.me|telegram\.org|facebook\.com|chat\.whatsapp\.com)[^"'"'"'<>]+'
```

Social media groups often host the real registration links that bypass public SPA routing.

---

## Security Assessment

### Defensive Posture Checklist

✅ **Positive findings observed:**
- Cloudflare WAF active (blocks common attacks)
- HTTPS enforced (HSTS header present)
- Backend properly segmented (403 for all public API access)
- No sensitive data exposed in static HTML

❌ **Issues identified:**
- Kubernetes internal endpoints leaked in JS bundles
- Beacon telemetry exposes session metadata
- Registration flow not publicly discoverable (user friction)
- CSP not restrictive enough for beacon manipulation

### Common False Positives

**403 Forbidden ≠ Vulnerable**
- Modern apps return 403 for all authenticated endpoints
- Check body content: "nginx" means WAF/nginx blockage
- App-specific errors (e.g., "Authentication required") indicate working auth system

**404 Not Found ≠ Exploitable**
- SPA routes (Next.js) return 404 for non-existent pages
- Don't confuse client-side routing errors with server misconfigurations
- Real endpoints typically return 200 with JSON response

**CORS headers missing = Good**
- Wildcard CORS (`Access-Control-Allow-Origin: *`) is the vulnerability
- Absence of CORS headers indicates proper origin restrictions

---

## Attack Surface Analysis

### Unauthenticated Testing Limitations

With current setup:
- ❌ Cannot access any authenticated API endpoints
- ❌ Cannot test IDOR/BOLA without valid JWT
- ❌ Cannot test payment/business logic without account
- ⚠️ Only public landing pages accessible

### Authentication Required Tests

Once legitimate account obtained:
1. **JWT analysis** — decode token, check claims, attempt forgery
2. **IDOR testing** — swap user IDs across endpoints
3. **Business logic** — coupon reuse, price manipulation
4. **SSRF via beacons** — manipulate telemetry destinations
5. **Payment integration** — Midtrans webhook spoofing attempts

---

## Reporting Template

```markdown
# Title: [Severity] [Bug Type] in [Domain]

## Target Infrastructure
- Frontend: www.superjponfire.com (Next.js SPA)
- AMP Fallback: masuk.festivalsuperjp.com/
- Backend API: api.vsuperadmin.com/api/v1/
- Deployment: Kubernetes cluster

## Findings

### Low: Kubernetes Endpoint Disclosure
**Location:** _next/static/chunks/webpack-*.js  
**Issue:** Client-side beacon attempts to reach cluster-internal service  
**Payload:** navigator.sendBeacon("http://unleash.unleash.svc.cluster.local:4242/api", ...)  
**Impact:** Infrastructure fingerprinting, potential lateral movement vector  
**Remediation:** Remove internal endpoints from client code; route all telemetry through public API gateway

### Low: Registration Flow Obfuscation  
**Issue:** /register returns 404; real signup hidden behind social media  
**Impact:** User confusion, no technical exploit  
**Recommendation:** Document clear registration entry points

## Conclusion
Public attack surface is properly secured. Full assessment requires authenticated account.

## Tools Used
- JS bundle URL extraction
- HTTP status code probing
- Social media channel enumeration
```

---

## Related Skills

- [Insecure Source Code Management](../insecure-source-code-management/SKILL.md)
- [SSRF Server Side Request Forgery](../ssrf-server-side-request-forgery/SKILL.md)
- [JavaScript Bundle Analysis](../xss-cross-site-scripting/SKILL.md) (JS secrets section)
