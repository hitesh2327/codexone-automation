---
name: cloudflare-review
description: >-
  Expert code reviewer for Cloudflare architectures, Workers, Pages, D1, KV, R2, Queues,
  Hyperdrive, Vectorize, and edge security configurations. Use when the user asks to
  "review cloudflare code", "review my worker", "check cloudflare config", "audit cloudflare",
  or wants best practices, performance, security, and edge-compatibility reviews.
---

# cloudflare-review

A comprehensive review skill for auditing Cloudflare Workers, Pages, and Edge infrastructure code against production best practices, security, edge runtime limits, and performance patterns.

---

## 1. Scope & Core Review Dimensions

When invoked to review code or architecture, assess across these 6 pillars:

### Pillar 1: Edge Runtime & Compatibility
- **Node.js Compatibility**: Ensure `nodejs_compat` compatibility flag is enabled in `wrangler.toml` or `wrangler.jsonc` if Node APIs (`node:crypto`, `node:buffer`, `node:events`, etc.) are imported.
- **CPU Time & Execution Limits**: Workers have strict CPU time limits (e.g., 50ms on Free, 30s on Standard/Bundled, up to 15m on Unbound/Cron). Flag heavy blocking computation, synchronous regex backtracking, or massive in-memory parsing.
- **Memory Footprint**: Workers are constrained to 128MB (Standard) or up to 512MB (Paid). Flag unbounded caching or loading entire large files into memory instead of streaming.
- **Stateless Lifecycle**: Flag module-level mutable variables assumed to persist across requests (Workers spin up/down and run across hundreds of global PoPs).

### Pillar 2: Storage & State Management
- **Cloudflare D1 (Serverless SQL)**:
  - Check for prepared statements and parameter binding (`stmt.bind(...)`) to prevent SQL injection.
  - Review batching (`db.batch([...])`) to minimize network roundtrips.
  - Check transaction limits (D1 SQLite semantics).
- **Cloudflare KV**:
  - Remember KV is **eventually consistent** (up to 60s global propagation). Flag any usage requiring immediate read-after-write consistency.
  - Verify use of expiration TTLs (`expirationTtl`) for temporary sessions/tokens.
  - Flag single-key hot-spots (KV max write rate ~1 write/sec per key).
- **Cloudflare R2 (Object Storage)**:
  - Check streaming uploads/downloads via `body.pipeTo` / `ReadableStream` instead of buffering `arrayBuffer()` into memory.
  - Verify presigned URL expiry bounds.
  - Confirm custom domain & CORS configuration.
- **Hyperdrive (Postgres connection pooling)**:
  - If querying Postgres / Neon / RDS from Workers, ensure Hyperdrive binding is used to prevent edge-connection starvation and high TLS latency.
- **Durable Objects**:
  - Verify strongly consistent state requirements, concurrency controls, and web-socket hibernation APIs.

### Pillar 3: Security & Secrets
- **Wrangler Secrets vs Vars**:
  - Never store API keys, tokens, or private credentials in `wrangler.toml` under `[vars]`.
  - Ensure sensitive values are declared via `wrangler secret put <KEY>` or `.dev.vars` (for local development).
  - Verify `.dev.vars` is in `.gitignore`.
- **CORS & Headers**:
  - Enforce explicit `Access-Control-Allow-Origin` rather than wildcard `*` when credentials or authorization headers are present.
  - Ensure modern security headers (`Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Strict-Transport-Security`).
- **Input Validation**:
  - Validate all JSON bodies, URL query params, and headers using schemas (e.g., Zod) before handling.

### Pillar 4: Networking & Subrequests
- **Subrequest Limits**:
  - Free tier Workers allow 50 subrequests per request; Paid allows 1,000.
  - Flag unbatched serial `fetch()` loops. Suggest `Promise.all` or caching where applicable.
- **Cloudflare Cache API (`caches.default`)**:
  - Review cache key generation (`new Request(url, ...)`).
  - Check `cf: { cacheTtl, cacheEverything }` configurations.
  - Ensure `Cache-Control` response headers are properly set.

### Pillar 5: Streaming & Async Handling
- **Streaming Responses**:
  - Check `TransformStream` and `ReadableStream` usage for fast Time-to-First-Byte (TTFB).
- **`waitUntil` for Background Tasks**:
  - Ensure background logging, analytics, or metric recording uses `ctx.waitUntil(promise)` so it doesn't block the client response or get killed early.

### Pillar 6: Wrangler Config & Observability
- Check `compatibility_date` (should be modern and pinned, e.g., `2024-09-23` or newer).
- Check `compatibility_flags = ["nodejs_compat"]`.
- Verify tail workers / logging (e.g., Cloudflare Workers Analytics Engine or Tail Workers).

---

## 2. Review Workflow & Output Format

When conducting a Cloudflare code review:

1. **Scan Project Structure**:
   - Locate `wrangler.toml`, `wrangler.json`, `package.json`, worker entry points (`src/index.ts`, `functions/`), and bindings.
2. **Execute Systematic Review**:
   - Check each file against the 6 pillars above.
3. **Generate Actionable Report**:
   Structure the response as:

```markdown
# Cloudflare Architecture & Code Review

## Executive Summary
- **Overall Edge-Readiness**: [Ready | Needs Minor Adjustments | Critical Issues]
- **Key Risks Found**: [Brief summary]

## 🔴 Critical / Blocker Issues
*(Edge runtime crashes, security leaks, subrequest/memory overflows)*
- **[File & Line]**: Issue description
  - **Risk**: Why this will fail on Cloudflare edge
  - **Fix**: Direct code diff or replacement

## 🟡 Performance & Best Practice Improvements
*(Subrequest optimization, Hyperdrive, KV caching, streaming, ctx.waitUntil)*
- **[File & Line]**: Recommendation & code example

## 🟢 Configuration & Security Checklist
- [x] Node.js compatibility configured properly
- [ ] Secrets removed from plaintext configs
- [ ] Subrequest limits respected
- [ ] Prepared queries / parameterized SQL on D1
- [ ] Response streaming / TTFB optimization
```
