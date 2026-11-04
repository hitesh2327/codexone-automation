# Cloudflare Edge Infrastructure for CodexOne

This directory provides the production Cloudflare Edge setup to protect and optimize the authentication, API, and subscription/payment layer.

---

## Architecture Overview

```
Client Browser / Razorpay Webhooks
      │
      ▼
Cloudflare Edge Network (Anycast PoP)
  ├── 1. WAF & Rate Limiting Rules (waf_rules.json)
  │      ├── Exempt /api/subscription/razorpay/webhook from bot challenges
  │      ├── 10 req/min on /api/auth/login (Managed Challenge)
  │      ├── 8 req/min on /api/auth/password/forgot (Managed Challenge)
  │      ├── 6 req/min on /api/auth/password/reset (Managed Challenge)
  │      ├── 5 req/min on /api/auth/signup (Managed Challenge)
  │      ├── 10 req/min on /api/generate (Managed Challenge)
  │      ├── 10 req/min on /api/integrations (Managed Challenge)
  │      ├── 5 req/min on /api/subscription/checkout (Anti-carding)
  │      └── 12 req/min on /api/subscription/quote (Quote anti-spam)
  ├── 2. Cache Rules (cache_rules.json)
  │      ├── Bypass edge and browser cache on /api/* and __Host-cx_session
  │      ├── Bypass edge cache on SPA root/document routes (guarantees fresh asset hashes)
  │      └── 1-year immutable edge and browser cache on /assets/*
  ├── 3. Edge Proxy Worker (edge_proxy.ts)
  │      ├── Same-origin proxy: routes example.com/api/* to origin backend
  │      ├── Injects X-Origin-Verify header with shared secret (fails closed if unset)
  │      ├── Sanitizes client headers (strips client X-Origin-Verify, True-Client-IP)
  │      ├── Rewrites Host header to match upstream origin target host
  │      ├── Passes CF-Connecting-IP
  │      ├── Streams unbuffered request bodies for HMAC webhook verification
  │      ├── Enforces strict multi-CDN zero-store headers (CDN-Cache-Control: no-store)
  │      ├── Graceful JSON 502/504 fallback with full security headers (nosniff, DENY)
  │      └── Telemetry logging in ctx.waitUntil for payment failures (>= 400)
  │
  ▼
Origin Backend (FastAPI / Lambda / Container)
  └── Enforces ORIGIN_VERIFY, client IP resolution, and authentication
```

---

## Deployment Steps

### 1. Configure Cloudflare Secrets
Install wrangler and authenticate:
```bash
npm install -g wrangler
wrangler login
```

Set the shared origin verification secret:
```bash
cd infra/cloudflare
wrangler secret put ORIGIN_VERIFY
```
*Enter the exact same secret token configured in your backend `.env` / SSM Parameter Store (`ORIGIN_VERIFY`).*

### 2. Configure Origin URL
In `wrangler.toml`:
```toml
[vars]
ORIGIN_URL = "https://your-backend-origin.example.com"
```

### 3. Deploy the Edge Proxy Worker
```bash
wrangler deploy
```

### 4. Apply Cloudflare WAF Security & Rate Limiting Rules
Navigate to your **Cloudflare Dashboard > Security > WAF**:
- **Custom Rules**:
  - Add exemption rule: `(http.request.uri.path eq "/api/subscription/razorpay/webhook" and http.request.method eq "POST")` -> Action: `Skip` (all remaining rulesets).
- **Rate Limiting Rules**:
  - `/api/auth/login`: 10 req / 1 min (Managed Challenge).
  - `/api/auth/password/forgot`: 8 req / 1 min (Managed Challenge).
  - `/api/auth/password/reset`: 6 req / 1 min (Managed Challenge).
  - `/api/auth/signup`: 5 req / 1 min (Managed Challenge).
  - `/api/generate`: 10 req / 1 min (Managed Challenge).
  - `/api/integrations`: 10 req / 1 min (Managed Challenge, 5 min block).
  - `/api/subscription/checkout`: 5 req / 1 min (Managed Challenge, 5 min block).
  - `/api/subscription/quote`: 12 req / 1 min (Managed Challenge, 3 min block).
*(Reference: `waf_rules.json`)*

### 5. Apply Cloudflare Cache Rules
Navigate to your **Cloudflare Dashboard > Caching > Cache Rules**:
- **Rule 1 (Zero-Store)**:
  - Expression: `(http.request.uri.path starts_with "/api/") or (http.cookie contains "__Host-cx_session")`
  - Action: **Bypass cache** (Eligible for cache: False).
- **Rule 2 (SPA Document Freshness)**:
  - Expression: `(http.request.uri.path eq "/") or (not http.request.uri.path contains "." and not http.request.uri.path starts_with "/api/")`
  - Action: **Bypass cache** (Eligible for cache: False).
- **Rule 3 (Immutable Hashed Assets)**:
  - Expression: `(http.request.uri.path starts_with "/assets/")`
  - Action: **Cache eligible**, Edge TTL: 1 year (31,536,000s), Browser TTL: 1 year (31,536,000s).
*(Reference: `cache_rules.json`)*
