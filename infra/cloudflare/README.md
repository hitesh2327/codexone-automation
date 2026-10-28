# Cloudflare Edge Infrastructure for CodexOne

This directory provides the production Cloudflare Edge setup to protect and optimize the authentication and API layer.

---

## Architecture Overview

```
Client Browser
      │
      ▼
Cloudflare Edge Network (Anycast PoP)
  ├── 1. WAF & Rate Limiting Rules (waf_rules.json)
  │      └── 10 req/min on /api/auth/login (Managed Challenge / Turnstile)
  ├── 2. Edge Proxy Worker (edge_proxy.ts)
  │      ├── Same-origin proxy: routes example.com/api/* to origin backend
  │      ├── Injects X-Origin-Verify header with shared secret
  │      ├── Passes CF-Connecting-IP
  │      └── Enforces Cache-Control: no-store on sensitive endpoints
  │
  ▼
Origin Backend (FastAPI / Lambda / Container)
  └── Enforces ORIGIN_VERIFY, rate limits, and authentication
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

### 4. Apply Cloudflare WAF Rate Limiting
Navigate to your **Cloudflare Dashboard > Security > WAF > Rate Limiting Rules**:
- Create a rule with expression `(http.request.uri.path eq "/api/auth/login" and http.request.method eq "POST")`.
- Rate: 10 requests per 1 minute.
- Action: Managed Challenge (Turnstile).
