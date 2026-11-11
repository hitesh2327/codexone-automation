# CTO Architecture Decision Record (ADR) — Sprint 2 (`CDX-002`)

> **Owner:** Reed Richards — CTO (`CDX-002`)  
> **Product:** Mintly (`codexone-automation`)  
> **Date:** 2026-11-11  
> **Status:** LOCKED FOR SPRINT 2 EXECUTION  
> **Applies To:** `dev`, `feat/multiplatform-db-replan`, `feat/dynamic-categories-engine`, `feat/admin-stakeholder-console`, and Q1 2027 Video Editor Architecture  
> **Active Skills:** `conductor-spec-driven-dev`, `db-schema-branching`, `security-audit-trailofbits`, `karpathy-guidelines`

---

## Summary of Locked Architectural Decisions

| ADR ID | Domain | Core Decision | Non-Negotiable Constraint |
|---|---|---|---|
| **ADR-001** | DB Migration Policy | Expand → Backfill → Contract; linearize concurrent branches on `dev` merge | `alembic heads` MUST equal `1` (`tests/test_workflows.py` gate) |
| **ADR-002** | Admin Security Boundary | Zero-trust `/api/admin/*` via `require_admin`; 15-min read-only audited impersonation; DB kill-switches | Zero admin-to-admin/owner impersonation; all writes blocked in read-only mode |
| **ADR-003** | Dynamic Categories & SSRF | DNS-resolved IP pinning against private/metadata CIDRs; 1 MB body cap; single-call 40-candidate Gemini tagger; decoupled visuals | Reject `169.254.169.254`, RFC1918, loopback, link-local at socket connect time |
| **ADR-004** | User-Recorded Video Editor | Presigned direct upload → word-level ASR timestamps → 2-stage AI `EditSpec` JSON → deterministic FFmpeg/Remotion worker | No large binary proxying through FastAPI/Lambda; zero raw shell string interpolation |

---

## ADR-001: Database Migration Policy & Concurrent Branch Linearization

### Context
Currently, `dev` sits at Alembic revision `4a1b2c3d4e5f` (`api/migrations/versions/20261110_4a1b2c3d4e5f_scoped_generation_job_lock.py`, `down_revision = '3f9a1c7e5b2d'`). Three parallel feature branches are active in isolated worktrees:
- `feat/admin-stakeholder-console`
- `feat/multiplatform-db-replan`
- `feat/dynamic-categories-engine`

Simultaneous schema edits on independent branches risk producing multiple Alembic heads, breaking `api/migrate.py` (`command.upgrade(_config(), "head")`) and failing CI (`tests/test_workflows.py` single-head assertion). Furthermore, `api/migrate.py` relies on additive-only schemas so older Lambda/runner containers continue operating cleanly if the database is temporarily ahead of code (`QA-M-02`).

### Decision
1. **Strict Expand → Backfill → Contract Protocol (`db-schema-branching`):**
   - **Expand:** All new tables and columns MUST be additive (`NULL`-able or paired with an explicit `server_default` so existing ORM code in `src/db/models.py` never breaks on `INSERT`).
   - **Backfill:** Historic data backfills run in idempotent batched scripts/jobs *after* the expand migration lands, never inside a blocking DDL transaction.
   - **Contract:** Dropping or tightening legacy columns/constraints is deferred to a dedicated subsequent release *after* 100% of API and GitHub Actions workers stop reading the legacy column.
2. **Non-Blocking PostgreSQL DDL:**
   - New indexes on populated tables (`posts`, `activity_log`, `generation_jobs`, `users`) MUST use `CREATE INDEX CONCURRENTLY` inside `op.get_context().autocommit_block()` on PostgreSQL (with standard fallback for SQLite unit tests).
   - Every migration file MUST implement a working `downgrade()` function that cleanly reverses the `upgrade()`.
3. **Concurrent Branch Linearization Rule on `dev` Merge:**
   - **Merge Order:** `feat/admin-stakeholder-console` → `feat/multiplatform-db-replan` → `feat/dynamic-categories-engine`.
   - Each subsequent PR merging into `dev` MUST rebase onto the latest `dev` and update its new migration's `down_revision` to point to the newly merged `dev` head (never create an `alembic merge` diamond unless emergency hotfix requires it; linear history is mandatory).
   - **Hard CI Merge Gate:** `cd api && alembic heads` MUST return **exactly 1 head**, and `alembic check` (against `src/db/models.py`) MUST show zero unmigrated model drift.

---

## ADR-002: Admin Console Security Boundary, Impersonation & Kill-Switches

### Context
Historically, admin/operator controls were exposed via ad-hoc flags (`all_users=True` in `api/app/routes/posts.py` and unfiltered queries in `api/app/routes/logs.py`) without a strict RBAC boundary between creator tenants and operators. `docs/specs/admin-stakeholder-system-design.md` (`MNT-900`) established the initial design; this ADR locks the Sprint 2 production security invariants.

### Decision
1. **Zero-Trust `/api/admin/*` Perimeter:**
   - Every route under `/api/admin/*` MUST reside in a dedicated router mounted with `dependencies=[Depends(require_admin), Depends(require_csrf)]` (or stricter `require_role(RoleEnum.OWNER)` / `require_specific_roles(...)` per endpoint).
   - **Deny-by-Default:** `client` accounts (`User.role == "client"`) receive deterministic `HTTP 403` on all `/api/admin/*` endpoints. Legacy cross-tenant flags (`all_users=True`) on creator routes (`/api/posts`, `/api/logs`) MUST be removed or strictly restricted to verified operator roles.
   - **Privilege Separation:** An `admin` cannot view plaintext decrypted secrets in `config_values`/`user_config_values` (fingerprints only), cannot rotate `CONFIG_MASTER_KEY`, and cannot elevate any user to `owner` or `admin`.
2. **15-Minute Read-Only Audited Impersonation (Tightened from 60m Draft):**
   - **TTL Lock:** Impersonation tokens (`typ: "impersonation_session"`) minted via `POST /api/admin/users/{id}/impersonate` MUST carry a hard **15-minute (900-second) TTL** (`exp = iat + 900`), superseding the 60-minute draft in `MNT-SPEC-ADMIN-001`. No refresh or silent renewal is permitted.
   - **Separate Signing Key:** Signed with dedicated `IMPERSONATION_SIGNING_KEY` (HMAC-SHA256), never reusing the standard `JWT_SECRET` session key.
   - **Strict Target Guard (No Admin-to-Admin Impersonation):** Target user MUST have `role == "client"`. Attempting to impersonate `admin`, `owner`, `auditor`, or `analyst` MUST fail closed with `HTTP 403 CANNOT_IMPERSONATE_PRIVILEGED_ACCOUNT`.
   - **Read-Only Middleware Enforcement:** All impersonation sessions default to `read_only = True`. Middleware rejects `POST`, `PUT`, `PATCH`, `DELETE` requests (except `POST /api/admin/users/impersonate/end`) with `HTTP 403 IMPERSONATION_READ_ONLY_MODE`. Any break-glass write exception requires `owner` role + password/OTP re-auth + valid ticket ID.
   - **Immutable Audit Trail:** Start, every request count/action, and termination (`manual_exit`, `ttl_expired`, `revoked`) are persisted to `impersonation_audit_logs` with HMAC tamper-chaining, and the UI displays the non-dismissible `SupportImpersonationBanner`.
3. **Global DB-Backed Kill-Switches & Feature Flags:**
   - Store operational switches in PostgreSQL (`feature_flags` / `settings` key `"system_flags"` cached in-memory with <= 10s TTL) rather than env-var redeploys:
     - `kill_generation` (halts `POST /api/generate` and scheduled dispatches)
     - `kill_publishing` (halts `src/publish.py` and `src/publish_youtube.py` calls)
     - `kill_signups` (halts new user registration)
     - `kill_video_uploads` (halts presigned upload URL minting)
   - Only `owner` and `admin` may toggle kill-switches via `POST /api/admin/system/flags`, writing an immutable `ActivityLog` entry with actor, reason, and timestamp.

---

## ADR-003: Dynamic Categories SSRF Defense & Single-Call LLM Tagging

### Context
Supporting arbitrary creator niches requires ingesting user-supplied RSS/Atom/Substack feed URLs (`feat/dynamic-categories-engine`) and decoupling Mintly's visual templates from hardcoded tech categories (`AI`, `SystemDesign`, `DSA`, `Interview`, `OS`, `Dev` in `src/fetch_topics.py` and `src/reel_v2/spec.py`). Fetching arbitrary URLs from user input introduces Server-Side Request Forgery (SSRF) risk against AWS/cloud metadata (`169.254.169.254`) and internal VPC/DB endpoints.

### Decision
1. **SSRF Defense-in-Depth for User RSS/Substack Feeds:**
   - **Scheme & Port Allowlist:** Only `https://` (and `http://` if explicitly opted in for public feeds, normalized to standard ports `80`/`443`). Reject `file://`, `gopher://`, `ftp://`, `data:`, and non-standard ports.
   - **DNS Resolution & IP Pinning (Anti-DNS-Rebinding):**
     - Resolve hostname via `socket.getaddrinfo()` *before* opening any HTTP connection.
     - Reject ANY resolved IPv4/IPv6 address falling in private/reserved networks using Python `ipaddress`: `is_private`, `is_loopback` (`127.0.0.0/8`, `::1`), `is_link_local` (`169.254.0.0/16` including AWS IMDS `169.254.169.254`, `fe80::/10`), `is_multicast`, `is_reserved`, `is_unspecified`, or CGNAT (`100.64.0.0/10`).
     - **Pin the validated IP** into the HTTP transport/socket connection (connecting directly to the vetted IP while passing `Host` header + SNI `server_hostname`) so a second DNS lookup cannot rebind to `127.0.0.1` between validation and fetch (TOCTOU).
   - **Redirects & Payload Bounds:** Disable automatic HTTP redirects (`allow_redirects=False`, or cap at 2 hops with full IP re-validation per hop). Enforce strict **connect timeout = 5s**, **read timeout = 10s**, and **streaming response byte cap = 1 MB (`1,048,576` bytes)**—aborting immediately if `Content-Length` or streamed bytes exceed 1 MB.
   - **Safe XML Parsing:** Parse RSS/Atom exclusively via `defusedxml` (disabling external entities/DTDs to block XXE and Billion Laughs XML bombs).
2. **Single-Call 40-Candidate Gemini Semantic Tagging:**
   - Rather than issuing per-article LLM calls (which blow up latency and token COGS), `src/rank_topics.py` batches up to **40 deduplicated candidate headlines/summaries** from RSS/HN/Reddit into a **single structured `generate_json()` call** (`gemini-flash-latest`) against the user's dynamic category list + `taste` profile.
   - Output schema returns `{candidate_index, matched_category, relevance_score, hook_angle}` in one round-trip, keeping topic discovery under **1 LLM call per run** (~3k–5k input tokens, < 1k output tokens).
3. **Non-Tech Visual Decoupling:**
   - `src/reel_v2/spec.py` currently relies on tech-centric `Icon` literals (`server`, `router`, `balancer`, `database`, `cache`, `queue`, `container`).
   - Introduce a category/niche mode router:
     - `diagram` mode (Tech/SystemDesign/DSA/AI) continues using the persistent animated node-edge `SceneSpec`.
     - `editorial` / `kinetic` mode (Finance, Fitness, Business, Lifestyle, Marketing, Real Estate) renders **typographic kinetic cards, comparison tables, metric callouts, and brand-accented visual layouts** without forcing meaningless server/database icons onto non-tech topics.

---

## ADR-004: User-Recorded Video Editor Technical Stack (Q1 2027 Blueprint)

### Context
Solo creators want to upload their own talking-head or screen-recording MP4/MOV clips (up to 3 minutes) for AI silence removal, dynamic captions, and smart cutaways. Routing 100–150 MB video binaries through FastAPI/AWS Lambda API Gateway hits payload limits (6 MB on Lambda) and stalls API workers.

### Decision
1. **Stage 1 — Presigned Direct Upload (Zero API Binary Proxying):**
   - Client requests an upload ticket (`POST /api/media/upload-url`) validated against tenant tier quotas and `kill_video_uploads` flag.
   - API verifies MIME type (`video/mp4`, `video/quicktime`, `video/webm`), declares strict `max_bytes` (e.g., 150 MB) and TTL (15 min), and returns a **Cloudinary signed upload signature** or **S3 Presigned PUT URL** scoped to `uploads/{user_id}/{upload_id}`.
   - Browser uploads directly to object storage; completion webhook/callback registers the asset metadata (`duration_sec`, `bytes`, `width`, `height`) via `ffprobe` in an async validation job.
2. **Stage 2 — Word-Level ASR Timestamps:**
   - Extract 16kHz mono WAV/Opus audio track via FFmpeg (`-vn -ac 1 -ar 16000`).
   - Run transcription via **Deepgram Nova-3 / Hosted Whisper** (primary, ~$0.0043–$0.0048/min with native word-level `[start, end, word, confidence]` timestamps + Hinglish/code-switching support) with **Gemini Multimodal Audio** as structured fallback.
   - Persist normalized `WordTimestamp[]` JSON alongside detected silence intervals (`> 450ms` gaps).
3. **Stage 3 — 2-Stage AI Prompt Refiner (`EditSpec` JSON):**
   - **Pass 1 (Structural Cut & Hook Refiner — Gemini Flash):** Takes `WordTimestamp[]` + silence intervals + user taste; outputs cut ranges (`keep_segments`), filler/bad-take removals, and suggested hook trim.
   - **Pass 2 (Visual & Caption Stylist — Gemini Flash/Pro):** Enriches `keep_segments` with word-highlight caption chunks (`max 4 words/line`), punch-in zoom keyframes (`1.0x → 1.12x`), optional B-roll/diagram overlay slots, and validates strictly against a Pydantic `EditSpec` schema (clamping all timestamps within `[0, source_duration]`).
4. **Stage 4 — Deterministic Worker Rendering (FFmpeg / Remotion):**
   - Execute `EditSpec` inside an isolated container worker (ECS Fargate Spot / dedicated Docker worker, or GitHub Actions for low volume) using **deterministic FFmpeg filtergraphs** (concat demuxer/filter_complex for cuts + `ass`/libass burned captions) and **Remotion** (for rich animated overlays/intro cards).
   - **Security Invariant:** All paths, text strings, and timestamps from `EditSpec` MUST be escaped/passed as typed arguments or generated `.ass`/JSON config files—never interpolated into `shell=True` commands.
   - Output MP4 (`1080×1920`, H.264/AAC) uploads back to Cloudinary (`src/upload.py`) and enters the existing Telegram/Web approval queue.
