# Next.js SPA Security Testing Reference

**When to use**: Target adalah modern web app dengan pattern:
- Next.js 13+ App Router (SSR/CSR hybrid)
- Cloudflare WAF + Turnstile/reCAPTCHA protection
- Server-side rendering with client component hydration
- Redirect/SPA routing behavior (all paths return HTML shell)

## Quick Recognition Signals

| Signal | What It Means | Attack Impact |
|--------|---------------|---------------|
| All non-existent paths return 404 HTML shell | SPA routing intercepts everything | Don't waste time brute-forcing fake endpoints |
| `/login?redirect=/dashboard` redirect loops | Client-side navigation guard | Use Network tab to trace actual fetch requests |
| `CORS: *` header present | Permissive CORS config | Still need valid JWT for Supabase queries → NOT automatically exploitable |
| JS bundles at `/_next/static/chunks/*.js` | Contains API call definitions | Parse for real endpoints (GraphQL operations, REST calls) |
| `/api/favicon`, `/register`, custom favicon handler | Custom API routes exist | Probe these specific paths first |
| External redirects to Telegram/Facebook/WhatsApp | Social engineering funnel | Track all external links (phishing target) |

## Recon Commands — SPA-Safe

```bash
# Status-code-only probing (no body parsing → fast against SPA)
for p in admin graphql api/v1 rest/v1/auth/forgot-password; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -L -A "Mozilla/5.0" "https://target.com/$p")
  [ "$code" != "404" ] && echo "$code $p"
done

# Extract Next.js build artifacts
curl -s https://target.com/login | grep -oE '_next/static/[^\"]*\.js' | sort -u

# Find CDN configuration
curl -s https://target.com/login | grep -oE 'cdn[^\"]*\.(b-cdn\.net|r2\.dev|cloudfront\.net)' | sort -u

# Detect auth mechanism
curl -s https://target.com/login | grep -oE '(supabase|firebase|jwt|Bearer|apikey)[^\"]*' | head -10
```

## Common False Positives — Skip These

1. **200 OK on random paths** → SPA returning index.html, not real endpoint
2. **Redirect chains** → `/login?redirect=/dashboard` often loops back to login
3. **405 Method Not Allowed** → Endpoint exists but method blocked; check if other methods work
4. **CORS warnings** → Origin reflection ≠ exploitation without valid session token
5. **Public asset URLs** → Images/scripts loaded from CDN = not attack surface

## Authenticated Testing Priority

After bypassing registration wall:

### 1. API Discovery (Browser DevTools)
- Open Network tab during login → capture all XHR/fetch requests
- Look for patterns: `/api/*`, `/rest/v1/*`, GraphQL POST
- Extract request bodies (search for field names, ID formats)

### 2. IDOR Chains (Highest ROI)
Test sequential/random ID access across resources:
```bash
# Pattern: resource_id, order_id, invoice_id, user_id
for id in $(seq 1 100); do
  curl -H "Authorization: Bearer $TOKEN" \
    "https://target.com/rest/v1/orders?order_id=eq.$id&select=*" \
    -o /dev/null -w "%{http_code} %s\n"
done
```

### 3. Payment Flow Manipulation
- Intercept checkout POST → modify price/quantity
- Test webhook signature validation
- Replay successful payment callbacks with different order IDs

### 4. Business Logic Abuse
- Race condition: parallel coupon redemption requests
- Negative quantity/price injection
- Role escalation via mass assignment (`{"admin":true}` in user profile update)

## Tool Integration

### JavaScript Analysis (session-specific workflow)
```bash
# Download all JS chunks
curl -s https://target.com/login | grep -oE 'src="[^"]*_next/static/chunks/[^"]*"' | \
  sed 's/src="//;s/"$//' | while read url; do
    curl -s "$url" -o "$(basename $url).js"
  done

# Scan for secrets/patterns
grep -rE 'api[_-]?key|secret|token|password|supabase\.co|graphql' *.js | \
  grep -v "base64(" | grep -v "btoa(" | head -50
```

### Supabase RLS Bypass Check
```bash
curl -X GET "https://project-id.supabase.co/rest/v1/users" \
  -H "apikey: ANON_KEY" \
  -D- -o /dev/null | grep -E "401|403|error"
```

## Pitfalls — From Real Engagements

1. **Cloudflare Turnstile blocks automation** → Use headless browser with proxy rotation, or find API endpoint directly
2. **Next.js SPA redirects trap recon scripts** → Use `-o /dev/null -w "%{http_code}"` only (no response parsing)
3. **Payment systems server-side enforced** → Midtrans callback requires server secret key; don't brute force client configs
4. **All paths return valid HTTP codes** → Check BODY content, not just status line
5. **External CMS/API domains** → Check v1008.p120p0ap1.xyz, cdn subdomains, R2 buckets separately
6. **Rate limiting per IP** → Rotate X-Forwarded-For headers for bulk testing

## Session Artifact Example

**Target observed today**: `superjponfire.com` ecosystem
- Primary domain dead (404), AMP fallback active
- R2 storage bucket for images (`pub-a8cc77b...`)
- CDN misconfiguration (old b-cdn.net prefix still referenced)
- No immediate unauthenticated bugs found
- Needs test account for authenticated testing

---

Last updated: Aug 31, 2026
Class reference: Next.js SPA security testing methodology