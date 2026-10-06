# Spec: Dashboard "Config" section (setup wizard, verified settings, docs, readiness)

Status: Draft for owner review | Author: BA (Bruce Banner) | Date: 2026-10-05
Related: Generate (spec in `docs/specs/generate-section.md`), Posts (built), Logs (built), Dashboard (`docs/specs/dashboard-section.md`)
Sidebar: item `/config` is `ready: false` ("soon") in `web/src/components/app-shell.tsx`.

---

## 0. How to read this document

### 0.1 Evidence legend (requirement 5: no assumptions)

Every factual statement carries one tag:

| Tag | Meaning |
|---|---|
| **[R: file:line]** | Verified by reading this repo. Re-checkable by anyone. |
| **[D: S#]** | Stated by an official provider document; `S#` is the numbered URL in section 14. |
| **[2nd: S#]** | Only a third-party source was found. Treat as unverified until promoted. |
| **[U#]** | UNVERIFIED. Not stated as fact. Listed in section 13 with the exact test that settles it. |
| **[EST]** | My estimate/design number, not a fact. Must be measured (S-UX spike). |

### 0.2 Honest limit of the research method

I could only run web *searches* (no page fetch). Each `[D]` claim was confirmed against the official page's search excerpt/summary, not by reading the full page. Before build starts, spike **S0** re-reads each `[D]` page top to bottom and records the date. Where an excerpt was ambiguous I downgraded the claim to `[U#]` rather than guess. The two most important downgrades are the Gemini "auth keys vs standard keys" change (U1) and whether the Instagram App Dashboard token is long-lived (U2).

### 0.3 Established decisions this spec respects (and where it proposes a change)

| Existing decision | Source | This spec |
|---|---|---|
| Nothing publishes without Telegram/dashboard approval | CLAUDE.md, `src/publish.py` | Respected. No verification step ever publishes (section 6, "must NOT"). |
| GitHub Actions is the only publisher; Lambda never publishes (`PUBLISH_VIA=dispatch`) | `infra/README.md`, `infra/template.yaml:79` | Respected. |
| Generation/render/publish run in GitHub Actions; Lambda cannot run Chromium/FFmpeg | `generate-section.md` 2.1 | Respected. The pipeline test runs in Actions. |
| YouTube scope is `youtube.upload` only | `src/publish_youtube.py:39`, README | **PROPOSAL (needs owner OK, OQ6):** add `youtube.readonly` so the channel can be verified. Not assumed. |
| `get_yt_token.py` is local-only, Desktop OAuth client | `get_yt_token.py` | **PROPOSAL:** replace with an in-dashboard "Connect YouTube" web flow for customers; keep the script as fallback. |
| Secrets live in `.env` (local), GitHub Secrets (CI), SSM (Lambda) | README, `infra/put_secrets.py` | **PROPOSAL:** one encrypted store in Postgres (section 3). Existing places keep working during migration. |
| Slot times in `brand/config.yaml` are mirrored by workflow crons | `daily-generate.yml:18,110` | Not editable from the dashboard until decoupled (R-24). |

### 0.4 Scope and assumptions I am NOT making silently

- **Single-tenant, deploy-per-customer** (one brand, one Telegram chat, one IG account per deployment) matches the code [R: `brand/config.yaml`, `src/approve_bot.py:50`]. If you intend a multi-tenant SaaS, section 3 changes materially (OQ1).
- Deploying the stack itself (AWS account, Neon DB, GitHub repo, CloudFront) happens **before** Config exists. It will dominate first-time setup time more than anything in this spec; section 4.4 treats it as "Step 0" and recommends it be one command, but does not specify it.

---

## 1. Summary and key decisions

1. **One source of truth:** an AES-256-GCM encrypted `config_values` table in the existing Postgres, read by both the API Lambda and the GitHub runner. Only two bootstrap values stay outside it per environment: `DATABASE_URL` and `CONFIG_MASTER_KEY`. (section 3)
2. **Verify-before-save:** a value is verified against the real provider before it replaces a working one. A typo can never break a working configuration. (UX-6)
3. **Secrets are write-only** from the browser. The API never returns a secret, only status, evidence (e.g. `@username`) and expiry. (SEC-1)
4. **Three verification depths:** format (instant, local) -> live check (seconds, Lambda) -> **pipeline test** (minutes, GitHub runner: render a real reel, upload it, ask Instagram to process it, never publish). (section 6)
5. **Readiness is a precise predicate** over verified checks plus a "config version" so that editing any required value makes readiness stale until re-verified. (section 7.5)
6. **Paste vs Connect:** Phase 1 uses paste + deep links + step cards. Phase 3 adds OAuth "Connect" for YouTube and Instagram, which removes the two worst copy-paste steps.
7. **Honest time budget:** under 15 minutes is realistic for "Generate-ready + one platform" if the Meta/Google console steps go well; all five integrations is more like 25-35 minutes [EST]. Gate by tiers so users get value after tier 1. (section 4.3)
8. **Real defects found while inventorying** that block selling this: hard-coded owner repo default, hard-coded owner IDs in a workflow, possible token leakage into logs/Telegram, OTP codes logged by the console mail driver, a token-refresh job that writes only GitHub. (section 2.3)

---

## 2. Ground truth inventory (task A)

### 2.1 Every configurable setting

Legend: **Lam** = API Lambda, **Run** = GitHub Actions runner, **Loc** = local dev. Required: **Req**, **Opt**, **Cond** (conditional). "Editable in UI" is my recommendation (section 3.6): **UI** = editable and verified in Config; **BOOT** = bootstrap, never in UI; **INFRA** = set by deploy.

Names are taken from `.env` key names only (no values read), `get_env(...)` calls, workflow YAML and `infra/`.

#### Pipeline integrations

| Setting | What it does | Read at | Who | Req | Default | Format rule | How a user obtains it | UI |
|---|---|---|---|---|---|---|---|---|
| `GEMINI_API_KEY` | Gemini client for ranking, writing, review | `src/llm.py:28` | Run | Req | none | Non-empty, no whitespace. Do **not** hard-code a prefix check (U1). `scripts/check_secrets.py` only lists models [R: check_secrets.py:50-57] | Google AI Studio API keys page [D: S4] | UI |
| `GEMINI_MODEL` | Primary model | `src/llm.py:33` | Run | Opt | `gemini-flash-latest` [R: llm.py:17] | Model id string; verified by `countTokens` (6.1) | Models page | UI (Advanced) |
| `GEMINI_FALLBACK_MODELS` | Comma list tried after primary | `src/llm.py:34` | Run | Opt | long chain [R: llm.py:20-21] | Comma-separated ids; unknown ids are skipped on 404 [R: llm.py:67-69] | - | UI (Advanced) |
| `CLOUDINARY_URL` (aliases `COUDNARY_API_ENV_VAR`, `CLOUDINARY_API_ENV_VAR`) | Public HTTPS URLs for media | `src/upload.py:29`, alias map `src/config.py:25-27` | Run | Req | none | `cloudinary://<key>:<secret>@<cloud_name>`; tolerates a pasted `CLOUDINARY_URL=` prefix [R: upload.py:30-33] | Cloudinary Console > Settings > API Keys shows the ready-made "API environment variable" [D: S21] | UI |
| `TG_BOT_TOKEN` | Telegram previews, button polling, notifications | `src/approve_bot.py:54` | Run; Lam only if `TELEGRAM_SYNC=true` | Req | none | `<digits>:<secret>`. Exact length not documented, so warn-only (U9). Live: `getMe` | @BotFather `/newbot` [2nd: S20b] | UI |
| `TG_CHAT_ID` | Only chat whose presses count | `src/approve_bot.py:50` (`int()`) | Run, Lam | Req | none | Integer, may be negative for groups [R: check_secrets.py:33-34] | Send `/start` to the bot; wizard detects it (6.4) | UI |
| `TG_BOT_NAME` | (none) | **never read by code** | - | - | - | - | - | Remove from `.env` template |
| `IG_USER_ID` | Instagram professional account id | `src/publish.py:106` | Run | Req | resolved from token via `/me` if not numeric [R: publish.py:99-115] | Digits only (`check_secrets.py:73`). UI should *auto-fill* it from `/me` | Returned by `/me` once the token is valid | UI (auto-filled) |
| `IG_ACCESS_TOKEN` | Instagram User long-lived token | `src/publish.py:51`, `src/refresh_token.py:31` | Run | Req | none | Non-empty, no whitespace/quotes/`NAME=` prefix. No length rule documented (U3) | Meta App Dashboard "Generate token" [D: S9]; or Business Login flow [D: S10] | UI |
| `IG_APP_ID`, `IG_APP_SECRET` | App credentials for Business Login token exchange | **never read by code today** (present in `.env` only) | would be Lam | Cond (only for "Connect Instagram", Phase 3) | none | numeric id / hex secret [U3] | Meta App Dashboard > App settings > Basic | UI |
| `IG_API_VERSION` | Graph version in URL | `src/publish.py:46` | Run | Opt | `v21.0` | `v\d+\.\d` | - | UI (Advanced). **Note:** v21.0 is dated for deprecation 2027-01-21 per a secondary source (U5, R-21) |
| `YT_CLIENT_ID` | Google OAuth client id (YouTube) | `src/publish_youtube.py:66` | Run | Cond (YouTube on) | none | ends `.apps.googleusercontent.com` [R: check_secrets.py:113] | Google Cloud Console > Credentials | UI |
| `YT_CLIENT_SECRET` | Client secret | `:66` | Run | Cond | none | starts `GOCSPX-` [R: check_secrets.py:114] (heuristic, warn-only) | same | UI |
| `YT_REFRESH_TOKEN` | Offline grant for uploads | `:65` | Run | Cond | none | starts `1//` [R: check_secrets.py:115] (heuristic, warn-only) | `get_yt_token.py` today; "Connect YouTube" later | UI (via Connect) |
| `YT_PRIVACY` | Privacy of uploaded Shorts | `src/publish_youtube.py:58` | Run (GitHub repo *variable*, not secret [R: poll-approvals.yml:37]) | Opt | `private` | `private`/`unlisted`/`public` [R: publish_youtube.py:59-60] | - | UI |
| `GITHUB_TOKEN` | Higher rate limit for GitHub trending fetch | `src/fetch_topics.py:222` | Run | Opt | provided automatically by Actions [R: daily-generate.yml:97] | - | automatic | not user config |

#### Automation / orchestration

| Setting | What it does | Read at | Who | Req | Default | Format | Obtain | UI |
|---|---|---|---|---|---|---|---|---|
| `GITHUB_DISPATCH_TOKEN` | Lambda starts workflows and reads run status | `src/actions.py:237`, `src/github_actions.py:44,52` | Lam | Req for dashboard Generate/Publish-now/Retry/Regenerate; scheduled runs work without it [R: actions.py:238-241, generate-section E1] | none | fine-grained PAT, this repo only, **Actions: read + write** [R: github_actions.py:8; D: S22] | GitHub > Settings > Developer settings > Fine-grained tokens [D: S22] | UI |
| `GITHUB_REPOSITORY` | `owner/name` of the automation repo | `src/actions.py:238`, `src/github_actions.py:48` | Lam (Run gets it automatically) | **Req for customers** | **hard-coded to `hitesh2327/codexone-automation`** [R: actions.py:238, github_actions.py:48, check_secrets.py:91] | `^[\w.-]+/[\w.-]+$` | The user's own repo | UI. Default must be removed (R-20) |
| `GH_PAT` | Lets the weekly job rewrite the `IG_ACCESS_TOKEN` GitHub secret | `src/refresh_token.py:46`, `check_secrets.py:93` | Run (`refresh-token.yml`) | Req today | none | fine-grained PAT, **Secrets: read and write** [R: check_secrets.py:96-97] | GitHub | **Eliminated** by the new design (3.5): the refresh job writes to the config store |
| `PUBLISH_VIA` | `dispatch` = API only kicks Actions | `src/actions.py:176` | Lam (template sets `dispatch`) [R: template.yaml:79] | Opt | `inline` in code | `inline`/`dispatch` | - | INFRA |
| `PUBLISH_ENABLED` | Kill switch for publish-now/retry | `src/actions.py:37` | Lam | Opt | `true` in code; **template default `false`** [R: template.yaml:17-20] | bool | - | UI (Readiness controls it, 7.5) |
| `TELEGRAM_SYNC` | Mirror dashboard decisions to Telegram | `src/approve_bot.py:46` | Lam | Opt | `true` in code; **template default `false`** [R: template.yaml:21-24] | bool | - | UI |
| `GENERATE_DAILY_CAP` | Dashboard generations per IST day | `api/app/routes/generate.py:49` | Lam | Opt | `4` [R: generate.py:36] | int >= 0 | - | UI |
| cron-job.org account + job definitions | On-time scheduling (primary trigger; GitHub's own `schedule:` is "often hours late") | external | external | Opt (strongly recommended) | none | 3 POST jobs [R: README "On-time scheduling"] | cron-job.org + a **second** GitHub PAT (Actions read/write) | Guide only (cannot be verified from our side, U12) |
| `TZ` | Runner timezone | workflows | Run | INFRA | `Asia/Kolkata` | - | - | INFRA |

#### Database, auth, mail, infra

| Setting | What it does | Read at | Who | Req | Default | Format | Obtain | UI |
|---|---|---|---|---|---|---|---|---|
| `DATABASE_URL` | Postgres (Neon). Presence switches the pipeline from JSON files to DB | `src/db/__init__.py:22`, `scripts/has_work.py:37` | Lam, Run | Req | none (file mode) | `postgres(ql)://...`; Lambda uses the **direct** URL, not pooled [R: put_secrets.py:22-23] | Neon console > connection string | **BOOT** |
| `DATABASE_URL_POOLED` | (none) | **never read by code** | - | - | - | - | - | Remove from `.env` template |
| `JWT_SECRET` | Session signing, **>= 32 chars** | `api/app/settings.py:41-43` | Lam | Req | none | length >= 32 | generated | **BOOT** |
| `SESSION_SECRET` | OAuth state cookie | `settings.py:47` | Lam | Opt | `JWT_SECRET[::-1]` (weak derivation) | - | generated | **BOOT** |
| `SESSION_HOURS` | Session length | `settings.py:48` | Lam | Opt | 12 | int | - | UI (Advanced) |
| `COOKIE_SECURE` | Secure cookie | `settings.py:49` | Lam | Opt | true | bool | - | INFRA |
| `PUBLIC_URL` | Browser-facing origin; builds OAuth redirect URIs | `settings.py:50` | Lam | Req in prod | `http://localhost:5173` | URL, no trailing slash | set by `deploy.sh` [R: deploy.sh:42] | INFRA (read-only in UI) |
| `WEB_ORIGIN` | CORS if split origins | `settings.py:51` | Lam | Opt | none | URL | - | INFRA |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Seeds/updates the admin account on every API start [R: README] | `settings.py:52-53` | Lam | Req (or Google) | none | - | chosen at install | **BOOT** (password change through Profile) |
| `ADMIN_PASSWORD_FORCE` | Re-seed override | `api/app/main.py:34` | Lam | Opt | none | - | - | BOOT |
| `GOOGLE_WEB_CLIENT_ID`, `GOOGLE_WEB_CLIENT_SECRET` | "Sign in with Google" | `settings.py:54-55` | Lam | Opt | none | same shapes as YT client | Google Cloud Console (Web application client) | UI (guarded, 7.6) |
| `ALLOWED_GOOGLE_EMAILS` | Comma list of permitted emails | `settings.py:44,56` | Lam | Cond (with Google sign-in) | empty -> Google disabled [R: settings.py:35] | emails | - | UI |
| `API_DEBUG` | Debug | `settings.py:57` | Lam | Opt | false | bool | - | INFRA |
| `MAIL_DRIVER` | `smtp` or `console` | `api/app/mailer.py:128` | Lam | Opt | `smtp` if `SMTP_HOST` set else `console` | enum | - | UI |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURE`, `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM`, `MAIL_FROM_NAME` | Outgoing email (password reset, set password, verify email) | `mailer.py:127-144` | Lam | Cond (for OTP flows) | port 587; secure = ssl on 465 else starttls; from-name `Content admin` [R: mailer.py:135-144] | `SMTP_SECURE` in `ssl/starttls/none`; `MAIL_FROM` or `SMTP_USER` required [R: mailer.py:137-141] | Provider (e.g. Gmail app password) | UI |
| `MAIL_OUTBOX_DIR` | Where the console driver drops mails | `mailer.py:60` | Lam | Opt | `data/outbox` | path | - | INFRA |
| `SSM_PREFIX` | Lambda cold-start secret load | `api/lambda_handler.py:18` | Lam | INFRA | `/codexone/` | - | `deploy.sh` | INFRA |
| `ORIGIN_VERIFY` | CloudFront-to-Lambda shared secret | `lambda_handler.py:40` | Lam | INFRA | generated | - | `deploy.sh` | INFRA |
| `AWS_PROFILE`, `AWS_REGION` | Local deploy helper | `infra/put_secrets.py:19-20` | Loc | INFRA | `shhh`, `us-east-1` (owner's profile) | - | - | n/a |

#### Brand and schedule (`brand/config.yaml`, stored in `settings` row `brand` when migrated [R: config.py:48-61])

| Key | Meaning | Notes for Config |
|---|---|---|
| `handle`, `cta`, `hashtags`, `language` | Identity and text | Safe to edit; first-run wizard "Your brand" step |
| `colors`, `fonts` | Slide rendering | Safe; preview |
| `voices`, `pronunciations` | edge-tts voices rotation, spoken forms | Validate voice ids against edge-tts list (pipeline test P4) |
| `topics_weight` | Category weights | Safe to edit |
| `posts_per_day`, `post_times_ist` | Slots | **Not safe to edit in UI today:** the generate workflow hard-codes `"30 2 * * *"` -> `10:00` and `"30 12 * * *"` -> `19:00` [R: daily-generate.yml:18-19,110-114] and cron-job.org has its own jobs. See R-24 |
| `reel.size/duration_sec/structure`, `carousel.size/slides`, `reel.music` | Output specs | Read-only in MVP |

### 2.2 Which environment needs what (the three-places problem, concretely)

| Group | Lambda (SSM today) | Runner (GitHub Secrets today) |
|---|---|---|
| DB + auth | `DATABASE_URL`, `JWT_SECRET`, `SESSION_SECRET`, `ADMIN_*`, `GOOGLE_*`, `ALLOWED_GOOGLE_EMAILS` [R: put_secrets.py:24-26] | `DATABASE_URL` only |
| Telegram | `TG_BOT_TOKEN`, `TG_CHAT_ID` (optional) | both, always |
| Dispatch | `GITHUB_DISPATCH_TOKEN` (added by hand, not in `.env` [R: put_secrets.py:6-7]) | `GH_PAT` (for refresh) |
| Generation | - | `GEMINI_API_KEY`, `CLOUDINARY_URL` |
| Publishing | - | `IG_*`, `YT_*` |
| Mail | `SMTP_*` (not even in `put_secrets.py`'s lists) | - |

Drift is already present and checked by hand: `check-secrets.yml` hard-codes SHA-256 fingerprints of the owner's working local values to detect copy mistakes [R: check-secrets.yml:65,72,79]. That is the symptom this spec removes.

### 2.3 Defects and hazards found during the inventory (each has a risk-register entry)

| # | Finding | Evidence | Risk ID |
|---|---|---|---|
| F1 | Default repo is the owner's repo in 3 places | `actions.py:238`, `github_actions.py:48`, `check_secrets.py:91` | R-20 |
| F2 | Owner's bot id, IG id and secret fingerprints hard-coded in a workflow | `check-secrets.yml:19-20,65,72,79` | R-20 |
| F3 | Exceptions are logged raw; `requests` exception text can include the request URL and the IG token is sent as a **query parameter** on GET | `publish.py:51-58` (`access_token` in `params`, `f"network error: {e}"`), `upload.py:47`, `main.py:336` forwards `type(e).__name__: e` to Telegram. `src/logger.py` has no redaction (grep: none) | R-05 |
| F4 | The `console` mail driver prints OTP codes to the log and to `data/outbox`; it is the default when `SMTP_HOST` is unset | `mailer.py:16,51-67,128` | R-06 |
| F5 | IG token refresh writes only the GitHub secret (`gh secret set`) or local `.env`; any other copy goes stale | `refresh_token.py:42-56` | R-08 |
| F6 | `settings()` is `lru_cache`d and `llm._client` is a module global, so a changed value is not seen until restart | `settings.py:39`, `llm.py:22-29` | R-12 |
| F7 | `.env` typo key `COUDNARY_API_ENV_VAR` is accepted by an alias | `config.py:26` | R-18 |
| F8 | Template defaults `PUBLISH_ENABLED=false`, `TELEGRAM_SYNC=false`, while code defaults are `true` | `template.yaml:17-24` vs `actions.py:37`, `approve_bot.py:46` | R-17 |
| F9 | Lambda cannot see GitHub Secrets and GitHub cannot see SSM, so "is the runner's key valid?" cannot be answered by the Lambda today | architecture | section 3 |
| F10 | An existing verifier already exists and is the right seed: `scripts/check_secrets.py` (telegram, gemini, cloudinary, instagram, youtube, gh_pat, database) | `check_secrets.py:162-166` | reuse (6.0) |

---

## 3. The architectural problem: one source of truth (task B)

### 3.1 Requirement

A non-technical user pastes a value on a web page and every consumer (API Lambda, GitHub runner, local dev) uses it from then on, with no second place to edit.

### 3.2 Options analysed

| | **A. Encrypted `config_values` table in Postgres** | **B. Dashboard writes GitHub Secrets + SSM via their APIs** | **C. SSM Parameter Store as the single store; runner reads it through GitHub OIDC** | **D. Hybrid: A for values, KMS as the key-encryption key** |
|---|---|---|---|---|
| Single copy of each value | Yes | **No (two copies, no atomic write)** | Yes | Yes |
| Bootstrap left in each env | Lam: `DATABASE_URL` + `CONFIG_MASTER_KEY` (already via SSM). Run: same two as GitHub secrets | Lam: SSM write creds. Run: GitHub PAT stored in SSM | Lam: nothing new. Run: an IAM role ARN (not secret) | Lam: `DATABASE_URL`. Run: `DATABASE_URL` + AWS role ARN |
| Can the dashboard read back / verify what the runner uses? | Yes (same row) | **No: GitHub secrets are write-only** [D: S22 secrets REST]; drift is undetectable except by running a job | Yes | Yes |
| Write path | DB transaction (atomic with status, audit row, version) | PUT GitHub secret (libsodium sealed-box encryption required [D: S22]) **and** `ssm:PutParameter`; partial failure = split brain | `ssm:PutParameter` + KMS | DB transaction + KMS call |
| Extra permission the dashboard Lambda needs | **None beyond today** (`ssm:GetParametersByPath` to load the master key [R: template.yaml:56-61]) | `ssm:PutParameter` (+KMS), **and** a GitHub PAT with **Secrets: write** for the repo, which can overwrite every CI secret (blast radius), plus Actions write | `ssm:PutParameter`, `ssm:GetParameter*`, `kms:Encrypt/Decrypt` | `kms:GenerateDataKey/Decrypt` on one key |
| Runner access path | existing DB connection | n/a (uses GitHub secrets) | GitHub OIDC -> `sts:AssumeRoleWithWebIdentity` -> role; needs `id-token: write` and an IAM OIDC provider + trust policy [D: S22 OIDC] | same as C for KMS |
| Audit of who changed what | App-level into `activity_log` (existing Logs page) [R: activity.py] | GitHub audit + CloudTrail, not in our Logs | CloudTrail + app log | App log + CloudTrail |
| Cost | ~$0 | ~$0 (standard SSM params free, <=4 KB [D: S25]) | ~$0 | KMS CMK $1/month + 20k free requests/month [D: S25] |
| Works with SQLite tests / local dev | Yes (tests already use SQLite [R: README]) | No | Needs AWS locally | Needs AWS locally |
| Customers not on AWS | Works (DB is the only dependency, and it is already required) | Needs both GitHub+AWS creds | AWS only | AWS only |
| Customer setup steps added | Install script generates and places the master key (0 user steps) | PAT with Secrets write + IAM | OIDC provider + role (can be CloudFormation) | same as C |
| Rotation | App-managed KEK rotation (rewrap one DEK) | Per-secret re-push to two stores | KMS/SSM versions | KMS-managed rotation |
| Biggest weakness | Master key held in two places (SSM + GH secret); a DB dump alone is useless, but Lambda or runner compromise exposes everything (true for every option) | Drift, blast radius, no read-back | AWS lock-in; OIDC trust-policy mistakes are a classic privilege hole | Highest setup complexity |
| Effort [EST] | 6-8 dev-days incl. migration | 5-7 dev-days, more support burden | 6-9 dev-days | 8-11 dev-days |

### 3.3 Recommendation

**Option A with an abstracted key provider (so D is a later swap, not a rewrite).**

Why: it is the only option that (1) gives one atomic write containing value + verification status + audit entry, (2) lets the dashboard verify exactly what the runner will use, (3) needs no new IAM permission or customer-side step, (4) works in tests and local dev, and (5) keeps the Logs page the audit trail. Option B is rejected because GitHub secrets cannot be read back [D: S22] so "verified" can never mean "what CI will use", and its PAT is a high-value credential. Option C is the best crypto custody and is the recommended **Phase 5 upgrade** if a customer is AWS-native or demands CloudTrail-grade audit; it is not the default because it adds an OIDC trust policy that non-AWS-fluent customers will misconfigure.

**Stays as bootstrap config (never in the UI, never in the store):**

| Env | Bootstrap values |
|---|---|
| API Lambda | `DATABASE_URL`, `CONFIG_MASTER_KEY`, `JWT_SECRET`, `SESSION_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ORIGIN_VERIFY`, `PUBLIC_URL`, `COOKIE_SECURE`, `SSM_PREFIX`, `PUBLISH_VIA` (all already SSM/template [R]) |
| GitHub runner | `DATABASE_URL`, `CONFIG_MASTER_KEY` (two GitHub secrets; set once by the installer) |
| Local dev | `.env` with the same two, or the old full `.env` (still works, precedence rule 3.4) |

Everything else (Gemini, Cloudinary, Telegram, IG, YT, GitHub dispatch token, SMTP, Google sign-in client, flags, caps) moves into the store. `GH_PAT` disappears (3.5).

### 3.4 Design

**Tables** (new Alembic revisions; the API never migrates, CI does [R: infra/README.md "Migrations run in CI"]):

```
config_keys    (version smallint PK, wrapped_dek bytea, kek_id text, created_at, retired_at)
config_values  (key varchar(64) PK, is_secret bool, ciphertext bytea|null, nonce bytea|null,
                value_plain text|null,          -- only for non-secrets (flags, model names)
                dek_version smallint, version int, fingerprint char(8)|null,
                source varchar(12),             -- ui | import | refresh | oauth
                updated_at, updated_by)
config_checks  (id, integration varchar(24), status varchar(10), code varchar(32), message text,
                evidence jsonb, ran_at, ran_in varchar(8), duration_ms int, config_version char(16))
config_meta    (singleton: canary_ciphertext, config_version, ...)
```

**Crypto** (OWASP: centralise, least privilege, audit, rotate [D: S26]):
- AES-256-GCM, fresh 96-bit random nonce per write, AAD = `key name || version` so ciphertexts cannot be swapped between rows. Library `cryptography` (**add to `requirements.txt` and the Lambda image; confirm size, U10**).
- Two levels (envelope): a **DEK** encrypts values; the **KEK** (`CONFIG_MASTER_KEY`, 32 random bytes, base64, generated by the installer) wraps the DEK. Rotating the KEK = rewrap one row. Rotating the DEK = re-encrypt all rows in one transaction. A `KeyProvider` interface (`EnvKeyProvider` now, `KmsKeyProvider` later) hides this [envelope pattern: D: S25 KMS concepts].
- `fingerprint` = first 8 hex chars of `HMAC-SHA256(KEK-derived key, value)`, secrets only. Plain SHA-256 of low-entropy values (e.g. a chat id) would be brute-forceable, which is why HMAC. (The existing workflow uses plain SHA-256 prefixes [R: check_secrets.py:139].)
- A **canary** row (known plaintext, encrypted) is decrypted at every start-up in both environments; failure = "key mismatch between Lambda and runner" (R-09).

**Resolver.** `get_env(name)` keeps its signature [R: config.py:34]. Order:
1. Phase 1 (migration, "env wins"): `os.environ` (existing GitHub Secrets / SSM) -> store -> default.
2. After burn-in (flag `CONFIG_PRECEDENCE=store`): store -> `os.environ` -> default.
The UI shows per field **"Source: environment override"** when env wins, with the text "editing here will not take effect until you remove the old secret" (R-14).
- Lambda: process cache with 60 s TTL, invalidated on own writes (fixes F6). Runner: lazy, per-process. On first resolution of each secret the runner prints `::add-mask::<value>` before use (pattern already used for the IG token [R: refresh_token.py:44-45]); this matters because GitHub only auto-masks values it knows as secrets.
- Update with optimistic concurrency (`version`): stale write -> 409 "changed by someone else, reload".

**API surface** (all admin-only, CSRF + rate limited, same pattern as `generate.py` [R: generate.py:26-34]):

| Endpoint | Behaviour |
|---|---|
| `GET /api/config` | Per-integration: `status`, `evidence`, `last_verified_at`, `expires_at`, per-field `{set: bool, source, updated_at, updated_by, fingerprint?}`. **Never** a secret or its last characters |
| `POST /api/config/{integration}/verify` | Body optional. With a body = verify-before-save (3.4 below). Without = re-check stored values |
| `PUT /api/config/{integration}` | Save (internally calls verify first; `?force=true` only for outcome `unknown`) |
| `DELETE /api/config/{integration}/{field}` | Remove, confirm dialog, audited |
| `GET /api/config/readiness` | Predicate result (7.5) |
| `POST /api/config/pipeline-test` | Dispatches `preflight.yml` (6.11); returns job id; polled like Generate jobs [R: generation_jobs] |
| `GET /api/config/{youtube|instagram}/start` + `/callback` | OAuth connect flows (Phase 3) |

**Audit** into `activity_log` with `source="config"` [R: activity.record, models.py:138-155]: `config.saved`, `config.removed`, `config.verified`, `config.verify_failed`, `config.imported`, `config.token_refreshed`, `config.key_rotated`, `config.test_message_sent`. `detail` holds field **names**, outcome and error code, never values. (activity.py already says "never put passwords, codes, tokens" [R: activity.py:7].) Retention 90 days [R].

### 3.5 What this fixes in the existing jobs

- `refresh-token.yml` writes the new token to the store (`source=refresh`), updates `expires_at`, and no longer needs `GH_PAT` or `gh secret set` [R: refresh_token.py:42-56]. It needs only `DATABASE_URL` + `CONFIG_MASTER_KEY`.
- `check-secrets.yml` loses its hard-coded owner IDs and fingerprints (F2); its logic becomes the shared verifier library `src/verify/` called by both the Lambda endpoint and the scheduled health check.
- `scripts/has_work.py` stays a no-secret gate (only `DATABASE_URL`) [R: has_work.py:37].

### 3.6 Security properties (testable)

| # | Property | How tested |
|---|---|---|
| S1 | No endpoint ever returns a secret or part of one | Contract test over every response of `/api/config*` with sentinel values |
| S2 | DB dump alone reveals no secret | Test with DB only, no master key |
| S3 | Logs, `activity_log`, Telegram notifications and exception messages never contain a secret | Sentinel-value test through every verifier + the redaction filter (6.0, R-05) |
| S4 | Only a signed-in admin can write; CSRF required; per-user rate limit | API tests (pattern exists [R: api/tests]) |
| S5 | A failed verify never alters stored values | Test: save bad value over good, assert unchanged |
| S6 | Concurrent edits cannot silently overwrite | 409 test |
| S7 | KEK rotation: all values still decrypt, old KEK stops working | Rotation test |
| S8 | `PUBLISH_ENABLED=false` (and all verifiers) cannot cause any publish | Test with a fake provider recording every call |

**Who can read values back:** nobody through any UI/API. The Lambda and runner decrypt in process memory only. A compromise of either process exposes the secrets it can decrypt; that is inherent to every option and is why verification endpoints are admin-only, rate-limited and never echo input.

### 3.7 Failure modes of the recommended design

| Failure | Effect | Handling |
|---|---|---|
| Neon asleep (scale-to-zero after 5 min, free plan cannot disable; resume "a few hundred ms to a few seconds") [D: S23] | First config read slow | One retry, 10 s connect timeout, "database waking up" message |
| DB unreachable at runner start | Generation cannot start | Already true in DB mode [R: has_work.py]; fail fast with `config_store_unreachable`, Telegram alert [R: main.py:336 pattern] |
| Master key differs between SSM and GitHub secret | Decrypt failure | Canary check at start-up in both; Readiness shows `key_mismatch` with fix steps |
| Master key lost in both places | Secrets unrecoverable | Documented recovery: re-enter values; installer offers a one-time "recovery key" display (OQ9) |
| Value edited while a run is in progress | Run uses the value read at its start | Acceptable; shown in run log as config version used |
| Lambda warm container holds old value | Up to 60 s stale | TTL + invalidate on write |

### 3.8 Migration without downtime, and rollback

1. Ship tables + resolver with **env-wins** precedence. Nothing changes for the running system.
2. Installer/script `scripts/import_env_to_store.py` (same shape as `infra/put_secrets.py`: dry-run lists **names only**, `--apply` writes) reads `.env`, encrypts, stores with `source=import`, writes the master key to SSM and GitHub secrets, and runs verify on each integration. Values are never printed.
3. Operator confirms all cards are green in Config.
4. Flip `CONFIG_PRECEDENCE=store`. Run the pipeline test (6.11). Watch one full day of scheduled slots.
5. Remove old GitHub secrets and SSM params for migrated keys, one integration at a time.
6. **Rollback:** set `CONFIG_PRECEDENCE=env` (still present until step 5), or restore the old secret. The store is additive, so removing it changes nothing else.

---

## 4. Research: what makes setup fast and trustworthy (task C)

### 4.1 Patterns observed in products people consider good, and what we take

| Principle | Evidence (official/primary where possible) | Applied here |
|---|---|---|
| **Connection health is a first-class, always-visible status** with states like expired / disconnected / error, and a one-click Reconnect | HubSpot "Connected apps" shows "Needs your attention" for expired, disconnected and errored connections and a Reconnect action [D: S27a]. Zapier lists connections and offers Reconnect [D: S27b] | Status cards (7.2), a global Readiness banner, a Reconnect action per card |
| **A "Test" next to credentials, run before relying on them** | n8n credential types can define a `test` request so a Test button validates before saving [D: S27c; the page says some credential types have it] | Verify button per card; verify-before-save |
| **Write-only secrets; hide after save** | Vercel "sensitive" env vars can't be viewed or edited later, only replaced [D: S27d] | Secrets write-only (SEC-1); "Replace" not "Edit" |
| **Test mode / dry run before live, plus an explicit go-live checklist** | Stripe: use test environments from account creation; go-live checklist; swapping keys is the switch [D: S27e] | Pipeline test (6.11) and `PUBLISH_ENABLED` gate; "Ready to publish" checklist |
| **Progressive disclosure:** the few needed options first, the rest behind a labelled secondary level | Nielsen's definition [2nd: S27f] | Advanced accordions (model lists, SMTP details, API version) |
| **Checklist and wizard guidelines:** 3-7 items, quick wins first, progress bar, don't start at 0% | Onboarding-checklist guidance [2nd: S27g] | Tiered wizard (4.3), progress starts after Step 0 |
| **Short time-to-first-value** | same | Tier 1 reaches "generate and see previews in Telegram" before any Meta/YouTube work |
| **OAuth "Connect" over pasting tokens** where the provider allows it | Instagram Business Login exposes authorize + token-exchange + refresh endpoints [D: S10]; Google OAuth web flow with offline access [R: get_yt_token.py:33] | Phase 3 Connect flows |

I did not find primary-source UX research for Buffer, Segment, Make or Twilio within this session's searches, so they are **not** cited as evidence (U13). The principles above stand on the sources listed.

### 4.2 Concrete rules derived (apply to every screen)

1. Never ask for something the system can discover (e.g. `IG_USER_ID` comes from `/me` [R: publish.py:110-111]; bot name from `getMe`; chat id from detection).
2. Every field has: where to get it (deep link + 3-line step card), an example of the **shape** (never a real value), and a one-click paste cleaner (strips quotes, `NAME=` prefix, whitespace [R: check_secrets.py:133-134]).
3. Errors say **what happened, why, and the exact next click**, never the provider's raw body.
4. A red status always has a primary button that fixes it.
5. Nothing is ever "saved but silently broken": every card shows its last verification time.
6. Optional integrations are skippable and never block "Ready".
7. Time-box steps: show an honest estimate per step.

### 4.3 Target setup-time budget [EST: measure in S-UX with 5 first-time users]

| Tier | Result | Active time target | Dominant steps |
|---|---|---|---|
| **0. Deploy** (outside Config) | Dashboard reachable | not budgeted here | AWS/Neon/GitHub/CloudFront; see 4.4 |
| **1. Generate-ready** | Generate works; previews arrive in Telegram; nothing posts | **<= 8 min** | Gemini key (2), Telegram bot + chat (3), Cloudinary (2), GitHub token + repo (3) |
| **2. Publish to Instagram** | Approved items post to IG | **+ <= 10 min** | Meta developer app, Instagram product, add account/tester, generate token (6-9) |
| **3. Publish to YouTube** (optional) | Approved reels go to Shorts | **+ <= 10 min** | GCP project, enable API, consent screen **In production**, OAuth client, authorize (7-10) |
| **4. Quality of life** | Email OTP, Google sign-in, brand | + <= 5 min | SMTP app password, Google client |
| **Total, all tiers** | | **~25-35 min [EST]** | |

Stating honestly: **"under 15 minutes for everything" is not credible** given steps that need a human in a third-party console. The defensible promise is **"under 15 minutes to a first approved Instagram post"** (tiers 1+2) provided tier 0 is done. Tier 3 and 4 are optional and can be done later without blocking anything.

### 4.4 Steps that dominate time and cannot be fully automated

| Step | Why it can't be automated | How we shorten it |
|---|---|---|
| Create a Meta developer app (Business type), add Instagram product, add the Instagram professional account as a tester/role | Requires the user's Meta login and an account that is a Business/Creator professional account; personal accounts cannot publish [2nd: S11b]; only people with a role on the app can use Standard Access, no App Review needed for your own account [D: S11a] | Step card with screenshots; deep link to `developers.facebook.com/apps`; a pre-written checklist "App type = Business; Product = Instagram API with Instagram Login; Roles > Instagram Testers" [D: S9]; copy-buttons for any value we supply |
| Generate an Instagram token | App Dashboard "Generate token" per account [D: S9]; lifetime of this token unclear (U2) | Phase 1: paste. Phase 3: Business Login "Connect" which returns a 1-hour token that we exchange to a 60-day one with the app secret [D: S10, 2nd summary] |
| YouTube: GCP project, enable YouTube Data API v3, consent screen, OAuth client | Google console, user's own Google account | Re-use one Web client for both Google sign-in and YouTube (U8) so the user creates one client; pre-filled redirect URI displayed with a copy button (exact-match rule [D: S30]); explicit step "Publish app -> In production" (the 7-day trap [D: S17,S18]) |
| Google consent screen "unverified app" warning on first authorize | Google shows it for sensitive scopes; `youtube.upload` is a sensitive scope [2nd: S17b] | Docs show the exact screen and "Advanced > Continue" click; no cap issue for one's own account (100-user cap only matters beyond that [2nd: S17b]) |
| Redirect URI propagation | Google says changes can take minutes to hours [2nd: S30] | Wizard says so and offers "Test again" with a countdown, not an error |
| Telegram: talk to @BotFather, press Start on the bot | Telegram design: bots cannot start conversations [2nd: S20b] | Deep link `t.me/BotFather`; auto-detect chat id (6.4) |
| Gemini free-tier terms | User must accept Google's terms | Show the data-use notice (6.1) |
| YouTube API audit (public uploads) | Human review by Google: projects created after 2020-07-28 that are unaudited get private-only uploads [D: S16] | Say it up front; `YT_PRIVACY` shown as "effective: private until audited" |
| Meta App Review/Business Verification | Only needed for Advanced Access (serving accounts you do not own) [D: S11a] | Not needed for a single-brand deployment; documented as the trigger for multi-customer SaaS (OQ1) |

**Step 0 recommendation (out of scope, flagged because it dominates):** a single `deploy` command, a GitHub **template repository** (not a fork: forks have scheduled workflows disabled by default [D: S22 disabling]) and the installer generating the master key. Public repos also get scheduled workflows disabled after 60 days without repository activity [D: S22 disabling]; private repos get 2,000 free minutes/month on a Free plan [D: S22 billing]. The Config health check detects the disabled state (6.9).

---

## 5. Verification principles (apply to every check in section 6)

| Rule | Detail |
|---|---|
| Three depths | **L1 Format** (local, instant) -> **L2 Live** (provider call, <= 10 s, runs in the Lambda: no VPC, internet egress [R: infra/README.md]; Lambda timeout is 30 s [R: template.yaml:71]) -> **L3 Capability** (needs the runner: Chromium/FFmpeg [R: generate-section 2.1]) |
| Result shape | `{status: ok|warn|fail|unknown|skipped, code, message, evidence{}, expires_at?, ran_at, ran_in, duration_ms}`. `evidence` is non-secret (`@username`, cloud name, "3/100 posts used"). |
| Failure classes (shared) | `format`, `rejected` (credential wrong), `forbidden` (valid but lacking permission/scope), `expired`, `quota` (valid, no budget), `rate_limited`, `mismatch` (two fields disagree), `not_found` (repo/chat/model), `unreachable` (provider/network), `misconfigured` (e.g. webhook set, consent screen in Testing), `unknown` |
| `unknown` is not `fail` | A provider outage must not look like a bad key. `unknown` lets the user "Save anyway" with a confirm (UX-6) and re-verifies automatically later. |
| Cooldowns | Per integration: 10 s between manual verifies; automatic re-verify at most daily; mutating/visible tests (Telegram message, SMTP mail, pipeline test) 60 s / 60 s / 10 min. Per user: 20 verify calls/min (existing `RateLimiter` pattern [R: generate.py:33]). |
| Never in a check | Publish, create a queue item, write `posted_topics`, send a Telegram message **with approval buttons**, spend Gemini generation quota without an explicit click, leave test assets behind (`finally` cleanup), echo or log input |
| Redaction (build first, R-05) | A logging filter plus a `redact()` for exceptions: replace every known secret value and any `access_token=`/`key=`/`bot<token>`/`cloudinary://...:...@` pattern before logging, activity or Telegram. Wrap `requests` calls to pass tokens in headers where the provider allows (Telegram bot token is in the URL path by design [D: S20]; Instagram accepts it as a parameter [R: publish.py:51]) |
| Reuse | Refactor `scripts/check_secrets.py` into `src/verify/<integration>.py` returning structured results; keep the script as a thin CLI over it [R: check_secrets.py:162-166] |

---

## 6. Per-integration validation (task D)

Format used: **Check / Proves / Success / Failure classes -> user message / Retry / Must NOT**.

### 6.1 Gemini

| | |
|---|---|
| L1 | Non-empty, trimmed, no quotes, no `GEMINI_API_KEY=` prefix. **No prefix/length rule** because Google's key scheme is changing (U1). |
| L2a | `GET https://generativelanguage.googleapis.com/v1beta/models` (the repo uses the SDK `models.list()` [R: check_secrets.py:54]; endpoint [D: S3]). **Proves:** the key is accepted and the Generative Language API is reachable. **Does not prove:** generation quota, the chosen model, or structured-output support. Whether `models.list` consumes quota is unspecified (U4). |
| L2b | `countTokens` on the configured model with a one-word prompt. **Proves:** the model id exists and the key may use it. Documented as free of charge, 3000 RPM [2nd: S6 Firebase page about the same API; promote via S0]. Replaces guessing from a 404 [R: llm.py:67-69]. |
| L2c (opt-in click, "Run a real test, uses 1 request") | One `generateContent` with the pipeline's JSON schema, `maxOutputTokens` small. **Proves:** the exact capability the pipeline needs (`response_schema`) works on this key and model [R: llm.py:46-52]. Costs 1 of the daily requests (RPD resets at midnight Pacific; limits are per **project**, not per key [D: S2]), so an extra key from the same project adds no quota. |
| Failure -> message | `400 API key not valid` [D: S1] -> "Gemini rejected this key. Re-copy it from AI Studio (no spaces, no quotes)." / `403` permission or API not enabled / key restricted [D: S1 troubleshooting, excerpt limited; confirm S0] -> "The key is valid but not allowed to call Gemini. Check the key's API restrictions." / `404` model -> "Model X doesn't exist for this key. Use the suggested model or clear the field." / `429` -> distinguish **rate limit** vs **daily quota** by the nested reason, or by a 30 s retry [D: S1] -> "Your key works but its quota is used up. Free quota resets at midnight Pacific (about 12:30 IST in summer time, 13:30 in winter [EST of the offset; the midnight-Pacific rule is D: S2])." / `5xx/503` -> `unknown` "Gemini is busy; the pipeline has a fallback chain [R: llm.py:20]" / network -> `unreachable`. |
| Free-tier notice (must show) | Free-tier prompts/outputs can be used to improve Google products and reviewed by humans; paid tier does not; if the product serves people in the EEA, Switzerland or UK, Paid Services terms apply [2nd: S5 + D: S5 billing page]. Show once at key entry with a link; do not decide for the customer. |
| Warning | Standard vs auth keys deadline (U1): shown as a card warning if the verified key type is "standard" once the doc is confirmed. |
| Retry / cooldown | 10 s manual; on `429` do not auto-retry for 60 s. |
| Must NOT | Call `generateContent` without the explicit opt-in; cache the key in the browser. |

### 6.2 Instagram (Instagram API with Instagram Login, `graph.instagram.com`)

| | |
|---|---|
| L1 | `IG_USER_ID` digits only [R: check_secrets.py:73-74]; token non-empty, trimmed, not containing whitespace/quotes/`NAME=`. No length rule documented (U3). |
| L2a | `GET /me?fields=user_id,username,account_type` [R: publish.py:150]. **Proves:** token valid for an account; returns the id to auto-fill and compare with `IG_USER_ID` [R: publish.py:151-153]. `account_type` should indicate a professional account; personal accounts cannot publish [2nd: S11b]; exact enum values (U6). |
| L2b | `GET /{id}/content_publishing_limit?fields=quota_usage,config` [R: publish.py:154]. **Proves:** account is publishing-capable enough to answer the limit query (whether it requires the publish scope is U7). Shows used/total of the **100 API-published posts per rolling 24 h** [D: S8]. Warn at >= 80%. |
| L3 (deep, no post) | Create a **container** only: `POST /{id}/media` with `image_url` of a test JPEG (Instagram accepts only JPEG [R: upload.py:3-4]) uploaded to Cloudinary, poll `status_code` to `FINISHED`, then **never call `media_publish`**. Containers not published within 24 h become `EXPIRED` [D: S13]; the quota is enforced on `media_publish` [D: S8]. **Proves:** the token's content-publish permission and that Instagram can fetch our Cloudinary URLs. In the pipeline test the same is done with the real rendered reel (REELS container) to prove IG accepts the MP4. Not yet proven: whether a dangling container has any visible effect or counts toward anything (U7). |
| Expiry | Long-lived tokens last 60 days; refreshable only when >= 24 h old and unexpired, via `GET /refresh_access_token?grant_type=ig_refresh_token`; the refreshed token is valid 60 days from refresh; requires `instagram_business_basic` [D: S7]. The refresh response gives `expires_in` [D: S7], so **expiry is only known after the first successful refresh**. Until then the card says "Valid. Expiry will be confirmed within 48 h." We never guess from `saved_at`, because a pasted token may already be 59 days old. A documented debug endpoint for IG-Login tokens was not found (U2b). |
| Failure -> message | code `190` without subcode = invalid/expired/revoked; subcodes `463`/`467` = expired [D: S12] -> "Instagram says this token is invalid or expired. Generate a new one (steps)." (existing message at [R: publish.py:72-74]). `4/17/32/613` rate limits and the transient set [R: publish.py:38] -> `rate_limited`/`unknown`. User-id mismatch -> `mismatch` "This token belongs to @x (id N) but IG_USER_ID is M. Use the id we detected? [Use it]". Container `ERROR` with `2207xxx` subcodes: `2207003` timeout fetching media, `2207020` expired, `2207008` builder missing [D: S12 error codes] -> specific advice. Permission-denied code (U7). |
| Reel media specs the pipeline must meet (checked in P5) | MP4/MOV, H.264/HEVC, AAC <= 48 kHz, 23-60 fps, 3 s to 15 min, <= 300 MB, no edit lists, moov atom at front, recommended 9:16 [D: S13 per excerpt; U17 to confirm on the page] |
| App access | Standard Access suffices for an account you own/manage; no App Review needed. Advanced Access (App Review + Business Verification) is only for serving accounts you don't own [D: S11a]. |
| API version | `IG_API_VERSION` default `v21.0` [R: publish.py:46]. v21.0 released 2024-10-02 [D: S14]; deprecation date reported as 2027-01-21 (U5, R-21): a health check warns when the configured version is within 90 days of its published sunset once confirmed. |
| Retry / cooldown | Manual 10 s; deep L3 check 10 min and **only** on explicit click or in the pipeline test. Container polling uses the repo's 4-10 s interval [R: publish.py:83,130-144]. |
| Must NOT | Call `media_publish`; ever; create a carousel parent; run L3 automatically on a schedule. |

### 6.3 YouTube

| | |
|---|---|
| L1 | `YT_CLIENT_ID` ends `.apps.googleusercontent.com`; `YT_CLIENT_SECRET` starts `GOCSPX-`; `YT_REFRESH_TOKEN` starts `1//` [R: check_secrets.py:112-116]. Warn-only (heuristics from the owner's working values, not a documented contract, U9b). |
| L2a | Refresh -> access token via `https://oauth2.googleapis.com/token` (the repo does `creds.refresh()` [R: publish_youtube.py:64-75]). **Proves:** client id+secret+refresh token are mutually valid. |
| L2b | `tokeninfo` on the fresh access token returns `scope` and `expires_in` [D: S19, endpoint documented as `oauth2/v2/tokeninfo`; host variant U11] -> assert `youtube.upload` is in `scope`. **Proves the scope**, not the channel. |
| L2c | `channels.list?part=snippet&mine=true` costs 1 unit and shows the channel title, proving a channel exists. **It needs a read scope** (`youtube.readonly`), which `youtube.upload` alone is not believed to grant (U14). Therefore **proposal PQ6**: request `youtube.upload` + `youtube.readonly`, giving a channel-level proof and showing "Uploading to: <Channel name>". Alternative if declined: no channel proof until the first real upload. |
| Deep check | **Not possible without side effects.** A real `videos.insert` costs 1,600 units of the default 10,000/day [D: S15] (about 6 per day, matching README [R]) and creates a video (private) that cannot be deleted with upload-only scope (U14). We therefore **do not test upload**. We test everything before it: token, scope, channel (if readonly), media URL reachability and metadata build in the existing `--dry-run` [R: publish_youtube.py:208-218]. The first real post is the final proof, and its failure is classified (below). |
| The 7-day trap | Consent screen in **Testing** => refresh tokens expire after 7 days; **In production** removes that; tokens can still die if unused ~6 months, revoked, or beyond 100 live tokens per account per client [D: S17 (publishing status), 2nd: S18 for the 100/6-month figures; confirm on Google's OAuth page in S0]. Not detectable through an API call (U15). Therefore track `first_issued_at` and show **"Long-lived: unconfirmed"** until the token has survived > 8 days, then **"Confirmed"**. If it dies near day 7, message: "Your Google consent screen is probably still in Testing. Set Publishing status to In production and reconnect." (existing text [R: publish_youtube.py:71-74]). |
| Unverified project | Videos uploaded through `videos.insert` by unverified API projects created after 2020-07-28 are forced **private** until an API audit passes [D: S16]. Card shows "Effective privacy: private until audited (Google rule)" next to `YT_PRIVACY`. |
| Quota | 1,600 units/upload, 10,000/day default, reset midnight Pacific [D: S15]; we count our own uploads and show "~N uploads left today (estimate)" because quota remaining is not exposed by an API I could find (U16). |
| Shorts | No separate Shorts endpoint; classification is automatic by aspect ratio and length (<= 3 min since 2024-10-15) [2nd: S29]. Pipeline test P5 asserts 9:16 and duration <= 3 min. |
| Failure -> message | `invalid_grant` -> "Google rejected the saved login (expired, revoked, or consent screen still in Testing). Reconnect YouTube." / `invalid_client` -> "Client ID or secret doesn't match." / insufficient scope -> "This login lacks upload permission. Reconnect and tick the YouTube permission." / `quotaExceeded` -> "Daily YouTube quota used. Resets midnight Pacific." [R: publish_youtube.py:183-185] / `uploadLimitExceeded` [R: :184] / channel missing -> "This Google account has no YouTube channel" (reason string U14) |
| Retry / cooldown | Manual 10 s; automatic daily. |
| Must NOT | Upload anything; cost quota units beyond a 1-unit read. |

### 6.4 Telegram

| | |
|---|---|
| L1 | Token `\d+:\S+` (warn-only, exact length undocumented, U9); chat id integer [R: check_secrets.py:33-34]. |
| L2a | `getMe` [R: check_secrets.py:38]. **Proves** the token; returns bot id/username to display. |
| L2b | `getWebhookInfo`: if `url` is set, `getUpdates` cannot work because they are **mutually exclusive** [D: S20]; our poll job uses `getUpdates` [R: approve_bot.py:6-8]. -> `misconfigured` "A webhook is set on this bot, which blocks approvals. [Remove webhook]" (button calls `deleteWebhook` after a confirm). |
| L2c | `getChat(chat_id)` [R: check_secrets.py:42]. **Proves** the bot can see the chat. Typical failure "chat not found" = wrong id or the user never pressed **Start**; bots cannot initiate conversations [2nd: S20b]. |
| L2d (explicit click) | `sendMessage` "Test message from <brand> setup. If you can read this, approvals will reach you." No buttons. **Proves** delivery (API returns a message object [D: S20]). The UI asks "Did it arrive?" because API success proves send, not that the human sees it. |
| Chat-id detection (wizard) | After the user sends `/start`, read `getUpdates` **without an `offset`**, `limit<=5`, `timeout=0`. Reason: updates are confirmed only when `getUpdates` is called with a higher `offset` [D: S20]; without an offset the earliest unconfirmed updates are returned and not confirmed, so we do not steal button presses from the poll job. Additionally ignore any update whose `update_id` is below the stored `tg_offset` [R: queue offset in settings row `tg_offset`, README] and **never advance the offset**. Run only when no poll/generation job is active (poll uses the same `getUpdates` and concurrent long-polls produce HTTP 409 "terminated by other getUpdates request" [2nd: S20c]). Spike S9 proves this on a real bot (U18). |
| Group chats | Bot must be a member; negative ids; "only presses from `TG_CHAT_ID` count" [R: approve_bot.py:8]. |
| Failure -> message | `401 Unauthorized` -> "Telegram doesn't recognise this token. Copy it again from @BotFather." / `409` -> "Another process is reading this bot's updates. Wait a minute, or check you haven't set the same token in a second app." / `chat not found` -> "Open your bot in Telegram, press Start, then click Detect." / `403 blocked` -> "You blocked the bot; unblock it." / network -> `unreachable`. |
| Must NOT | Send a preview with Approve/Reject buttons; advance `tg_offset`; call `setWebhook`; spam (60 s cooldown on message tests). |

### 6.5 Cloudinary

| | |
|---|---|
| L1 | `cloudinary://<key>:<secret>@<cloud>` after cleaning (prefix tolerated) [R: upload.py:28-33]. The canonical field name written is `CLOUDINARY_URL` only (F7). |
| L2a | Admin API `ping` [R: check_secrets.py:60-68]. **Proves** key+secret+cloud match. The Admin API is rate-limited: 500 requests/hour on the free plan, 2,000 on paid starts; the Upload API is **not** rate-limited [D: S21]. => one `ping` per verify, daily at most automatically. |
| L2b | Upload a tiny test JPEG as `codexone/_selftest/<random>` via the **Upload** API (not rate-limited), `HEAD` its `secure_url` expecting 200 and an image content-type, then delete it. **Proves** upload permission + public HTTPS delivery (what Instagram and Telegram will fetch [R: upload.py:3, approve_bot.py:163-171]). API keys can be restricted by custom policies on paid plans, which would show as `forbidden` [D: S21 permissions]. |
| Limits to surface | Free-plan max video size 100 MB [D: S21 / support post]; Instagram accepts up to 300 MB [D: S13]; the pipeline test checks the real reel size against the lower one. |
| Failure -> message | credential `401` -> "Cloudinary rejected the key/secret/cloud name. Re-copy the whole 'API environment variable' from Settings > API Keys." (exact status/body strings U19) / rate limit -> `rate_limited` / quota or credits exhausted (U19) / network. |
| Must NOT | Leave test assets; call Admin API more than once per check; use the delete-all or `resources` list endpoints. |

### 6.6 GitHub token and repository

| | |
|---|---|
| L1 | `GITHUB_REPOSITORY` matches `owner/name`; token not empty. |
| L2a | `GET /repos/{repo}/actions/workflows/{poll-approvals.yml}` with the token. **Proves** repo reachable, token has at least Actions: read [D: S22 workflows page: list/get need read], the workflow file exists, and returns `state`: `active`, `disabled_fork`, `disabled_inactivity`, `disabled_manually`, `deleted` [D: S22; third-party schema listing, confirm S0]. This catches the **fork** and **60-day inactivity** traps [D: S22 disabling]. |
| L2b | The `GitHub-Authentication-Token-Expiration` response header gives the PAT expiry date [D: S22 changelog] -> `expires_at`; warn at 14 and 3 days. |
| L2c | **Write permission cannot be proven without dispatching.** Creating a workflow dispatch event needs **Actions: write** [D: S22]. We prove it with the **pipeline test** (6.11), whose dispatch is harmless (it does not publish and costs only Actions minutes). In the wizard, the first card shows "Read access OK; write access confirmed at the system test". |
| Failure -> message | `401` -> "GitHub doesn't accept this token (expired or mistyped)." / `403` with rate-limit headers -> `rate_limited` [R: github_actions.py:56-62] / `403` otherwise -> "Token lacks Actions permission. Edit the token: Repository permissions > Actions > Read and write." / `404` -> "Repository not found or the token can't see it. GitHub hides repos you lack access to as 404 (U20)." / `422` on dispatch -> "The workflow has no `workflow_dispatch` trigger or the branch is wrong." [R: `rejected` set github_actions.py:63-64] / state `disabled_*` -> "Scheduled/dispatched workflows are disabled (reason). [How to enable]". |
| Must NOT | Dispatch outside the pipeline test; request `Secrets: write` (not needed after 3.5); store the PAT with broader scope than documented (the guide tells users to select one repository only). |

### 6.7 Database (Neon/Postgres)

| | |
|---|---|
| Check | Connect with a 10 s timeout and one retry, `select 1`, read `alembic_version` and compare to migration heads [R: check_secrets.py:145-159], run a **write inside a transaction that is rolled back** on `config_meta` (proves write permission without changing data). Measure latency. |
| Proves | Connectivity, credentials, schema at head, write permission. |
| Messages | cold start -> "Database is waking up (Neon free plan sleeps after 5 minutes idle) [D: S23]; retrying." / schema behind -> "Database schema is older than the app. Run the migration job (`poll-approvals` runs `alembic upgrade head` on each run [R: poll-approvals.yml:62-65])." / pooled URL on Lambda -> warn: Lambda uses the **direct** URL, pooled breaks prepared statements [R: put_secrets.py:22-23]. |
| Note | `DATABASE_URL` is **bootstrap**, so this card is read-only status, never an edit form. |

### 6.8 SMTP / email

| | |
|---|---|
| L1 | Host non-empty; port int; `SMTP_SECURE` in `ssl/starttls/none`; `MAIL_FROM` valid email or falls back to `SMTP_USER` [R: mailer.py:127-141]. Hint if port 465 with `starttls` (default is ssl on 465 [R: mailer.py:136]). |
| L2a | Connect, `STARTTLS`/SSL, `login` with **no message sent** (the repo's `_connect` + `login` [R: mailer.py:92-110]). **Proves** reachability and credentials. |
| L2b (explicit click) | Send a real test email **only to the signed-in admin's own verified address** (`email_verified_at` [R: models.py:116]), never to arbitrary addresses (no open relay behaviour). Ask "Did it arrive?" because provider acceptance != inbox delivery. |
| Provider notes | Gmail: `smtp.gmail.com`, 587 STARTTLS or 465 SSL, an **app password** with 2-Step Verification, full address as username [2nd: S24; Google's own page not retrieved, U21]. |
| Failure -> message | `SMTPAuthenticationError` -> "The mail server rejected the username or password." [R: mailer.py:114-115] / refused recipient / `Couldn't reach the mail server` [R: mailer.py:123] with port/TLS hints. |
| Readiness | Mail is **optional**, but while `MAIL_DRIVER=console` password-reset codes are written to logs and `data/outbox` [R: mailer.py:16,54-67]. Card must say "Email not configured: password reset by email is unavailable" and the API should refuse `console` when `COOKIE_SECURE=true` (R-06). |
| Must NOT | Send to anyone but the admin; retry auth failures [R: mailer.py:114]. |

### 6.9 Google OAuth client (sign-in, and later YouTube Connect)

| | |
|---|---|
| L1 | Client id ends `.apps.googleusercontent.com`; secret `GOCSPX-` (warn-only). |
| L2 (credential validity) | Server-side `POST https://oauth2.googleapis.com/token` with the client id/secret and a **deliberately invalid** authorization code. Expectation: `invalid_client` = id/secret wrong; `invalid_grant` = client authenticated but the code is bad, i.e. **credentials are valid**. This is standard OAuth behaviour but Google's exact behaviour and ordering of checks is not documented in what I retrieved (U22), so the spike must confirm before we ship it. |
| Redirect URI | Cannot be verified server-side without a browser. Provide **"Test sign-in"** which opens a popup to our own `/api/config/google/test-start`; success = our callback receives a valid `state`. Google requires the redirect URI to **exactly** match a registered one (scheme, host, port, path, trailing slash), HTTPS except localhost, no wildcards, and changes can take minutes to hours [2nd: S30]. UI always shows the exact URI to register: `<PUBLIC_URL>/api/auth/google/callback` [R: README, deploy.sh:55] with a Copy button. |
| Safety | Saving a sign-in change must not lock the owner out: require that password login still works or that the current admin's email is in `ALLOWED_GOOGLE_EMAILS`; Google config is read once by `settings()` [R: settings.py:39] so it stays in the **guarded Advanced** area until `settings()` becomes dynamic (R-12). |

### 6.10 Source reachability (generation depends on it)

`fetch_topics` uses HN (Algolia), Reddit, dev.to, GitHub search, arXiv [R: fetch_topics.py]; Reddit JSON falls back to RSS because it rate-limits [R: fetch_topics.py:144-151]. The pipeline test (P2b) fetches each source once and requires **>= 2 of 5** to answer, reporting which. This is a config-adjacent failure (runner IPs blocked) that otherwise surfaces as a failed first Generate.

### 6.11 PIPELINE capability test ("can this configuration produce a video?")

New workflow `.github/workflows/preflight.yml`, `workflow_dispatch` with `request_id` (run-name carries it, the pattern the Generate page uses [R: daily-generate.yml:2]), inputs read **only** through `env:` (the repo enforces this for user-typed inputs [R: daily-generate.yml:13-15]), own concurrency group, `timeout-minutes: 20`. Results are written to `config_checks` and `activity_log` by the job; the dashboard polls the job like a generation job [R: generation_jobs].

| Stage | What it does | Pass criterion | Fails with (examples) |
|---|---|---|---|
| P0 Boot | checkout, setup-python 3.11, `pip install -r requirements.txt`, `playwright install --with-deps chromium` [R: daily-generate.yml:80-88] | all exit 0; duration recorded | dependency or Chromium install failure |
| P1 Config load | load `DATABASE_URL`+`CONFIG_MASTER_KEY`, decrypt canary, resolve every required value (names only logged, `::add-mask::` applied) | canary OK; all Req present | `key_mismatch`, `missing:<NAME>` |
| P2 Database | connect, migration head, rolled-back write | as 6.7 | schema behind |
| P2b Sources | fetch each topic source once | >= 2 of 5 respond | which sources blocked |
| P3 Carousel render | render one slide with **real** brand templates and canned content via `src/render_post` | PNG exists, 1080x1350 [R: brand/config.yaml:29] | Chromium/launch error, missing font, bad brand colors |
| P4 Voice | edge-tts synthesize one sentence with the first configured voice | audio length > 0.5 s | voice id invalid; service unreachable. edge-tts calls Microsoft's Edge read-aloud endpoint with no API key [2nd: S28]; Microsoft Q&A indicates commercial use may need Azure Speech (R-22) |
| P5 Reel render | render a ~5 s reel (canned script) with audio + subtitles through the **real** `render_reel` | `ffprobe`: H.264 + AAC, 1080x1920, duration within +-1 s of expected, <= 300 MB, 9:16, **moov atom at the front, no edit lists** (IG requirement [D: S13 excerpt, U17]) | FFmpeg/MoviePy error; spec violations named individually |
| P6 Cloudinary | upload the MP4 + a JPEG to `codexone/_preflight/<id>`, `HEAD` both | 200, `video/mp4`, size < free-plan 100 MB if on free plan [D: S21] | auth/permission/size; assets deleted in `finally` |
| P7 Telegram (opt-in) | `sendVideo` of the test reel with **no buttons**, caption "Pipeline test" | message id returned; **also exercises the download-and-upload fallback path if URL fetch fails** [R: approve_bot.py:163-171] | 400 media fetch; chat issues |
| P8 Instagram dry check | `content_publishing_limit` + create a **REELS container** from the P6 URL, poll to `FINISHED`, **do not publish** | `FINISHED` within 15 min [R: publish.py:144 uses 900 s] | `ERROR` with subcode mapped to advice |
| P9 YouTube dry check | the existing `--dry-run` path: token refresh, metadata build, `HEAD` of reel URL [R: publish_youtube.py:208-218] | OK | `invalid_grant`, etc. |
| P10 Gemini (opt-in, "uses ~2 requests") | one `generate_json` with a tiny schema, then run `main.py generate --dry-run` only if the owner ticks "full generation dry run" (whether `--dry-run` calls Gemini is U23) | valid parsed object | quota/permission |
| P11 Dispatch round trip | the fact the job ran proves `GITHUB_DISPATCH_TOKEN` has **Actions: write** and the workflow is enabled | job started within 90 s [R: generate-section E11] | `not_started` |

- **Report:** per-stage pass/fail/skipped with duration, the user-actionable message from the verifier table, a link to the run, and the test reel offered for download (artifact, 1-day retention). Total time and minutes used are shown. Time [EST]: 4-8 minutes, dominated by P0.
- **Cost controls:** one run at a time (partial unique index like `generation_jobs` [R: models.py:166-170]); cooldown 10 min; counted against its own cap (default 6/day); P7/P10 off by default.
- **Must NOT:** publish; create or touch queue items; write `posted_topics`; call Gemini generation without the opt-in; leave assets in Cloudinary; send Telegram buttons; run on a schedule unprompted (except after a config change, via an explicit "Re-run system test" prompt).
- **Staleness:** a pass is recorded against the **config version** (7.5). Editing any required value makes the test result stale.

---

## 7. User journey and screens (task E)

### 7.1 Journey overview

1. Admin signs in to a fresh deployment (credentials from the installer [R: README sign-in]). Dashboard shows a **Setup banner** ("Setup 0 of 5. About 8 minutes to generate your first post.") and the sidebar `Config` item has a dot.
2. Opens **Setup wizard** (also reachable later as "Run setup again"). Tier 1 first.
3. Each step: *Where to get it* (guide sheet) -> paste -> **Verify & save** (inline spinner, specific result) -> next.
4. After tier 1 -> "Run system test" -> **Ready to generate** screen with a primary "Generate my first post" button (links to Generate) while tiers 2-3 stay as a checklist.
5. Tier 2/3 completed whenever; each unlocks its platform checkbox on Posts.
6. Day to day: Config is a **status page**; it nags only when something expires (7.7).

### 7.2 Config page (`/config`)

Layout: header with Readiness summary (7.5), then a grid of **integration cards** grouped as Required / Publishing / Optional.

Card statuses (badge, using the existing `StatusBadge` pattern [R: web/src/components/status-badge.tsx]):

| Status | Meaning | Primary button |
|---|---|---|
| Not set | no value | "Set up" (opens the wizard step) |
| Checking | verify running | disabled, spinner |
| Valid | last check ok | "Verify again" |
| Warning | works, but: expires in N days, quota >= 80%, privacy forced private, token expiry unconfirmed | context action ("Refresh now", "Read why") |
| Invalid | check failed | "Fix" (opens field with the message + guide step) |
| Stale | a required value changed since the last verification | "Verify" |
| Unknown | provider outage during the last check | "Retry" |
| Env override | value comes from an environment variable, not the store | "Move to Config" |

Each card shows: integration name and icon, status, one **evidence line** (e.g. "Bot @codeXoneByHiteshBot", "Cloud: mycloud", "@handle, Business account", "Token expires in 41 days", "Channel: X"), last verified (relative time), and up to three actions: **Verify**, **Edit/Replace**, **Guide**. Details drawer: per-field set/not-set, updated by/at, source, check history (last 10 results), the failure message with its code.

Cards: Gemini, Cloudinary, Telegram, GitHub (automation), Instagram, YouTube, Database (read-only), Email (optional), Sign-in with Google (optional, Advanced), Brand (existing `brand` row; edit later), Advanced flags (model overrides, `GENERATE_DAILY_CAP`, `PUBLISH_ENABLED`, `TELEGRAM_SYNC`, `IG_API_VERSION`, `YT_PRIVACY`).

Field behaviour:
- Secret fields are `type=password`, `autocomplete=off`, with show/hide while typing, and **never prefilled**. Saved state reads "Saved on 5 Oct by admin" plus **Replace**.
- Paste cleaner: strips whitespace, wrapping quotes, and a leading `NAME=`; shows "We removed the quotes" when it acts [R: check_secrets.py:133].
- Inline format validation on paste/blur (L1) with friendly text; format warnings are warnings, not blockers, wherever the format is a heuristic (U1, U3, U9).
- **Verify & save** runs L2 and saves only on `ok`/`warn`; on `fail` nothing changes and the message explains; on `unknown` offers "Save anyway" (confirm) and flags the card Unknown (UX-6).
- Multi-field integrations verify as a unit (IG user+token, Telegram token+chat, YouTube 3 fields, Cloudinary).
- Auto-fill: after a valid IG token, `IG_USER_ID` fills from `/me`; after a valid bot token, show the bot name.

### 7.3 Setup wizard (ordered; what can be skipped; what blocks "ready")

| # | Step | Est. [EST] | Skippable? | Blocks Ready-to-generate? | Blocks Ready-to-publish? |
|---|---|---|---|---|---|
| 0 | **Environment check** (read-only): DB reachable, migrations at head, master key present and canary decrypts, public URL, admin account | 0 min | no | yes | yes |
| 1 | **Gemini key** (deep link, 3 steps, free-tier notice) | 2 | no | yes | yes |
| 2 | **Telegram**: create bot, paste token, press Start in Telegram, **Detect my chat**, test message | 3 | no | yes | yes |
| 3 | **Cloudinary**: paste the API environment variable | 2 | no | yes | yes |
| 4 | **GitHub automation**: choose/enter repo (`owner/name`), create fine-grained token (one repo, Actions read/write), paste. Status shows workflow `state` | 3 | no | yes | yes |
| 5 | **System test** (6.11) with the opt-ins | 4-8 (waiting) | no | yes | yes |
| -- | **Milestone: Ready to generate.** "Generate my first post" | | | | |
| 6 | **Instagram**: guide, token paste (later Connect), auto-filled id, deep check on the system test | 6-9 | skippable (YouTube-only is valid) | no | yes for IG |
| 7 | **YouTube**: guide, Connect (later), privacy choice with the audit notice | 7-10 | skippable | no | yes for YT |
| 8 | **Brand** (handle, CTA, hashtags, colors, voices preview) | 2 | skippable (defaults exist [R: brand/config.yaml]) | no | no |
| 9 | **Email** and **Google sign-in** | 3-5 | skippable | no | no |
| 10 | **Scheduling**: shows the three cron-job.org jobs to create with copy buttons and notes GitHub's own schedule is a backup [R: README] | 5 | skippable | no | no (but "on-time posting" shows Warning) |

The wizard remembers progress server-side (per config), can be left and resumed, shows "N of M, about X minutes left", and starts the progress bar after step 0.

### 7.4 Docs area

**Route:** `/config/guide` (index) and `/config/guide/:integration`, plus a **side sheet** opened by each field's "Where do I get this?" link so the user never loses their place. Sidebar: "Docs" as a child under Config. Content lives in the repo as versioned markdown rendered by the web app (no external site), each guide stamped **"Verified against the provider's current screens on <date>"** and a "This looks out of date" link (R-19).

Common guide template: *What it's for* / *Time* / *Before you start* / *Steps with exact links and a screenshot per step* / *What you will see when it works* / *Troubleshooting by error code* / *Security notes (what this key can do, how to revoke it)*.

Guides (steps are outlines; every link below is an official console/doc URL I saw in search results, and S0 confirms each before publishing):

| Guide | Steps (outline) | Links |
|---|---|---|
| **Gemini** | 1 Open the API keys page. 2 Accept terms (first time creates a default project and key [D: S4]). 3 Create key. 4 Copy, paste. 5 Read the free-tier note. 6 Note quota is per project [D: S2] | https://aistudio.google.com/api-keys , https://ai.google.dev/gemini-api/docs/api-key |
| **Telegram** | 1 Open @BotFather (blue check). 2 `/newbot`, name, username ending `bot`. 3 Copy token. 4 Open your bot, press **Start**. 5 Click Detect my chat. 6 Group variant: add the bot, id is negative | https://t.me/BotFather , https://core.telegram.org/bots/api |
| **Cloudinary** | 1 Sign in. 2 Settings > API Keys. 3 Copy the "API environment variable" (contains key, secret, cloud name) [D: S21]. 4 Paste whole | https://console.cloudinary.com/settings/api-keys (path per S21; confirm deep link in S0) |
| **GitHub** | 1 Create repo from the template (not a fork). 2 Enable Actions. 3 Settings > Developer settings > Fine-grained tokens > Generate [D: S22]. 4 **Only select repositories** = this repo; Permissions > Repository > **Actions: Read and write**; set an expiration you can remember. 5 Copy. 6 Note expiry date (we warn) | https://github.com/settings/personal-access-tokens/new (confirm S0), PAT docs S22 |
| **Instagram** | 1 Switch the Instagram account to **Business or Creator** (professional) [2nd: S11b]. 2 Meta for Developers > create **Business** app [D: S9]. 3 Add product **Instagram API with Instagram Login**. 4 Roles > add your Instagram account as **Instagram Tester**; accept the invite in Instagram (U24). 5 App Dashboard > Instagram > API setup with Instagram login > **Generate token** [D: S9]. 6 Paste. 7 We auto-fill the id. 8 Explain 60-day token and automatic weekly refresh [D: S7]. 9 Why no App Review is needed for your own account [D: S11a] | https://developers.facebook.com/apps , S9, S10 |
| **YouTube** | 1 Create a Google Cloud project. 2 Enable **YouTube Data API v3**. 3 Google Auth Platform: configure consent screen. 4 **Audience > Publish app -> In production** (avoids the 7-day token expiry) [D: S17]. 5 Create **OAuth client ID: Web application**, add the exact redirect URI we display. 6 Paste client id/secret. 7 Click **Connect YouTube**, accept the "unverified app" warning for your own app. 8 Privacy and audit explanation [D: S16] | https://console.cloud.google.com/apis/credentials , S17 |
| **Email (SMTP)** | Provider cards: Gmail app password (2-Step Verification on, 16-char app password, 587/465 [2nd: S24]), SendGrid, SES, generic. Test email goes to you only | provider docs |
| **Google sign-in** | Same Google project; Web client; register `<PUBLIC_URL>/api/auth/google/callback`; wait for propagation [2nd: S30]; add allowed emails | S30 |
| **Scheduling (cron-job.org)** | Create the 3 jobs from the README with copy buttons; separate PAT | README table [R] |

**Troubleshooting index:** every verifier `code` has a page `/config/guide/errors/<code>` containing the plain-language cause, the exact fix steps, and the provider doc link. The card's "Fix" button links to it.

**Glossary:** API key, token, OAuth, refresh token, scope, consent screen/Testing vs In production, redirect URI, webhook vs polling, quota vs rate limit, long-lived token, container (Instagram), professional account, fine-grained token, workflow, Neon scale-to-zero, secret vs variable.

### 7.5 Readiness and the precise definition of "zero further config"

**Config version** = HMAC over (names + fingerprints of all required secret values + non-secret required values). Any edit to a required value changes it. Every verification and the system test are recorded against the version they ran under.

**READY_TO_GENERATE is true iff all of:**

| # | Condition |
|---|---|
| G1 | Environment check (step 0) passes: DB reachable, schema at head, canary decrypts **in both Lambda and runner** (runner side proven by the system test) |
| G2 | Gemini L2a + L2b `ok` (L2c `ok` if the opt-in was run; otherwise recorded as "not exercised") |
| G3 | Telegram L2a-L2c `ok`, no webhook set |
| G4 | Cloudinary L2a + L2b `ok` |
| G5 | GitHub token L2a `ok`, workflow `state = active` |
| G6 | A system test finished with stages P0-P6 passed, P8/P9 passed or skipped for unconfigured integrations, **for the current config version**, within the last 7 days |
| G7 | No required credential is `Invalid`, `Stale` or `Env override` with an unresolved conflict; none expires in < 3 days |
| G8 | `GITHUB_REPOSITORY` is explicitly set (no owner default, F1) |

**READY_TO_PUBLISH_IG** = READY_TO_GENERATE + I1 IG L2a/L2b `ok` and id matches + I2 P8 (reel container reached `FINISHED`) for the current version + I3 token expiry known and > 7 days (or refresh confirmed) + `PUBLISH_ENABLED=true`.
**READY_TO_PUBLISH_YT** = READY_TO_GENERATE + Y1 token refresh + scope `ok` + Y2 P9 `ok` + Y3 "long-lived confirmed" or an explicit acknowledgement of the 7-day risk + effective privacy shown.

**What the owner can truthfully be told when READY_TO_GENERATE is green:** *"The first Generate will not fail because of configuration."* **What this does not cover** (stated in the UI as "can still happen, not a setup problem"): provider outages (`unknown`), Gemini daily quota exhausted, topic sources blocked at that moment, a token that expires or is revoked later (health check alerts), Instagram rejecting a specific piece of content, and a GitHub run queue delay [R: generate-section E12].

Readiness drives the product: the Generate page's "dispatch not configured" state [R: generate-section E1] becomes "Not ready" with a link to the exact failing card; the global banner shows "Ready to publish: yes/no, here is what's missing" (list of failing conditions with Fix buttons).

### 7.6 Safeguards on risky settings

- **Google sign-in** and **admin credentials**: guarded Advanced; saving requires password re-entry; blocked if it would leave no usable login.
- **`PUBLISH_ENABLED`**: toggle with explicit confirm; copy "Turning this on lets approved posts go out."
- **Removing** a credential: confirm dialog stating consequences ("Posts will stop publishing to Instagram").

### 7.7 Re-verification, expiry tracking and alerts

| Item | Rule |
|---|---|
| Scheduler | **EventBridge rule invoking the API Lambda daily** (L2 checks only, no L3), **not** a GitHub cron, so alerts still fire if GitHub disables schedules (the 60-day inactivity case [D: S22 disabling]). Needs a new template resource and a handler branch for non-HTTP events (U25). Fallback: reuse a daily run of `check-secrets.yml`. |
| Checks | All L2 checks; IG refresh weekly (also writes the new token and `expires_at` [3.5]); GitHub workflow `state` and PAT expiry header; YouTube refresh; Cloudinary `ping` (daily, well under 500/h [D: S21]) |
| Expiry thresholds | IG token, GitHub PAT: Warning at <= 14 days, Invalid-soon alert at <= 3 days; IG refresh failure alerts immediately and repeatedly (a 60-day token dies if refresh keeps failing [D: S7]) |
| Alert channels | (1) Dashboard banner and card badge; (2) Telegram message to `TG_CHAT_ID` (pattern exists [R: check-secrets.yml:97-104]); (3) email if SMTP is configured; (4) `activity_log` event `config.check_failed` visible in Logs |
| Dedupe | Alert on state change; reminder at most every 24 h while still bad; "Resolved" message on recovery |
| Drift | A config version change since the last system test shows "System test out of date. Re-run." |

---

## 8. Requirements

### 8.1 Functional

**Storage and resolution (ST)**
- ST-1 The system shall store every non-bootstrap setting in `config_values`, secrets encrypted with AES-256-GCM under a DEK wrapped by `CONFIG_MASTER_KEY` (3.4).
- ST-2 `get_env` shall keep its signature and resolve per the precedence rules in 3.4, with a flag to flip precedence.
- ST-3 Writes shall carry a version for optimistic concurrency and shall be atomic with the audit row and check result.
- ST-4 The system shall provide `scripts/import_env_to_store.py` (dry-run lists names only) and shall never print values.
- ST-5 A canary decrypt shall run at start-up in Lambda and runner and report `key_mismatch`.
- ST-6 The Lambda cache TTL shall be <= 60 s and invalidated on writes; the Gemini client shall be rebuilt when the key changes (F6).

**Verification (VR)**
- VR-1 Each integration shall expose L1, L2 and (where defined) L3 checks returning the shared result shape (section 5).
- VR-2 Verify-before-save: a failed verification shall leave stored values unchanged.
- VR-3 `unknown` outcomes shall allow "Save anyway" with confirmation and automatic re-verification within 24 h.
- VR-4 No check shall publish, create queue items or spend generation quota without an explicit click.
- VR-5 All error messages shall come from a catalogue keyed by `code`, each with a guide link; raw provider bodies shall never be shown.
- VR-6 A redaction layer shall scrub known secret values and token patterns from logs, activity rows, Telegram notifications and API errors (F3).
- VR-7 The pipeline test shall execute stages P0-P11 per 6.11 and report each separately.
- VR-8 Cooldowns and rate limits in section 5 shall be enforced server-side.

**UI (UX)**
- UX-1 `/config` shall show status cards for every integration with the states in 7.2.
- UX-2 The wizard shall follow 7.3, persist progress, and allow skipping optional steps.
- UX-3 Secrets shall be write-only in the UI (no prefill, no reveal).
- UX-4 A paste cleaner and inline L1 validation shall exist on every field.
- UX-5 Every Invalid/Warning/Stale card shall have a primary fix action linking to the relevant guide step.
- UX-6 Verify & save semantics per 7.2.
- UX-7 A global Readiness banner shall show the predicates in 7.5 with the failing conditions.
- UX-8 The Generate page shall be disabled with a link to the failing card when not READY_TO_GENERATE.
- UX-9 The sidebar `Config` item shall become `ready: true` and show a dot while setup is incomplete or any card is Invalid.
- UX-10 Fields sourced from environment variables shall display "Env override" and explain the effect (3.4).

**Docs (DOC)**
- DOC-1 Guides per 7.4 with exact links, screenshots, time estimates and a "verified on" date.
- DOC-2 One troubleshooting page per verifier `code`.
- DOC-3 A glossary.
- DOC-4 In-context side sheet from each field.

**Health (HL)**
- HL-1 Daily L2 re-verification independent of GitHub (7.7), weekly IG refresh storing the new token and expiry.
- HL-2 Alerts per 7.7 with dedupe and resolve messages.
- HL-3 GitHub workflow `state` shall be checked and `disabled_*` surfaced with fix steps.

**Connect flows (CN, Phase 3)**
- CN-1 "Connect YouTube" shall run a Web OAuth flow with `access_type=offline` and `prompt=consent` [R: get_yt_token.py:33] and store the refresh token; scopes per OQ6.
- CN-2 "Connect Instagram" shall use Business Login (authorize, code exchange, short-to-long-lived exchange) [D: S10], never exposing the app secret to the browser.
- CN-3 OAuth `state` shall be bound to the session and single-use.

### 8.2 Non-functional

- NFR-1 L2 verification completes in <= 10 s for 95% of calls (Lambda timeout 30 s [R: template.yaml:71]).
- NFR-2 No additional paid infrastructure for the recommended option (EventBridge rule and the extra EventBridge invocations are within free allowances [U26 confirm]).
- NFR-3 Works with SQLite for tests and Postgres in production [R: README].
- NFR-4 Accessibility: status is never colour-only; forms are keyboard-operable; errors are announced.
- NFR-5 Mobile-friendly cards (sidebar already has a compact mode [R: app-shell.tsx:52]).

---

## 9. Risk register (task F)

L = likelihood, I = impact (H/M/L). **Mitigation status:** **V** = verified by repo code or official doc; **S** = needs a spike (id in section 13) before it can be trusted.

| ID | Risk | Category | L | I | Mitigation | Status |
|---|---|---|---|---|---|---|
| R-01 | Secret returned to the browser by a bug | Security | M | H | Write-only API; contract test with sentinel values over every `/api/config*` response (S1); no "last 4 chars" | V (design) |
| R-02 | DB breach reveals secrets | Security | L | H | AES-GCM + KEK held outside DB; S2 test | V |
| R-03 | Admin session theft lets attacker overwrite credentials (redirect posts) | Security | L | H | Existing CSRF/cookie hardening [R: README]; require password re-entry for Advanced/Google/PUBLISH_ENABLED; audit + Telegram notice on every credential change | V |
| R-04 | Verification endpoints abused as an open proxy/oracle (SSRF-like, key brute force) | Security | M | M | Admin-only, fixed provider hosts (no user-supplied URLs), per-user rate limit, cooldowns; SMTP test mail only to the admin | V (design) |
| R-05 | Secrets leak via exception text, logs, Telegram: `requests` errors include URLs; IG token is a query parameter; Telegram bot token is in the URL path | Security | **H** | H | Redaction filter + `redact()` wrapper on every logger, activity row and `notify`; replace `f"{e}"` patterns [R: publish.py:58, upload.py:47, main.py:336]; runner prints `::add-mask::`; sentinel test S3 | S (S6) |
| R-06 | Console mail driver writes OTP codes to logs/outbox in production | Security | M | H | Refuse `MAIL_DRIVER=console` when `COOKIE_SECURE=true`; show "Email not configured" card | V [R: mailer.py] |
| R-07 | Test endpoint spends money or posts publicly | Cost/Policy | M | H | Rules in section 5; IG `media_publish` never called; YouTube never uploads; Gemini generation only on click; test asserts via a recording fake (S8) | V (design) |
| R-08 | Token refreshed but another copy stale (refresh writes only GitHub secret) | Correctness | H today | H | Single store; refresh writes store [3.5] | V |
| R-09 | Master key differs between SSM and GitHub secret | Correctness | M | H | Canary at start-up in both; installer sets both from one generation; Readiness shows `key_mismatch` | V (design) |
| R-10 | Master key lost | Availability | L | H | Documented re-entry; one-time recovery-key display (OQ9) | S |
| R-11 | Partial config states (e.g. IG token set, id wrong; Telegram token set, chat empty) | UX | H | M | Multi-field verify as a unit; wizard auto-fill; Readiness lists exact missing field | V |
| R-12 | Cached settings/clients ignore changes (`lru_cache`, `_client`) | Correctness | H | M | Resolver TTL; rebuild Gemini client on key change; Google/auth settings stay guarded until dynamic | V [R: settings.py:39, llm.py:22] |
| R-13 | Race: two admins edit one integration; runner reads mid-edit | Race | L | M | Optimistic version -> 409; runs read a consistent value per run; run log records config version | V (design) |
| R-14 | Env wins over store during migration, so user edits "do nothing" | UX | H | M | "Env override" badge and explanation; flip precedence after burn-in | V (design) |
| R-15 | Migrating `.env` causes downtime or a bad cut-over | Ops | M | H | Additive tables; env-wins first; import dry-run; per-integration verify; keep old secrets until 1 day of clean slots; rollback = flag (3.8) | S (S11 rehearsal on a copy) |
| R-16 | Verification itself rate-limited by providers (Cloudinary Admin API 500/h free [D: S21]; Meta limits unknown; Telegram) | Quota | M | M | One Admin call per check, daily auto cadence, cooldowns; use Upload API for the heavier test | V (Cloudinary) / S (Meta, U27) |
| R-17 | Template defaults `PUBLISH_ENABLED=false`, `TELEGRAM_SYNC=false` mismatch code defaults; user thinks "ready" but nothing mirrors/publishes | Correctness | M | M | Readiness shows both flags explicitly with effect text; wizard end screen asks to set them | V [R] |
| R-18 | Misspelled legacy key (`COUDNARY_API_ENV_VAR`) copied into customers' systems | UX | L | L | Importer maps aliases to the canonical `CLOUDINARY_URL` only | V [R: config.py:26] |
| R-19 | Guides rot when Meta/Google/Cloudinary change their consoles | UX | **H** | M | "Verified on" stamp; link checker in CI (HEAD each official URL); quarterly review owner; "report outdated" button | S |
| R-20 | Owner's repo/IDs baked in (`hitesh2327/...`, bot id, fingerprints): customer's dashboard dispatches **the owner's** repo | Security/Correctness | **H** | H | Remove defaults, make `GITHUB_REPOSITORY` required (G8); remove hard-coded IDs from `check-secrets.yml` | V [R] |
| R-21 | Instagram API version retires (`v21.0`, reported sunset 2027-01-21 [2nd: ppc.land]) | Provider | M | H | Version in config; health check warns <= 90 days before sunset; confirm date (U5) | S |
| R-22 | `edge-tts` is an unofficial client of Microsoft's Edge read-aloud endpoint; terms for commercial use unclear; may rate-limit or break [2nd: S28] | Provider policy | M | H | Disclose to owner (OQ10); P4 detects failure; plan an Azure Speech provider switch; do not market as "no third-party dependency" | S (legal read) |
| R-23 | GitHub disables schedules: forks by default; public repos after 60 days without activity [D: S22 disabling] | Availability | M | H | Template repo; check workflow `state` (6.6); health check on EventBridge; cron-job.org as primary trigger [R: README] | V (rule) / S (does a template-generated repo count as a fork: U28) |
| R-24 | Editing `post_times_ist` in the UI desyncs workflow crons and cron-job.org | Correctness | H | M | Not editable until the workflow takes one frequent trigger and the code decides slots; show read-only with the sync warning | V [R: daily-generate.yml:18,110] |
| R-25 | YouTube refresh token dies at 7 days (Testing mode), 6 months unused, or >100 live tokens [D/2nd: S17,S18] | Token expiry | H | H | Wizard step "In production"; "unconfirmed until day 8" status; daily refresh keeps it active; clear reconnect | V (rule) / S (U15) |
| R-26 | Unverified YouTube project forces private uploads, user thinks public posting is broken | Provider policy | H | M | Show "effective privacy" and the audit explanation [D: S16] | V |
| R-27 | Gemini key regime changes (auth vs standard keys) break existing/new keys | Provider | M | H | No format enforcement; test with current key now; card warning (U1) | S (S1) |
| R-28 | Gemini free tier data-use and EEA/UK/CH terms surprise the customer | Policy | M | M | Notice at key entry [2nd: S5] | V (notice) |
| R-29 | Instagram personal (non-professional) account | UX | M | H | Check `account_type`; step 1 of the guide; clear message | S (U6) |
| R-30 | Telegram: concurrent `getUpdates` -> 409; chat-id detection steals button presses | Race | M | M | No-offset read, never advance offset, idle-only, 409 message [D: S20] | S (S9) |
| R-31 | Telegram webhook left set by another tool blocks approvals | Config | M | H | `getWebhookInfo` check + one-click remove [D: S20] | V |
| R-32 | Dangling Instagram containers from deep checks | Provider | L | L | They expire in 24 h [D: S13]; cooldown; opt-in | S (U7) |
| R-33 | Pipeline test consumes Actions minutes / is spammed | Cost | M | L | Single-flight, cooldown, per-day cap; private repo allowance 2,000 min [D: S22] | V |
| R-34 | Test assets or the test reel left in Cloudinary/Telegram | Hygiene | M | L | `finally` cleanup; random ids in `_selftest`/`_preflight` folders; test reel has no buttons | V (design) |
| R-35 | Neon cold start makes a check look like failure | UX | H | L | Retry + "waking up" message [D: S23] | V |
| R-36 | `unknown` mistaken for `invalid`, user rotates a good key | UX | M | M | Distinct status/colour; "Save anyway" only for unknown; auto re-verify | V (design) |
| R-37 | Lambda in no-VPC can reach SMTP? Port restrictions unknown | Provider | L | M | Test 587/465 from the deployed Lambda | S (U29) |
| R-38 | GitHub token over-scoped by the user (all repos, Secrets write) | Security | M | H | Guide demands one repo + Actions only; the check can warn if `GET /repos/...` shows broader reach (U30); no `GH_PAT` needed after 3.5 | S |
| R-39 | Concurrent migrations/revisions: new tables absent when Config opens | Ops | M | M | Step 0 shows "schema behind" with the fix; deploy runs `alembic upgrade head` before releasing the web build | V [R: infra/README.md] |
| R-40 | Zero-downtime of the scheduled 10:00/19:00 slots during cut-over | Ops | M | H | Do not flip precedence within 3 h of a slot; rehearsal | S |
| R-41 | Verification results go stale and false-green | UX | M | M | Show `last verified`; daily re-verify; config version binding | V |
| R-42 | `.env`, `data/outbox/` or logs committed/shared | Security | L | H | `.gitignore` check in CI; outbox only in dev | V (check) |

---

## 10. Acceptance criteria (Given / When / Then)

**Storage and security**
- AC-1 Given a stored secret, When any `/api/config*` endpoint is called by an admin, Then no response body, header or log line contains the secret or any part of it.
- AC-2 Given only a DB dump, When an attacker lacks `CONFIG_MASTER_KEY`, Then no secret can be decrypted.
- AC-3 Given a working Gemini key, When the admin saves a mistyped key, Then the save is rejected with a specific message and generation continues to work with the old key.
- AC-4 Given two admins editing the same integration, When both save, Then the second receives 409 and no value is lost silently.
- AC-5 Given a rotated master key, When rotation completes, Then every value still decrypts and the old key fails.

**Verification**
- AC-6 Given a valid Cloudinary URL, When Verify runs, Then `ping`, an upload, a public `HEAD` and a delete all succeed and no asset remains.
- AC-7 Given a Telegram token with a webhook set, When Verify runs, Then status is Invalid with "webhook blocks approvals" and a Remove-webhook button; after removal it becomes Valid.
- AC-8 Given a new bot and the user pressed Start, When "Detect my chat" runs while no poll job is active, Then the chat id fills in and `tg_offset` is unchanged.
- AC-9 Given an expired Instagram token, When Verify runs, Then status is Invalid with the "generate a new token" step and no publish call was made.
- AC-10 Given a valid IG token for another account than `IG_USER_ID`, When Verify runs, Then a mismatch message offers to use the detected id.
- AC-11 Given a YouTube refresh token whose consent screen is in Testing and issued 8 days ago, When Verify runs, Then the status says the token was rejected and points to "In production".
- AC-12 Given an unverified Google project, When settings are shown, Then "effective privacy: private until audited" is displayed regardless of `YT_PRIVACY`.
- AC-13 Given a GitHub token without Actions permission, When Verify runs, Then the message names the exact permission to add.
- AC-14 Given a workflow in `disabled_inactivity` state, When Verify runs, Then status is Warning/Invalid with the enable instructions.
- AC-15 Given any verification, When it runs, Then no Instagram `media_publish`, no YouTube `videos.insert`, no queue item and no Telegram message with buttons is produced (asserted by a recording fake).

**Pipeline test**
- AC-16 Given tier-1 config, When "Run system test" is clicked, Then a run is dispatched, each stage reports pass/fail/skipped, and a failed stage names the fix.
- AC-17 Given the system test passed, When any required value is edited, Then Readiness shows "System test out of date".
- AC-18 Given the test reel, When P5 runs, Then ffprobe confirms H.264+AAC, 1080x1920, correct duration, moov at front, and the MP4 is accepted by an Instagram REELS container (reaches `FINISHED`) without publishing.

**Readiness and journey**
- AC-19 Given all G1-G8 true, When the admin opens Generate and clicks Generate, Then the run does not fail with a configuration error (a missing or invalid-credential failure class).
- AC-20 Given any G condition false, When the admin opens Generate, Then Generate is disabled with a link to the failing card.
- AC-21 Given a fresh deployment, When the owner follows the wizard with the guides, Then tier 1 completes in <= 10 minutes median across 5 first-time testers [EST target; measured in S-UX].
- AC-22 Given an expiring token (<= 14 days), When the daily check runs, Then a Warning shows, one Telegram alert is sent, and no duplicate is sent within 24 h.
- AC-23 Given GitHub schedules are disabled, When the daily Lambda check runs, Then the alert still fires.

**Migration**
- AC-24 Given the existing env-based deployment, When the importer runs with `--apply`, Then all integrations verify green and scheduled slots continue uninterrupted; setting the precedence flag back to `env` restores the old behaviour within one run.
- AC-25 Given an env-sourced field, When shown, Then it is labelled "Env override".

**Docs**
- AC-26 Given any Invalid card, When "Fix" is clicked, Then the exact guide step opens in a side sheet with the official link, and every external link in the guides returns 200 in CI.

---

## 11. Phased build order

| Phase | Deliver | Depends on | Effort [EST] |
|---|---|---|---|
| **P0 Spikes** | S0-S12 (section 13); owner answers to OQ1, OQ6, OQ7 | - | 2-3 days |
| **P1 Foundation** | Redaction layer (R-05) first; `src/verify/*` refactor of `check_secrets.py`; `config_*` tables, crypto, resolver (env-wins), importer, audit events; remove owner defaults (R-20); Step-0 environment check | P0 | 6-8 days |
| **P2 Tier 1** | `/config` cards, Verify & save, paste cleaner, readiness banner, Gemini/Telegram (incl. detect)/Cloudinary/GitHub/DB verifiers, guides for those four, Generate gating | P1 | 6-8 days |
| **P3 System test** | `preflight.yml`, P0-P6, P11, report UI, config-version binding | P2 | 4-6 days |
| **P4 Publishing tier** | Instagram verifier + refresh into store, YouTube verifier, effective-privacy notices, P8/P9, guides, readiness for IG/YT | P3 | 5-7 days |
| **P5 Health** | EventBridge daily check, alerts (Telegram/email/banner), expiry tracking, `disabled_*` handling | P4 | 3-4 days |
| **P6 Connect** | Connect YouTube, Connect Instagram, one shared Google client, wizard polish | P4 | 5-7 days |
| **P7 Extras** | Email and Google sign-in cards, brand editor, precedence flip + remove old secrets, schedule decoupling, optional KMS key provider or OIDC option | P5 | 5-8 days |

Rule: **P1 redaction and P1 owner-default removal ship before anything that lets a customer enter a secret.**

---

## 12. Open questions for the owner (with recommended defaults)

| # | Question | Recommended default |
|---|---|---|
| OQ1 | Single-tenant deploy-per-customer, or one multi-tenant SaaS? (Multi-tenant needs per-tenant keys, tenant ids on every table, and Meta App Review/Business Verification for Advanced Access [D: S11a].) | **Single-tenant per customer** for v1 |
| OQ2 | Is a fully hosted "we create the AWS/Neon/GitHub for you" install in scope? (It removes tier 0, the biggest time sink.) | Yes for demos: one `deploy` command + a GitHub template repository |
| OQ3 | Recommend Option A (encrypted Postgres store)? Or do you prefer SSM-only (Option C)? | **A**, with C as the later AWS-native upgrade |
| OQ4 | Which tiers must be in the sold MVP? | Tiers 1-2 mandatory; YouTube optional |
| OQ5 | Customers use their own Meta app/Google project (no review needed) rather than yours? | Yes: it avoids App Review/Business Verification and the 100-user Google cap |
| OQ6 | Add `youtube.readonly` to the YouTube scope to verify the channel and show its name? (Changes the owner's existing consent.) | Yes, for new customers; keep the owner's current token working |
| OQ7 | Replace `get_yt_token.py` with in-dashboard Connect for customers? | Yes (Phase 6) |
| OQ8 | Should the dashboard be allowed to remove a Telegram webhook (mutation) on the user's click? | Yes, confirm dialog |
| OQ9 | Offer a one-time "recovery key" display at install? | Yes, with strong "store it in a password manager" copy |
| OQ10 | Accept `edge-tts` for sold product, or plan Azure Speech/another TTS? | Disclose and plan a provider switch; do not market it as a guaranteed dependency |
| OQ11 | Alert channels: Telegram + banner + email (if SMTP set)? | Yes |
| OQ12 | Should `PUBLISH_ENABLED` default to `false` until the system test passes, then auto-offer to enable? | Yes (safe-by-default) |
| OQ13 | Is the owner's own deployment migrated first as the pilot? | Yes, in the rehearsal S11 |
| OQ14 | Brand/slots editing from the dashboard: acceptable to defer until crons are decoupled? | Defer |

---

## 13. UNVERIFIED: must be tested before launch

Each item names the test that settles it. None of these is stated as fact anywhere above.

| ID | Unverified statement | Test / spike |
|---|---|---|
| U1 | Gemini key regime: a search summary says new AI Studio keys are "auth keys" and "Standard keys" will be rejected from **September 2026** (today is 2026-10-05). Unknown: whether the owner's current key and `google-genai` SDK are affected, the key format, and the auth header. | **S1:** read https://ai.google.dev/gemini-api/docs/api-key fully; run `models.list` + `countTokens` + one `generateContent` with a freshly created key and with the owner's key. Do not hard-code a prefix. |
| U2 | Whether a token from the App Dashboard "Generate token" is long-lived (60 days) or short-lived. Official summary says long-lived; a third-party says short-lived. | **S2:** generate one, call `GET /me`, wait 25 h, call refresh, read `expires_in`. Also look for any debug endpoint (U2b) giving scopes/expiry for Instagram-Login tokens. |
| U3 | Instagram token/app-secret formats and lengths. | Observe 3 real tokens; never hard-block on shape. |
| U4 | Whether Gemini `models.list` and `countTokens` consume rate-limit quota. | **S1:** hammer both with a free key and watch the AI Studio rate-limit page. |
| U5 | Meta Graph API v21.0 sunset date (reported 2027-01-21 by a secondary source). | **S3:** read https://developers.facebook.com/docs/graph-api/changelog/versions ; decide version policy. |
| U6 | Exact `account_type` values returned for Business vs Creator vs personal, and the error for a personal account. | **S2** with a personal account. |
| U7 | Whether `content_publishing_limit` requires the publish permission; the exact error for a token missing it; whether container creation needs that scope, appears anywhere visible, or counts toward quota. | **S4:** use a token with only the basic scope; create/abandon a container; check Instagram app and quota endpoint. |
| U8 | One Google Web client can serve both sign-in and YouTube with one consent screen in one pass. | **S5** |
| U9 | Telegram token exact format/length. | Treat as warn-only; collect samples. |
| U9b | YouTube credential prefixes (`.apps.googleusercontent.com`, `GOCSPX-`, `1//`) are stable. | Warn-only. |
| U10 | `cryptography` fits the Lambda image size/limits. | **S6:** build the image. |
| U11 | Exact host/path/POST-vs-GET of Google's tokeninfo and whether it returns the refresh-grant scope. | **S5** |
| U12 | cron-job.org cannot be verified from our side (no API relationship). | Guide-only; health check reads recent run times from GitHub instead (planned). |
| U13 | UX research for Buffer, Segment, Make, Twilio was not retrieved. | Not used as evidence. |
| U14 | `youtube.upload` alone cannot call `channels.list`; whether an upload-only token can delete a video; the reason string for "no channel". | **S7** |
| U15 | There is no API to detect a consent screen in Testing mode. | **S7:** attempt with a Testing-mode client and inspect any field; otherwise keep the "unconfirmed until day 8" logic. |
| U16 | No API exposes remaining YouTube quota. | **S7** (Cloud Quotas API check) |
| U17 | Reel spec details (moov at front, no edit lists, 300 MB, 23-60 fps) are quoted from a search excerpt of Meta's page. | **S0:** read the page; **P5** asserts against it and S8 proves with a real container. |
| U18 | Telegram `getUpdates` without `offset` neither confirms updates nor conflicts with a concurrent poll in our timing. | **S9:** real bot test with a pending button press. |
| U19 | Cloudinary exact status/body for bad key, bad cloud name, exhausted credits; delete behaviour. | **S8** |
| U20 | GitHub returns 404 vs 403 for a token lacking repo access; `x-accepted-github-permissions` usefulness. | **S10** |
| U21 | Google's own page for Gmail SMTP/app passwords (only third-party retrieved). | **S0** |
| U22 | Google token endpoint returns `invalid_client` vs `invalid_grant` as hypothesised for a bogus code. | **S5** |
| U23 | Whether `main.py generate --dry-run` calls Gemini. | Read `main.py`, run with a spy. |
| U24 | The Instagram-tester invitation must be accepted inside the Instagram app, and where. | **S2** |
| U25 | EventBridge -> Lambda container with a Mangum handler needs a non-HTTP branch; cold-start cost. | **S12** |
| U26 | EventBridge/Lambda daily invocation is inside free allowances. | AWS pricing pages (S0) |
| U27 | Meta rate limits on `/me` and `content_publishing_limit` for our cadence. | **S4** |
| U28 | Whether a repository created from a template counts as a fork for the scheduled-workflow rule; whether workflow runs count as "repository activity". | **S10** (create from template, check `state`) |
| U29 | Lambda egress to SMTP 587/465. | **S12** |
| U30 | Ability to detect an over-scoped fine-grained PAT from the API. | **S10** |
| S-UX | Setup times in 4.3 are estimates. | Moderated test, 5 first-time users, record time per step; adjust budget |
| S11 | Migration rehearsal on a copy of the owner's DB. | See R-15, R-40 |
| S0 | Re-read every `[D]` page in full; record date; confirm each console deep link. | Before P1 |

---

## 14. Sources

Only URLs that appeared in this session's search results are listed. Pages were confirmed at excerpt level (section 0.2); S0 re-reads each in full.

**Gemini**
- S1 Troubleshooting guide: https://ai.google.dev/gemini-api/docs/troubleshooting
- S2 Rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- S3 Models API (list): https://ai.google.dev/api/models
- S4 API keys: https://ai.google.dev/gemini-api/docs/api-key (also https://ai.google.dev/gemini-api/docs/generate-content/api-key)
- S5 Billing/terms: https://ai.google.dev/gemini-api/docs/billing ; secondary: https://simonwillison.net/2024/Oct/17/gemini-terms-of-service
- S6 Tokens: https://ai.google.dev/gemini-api/docs/tokens ; count tokens (Firebase): https://firebase.google.com/docs/ai-logic/count-tokens

**Instagram / Meta**
- S7 Refresh access token: https://developers.facebook.com/documentation/instagram-platform/reference/refresh_access_token
- S8 Content publishing (limit, quota endpoint): https://developers.facebook.com/documentation/instagram-platform/content-publishing
- S9 Get started, Instagram Login: https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/get-started
- S10 Business Login for Instagram: https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login
- S11a Platform overview and access levels: https://developers.facebook.com/documentation/instagram-platform/overview ; App Review: https://developers.facebook.com/docs/instagram-platform/app-review
- S11b (secondary) professional accounts only: https://postproxy.dev/blog/post-to-instagram-via-api/
- S12 Error handling: https://developers.facebook.com/docs/graph-api/guides/error-handling ; Instagram error codes: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/error-codes
- S13 IG container and media reference: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-container ; https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media
- S14 Graph API v21.0 changelog and versions: https://developers.facebook.com/docs/graph-api/changelog/version21.0/ ; https://developers.facebook.com/docs/graph-api/changelog/versions ; (secondary, sunset date) https://ppc.land/meta-releases-graph-api-v21-0-and-marketing-api-v21-0/

**Google / YouTube**
- S15 Quota cost: https://developers.google.com/youtube/v3/determine_quota_cost
- S16 videos.insert (unverified-project private rule): https://developers.google.com/youtube/v3/docs/videos/insert (mirror seen: https://developers.google.cn/youtube/v3/docs/videos/insert)
- S17 Manage app audience / publishing status: https://support.google.com/cloud/answer/15549945 ; (secondary, sensitive scope, unverified-app screen, 100-user cap) https://support.google.com/cloud/answer/7454865 and https://postproxy.dev/blog/youtube-upload-api-guide/ (S17b)
- S18 (secondary) refresh-token expiry, 6-month and 100-token rules: https://developers.google.com/health/setup ; https://www.unipile.com/es/token-de-actualizacion-de-google-oauth/
- S19 tokeninfo schema: https://googleapis.dev/nodejs/googleapis/latest/oauth2/interfaces/Schema$Tokeninfo.html
- S29 (secondary) Shorts length/aspect rules: https://shortsync.app/resources/youtube-shorts-upload-requirements-2026
- S30 redirect URI exact-match (forum/secondary): https://discuss.google.dev/t/getting-error-redirect-uri-mismatch-when-using-oauth/124351

**Telegram**
- S20 Bot API: https://core.telegram.org/bots/api ; (secondary, BotFather, chat id, 409) S20b/S20c: https://dev.to/simplr_sh/telegram-bot-creation-handbook-g5g , https://community.openhab.org/t/telegram-exception-getupdates-failed-with-error-code-409/149661

**Cloudinary**
- S21 API Keys / API environment variable and access control: https://cloudinary.com/documentation/product_environment_settings ; custom policies: https://cloudinary.com/documentation/permissions_custom_policies ; usage limits: https://cloudinary.com/documentation/developer_onboarding_faq_usage_limits ; pricing: https://cloudinary.com/documentation/pricing ; 100 MB video limit: https://support.cloudinary.com/hc/en-us/community/posts/360009789299-Not-able-to-upload-more-than-100MB-video-in-cloudinary

**GitHub**
- S22 Workflows REST: https://docs.github.com/en/rest/actions/workflows ; Actions secrets REST: https://docs.github.com/en/rest/actions/secrets ; PATs: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens ; token-expiration header: https://github.blog/changelog/2021-07-26-expiration-options-for-personal-access-tokens/ ; billing: https://docs.github.com/billing/managing-billing-for-your-products/managing-billing-for-github-actions ; disabling workflows (forks, 60-day inactivity; version seen): https://docs.github.com/en/enterprise-server@3.20/actions/using-workflows/disabling-and-enabling-a-workflow ; OIDC in AWS (version seen): https://docs.github.com/en/enterprise-server@3.18/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws

**Neon / AWS / OWASP**
- S23 Neon scale to zero: https://neon.com/docs/introduction/scale-to-zero ; connection latency: https://neon.tech/docs/connect/connection-latency
- S25 SSM SecureString + KMS: https://docs.aws.amazon.com/kms/latest/developerguide/services-parameter-store.html ; KMS pricing: https://aws.amazon.com/kms/pricing/ ; KMS cryptography/envelope: https://docs.aws.eu/kms/latest/developerguide/kms-cryptography.html
- S26 OWASP Secrets Management: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

**UX / other**
- S24 (secondary) Gmail SMTP: https://developer.nylas.com/docs/cookbook/email/gmail-smtp-settings.md ; n8n Gmail: https://docs.n8n.io/integrations/builtin/credentials/send-email/gmail.md
- S27a HubSpot connected apps: https://knowledge.hubspot.com/integrations/manage-your-connected-apps
- S27b Zapier connections: https://help.zapier.com/hc/en-us/articles/8496290788109-Manage-your-app-connections
- S27c n8n credentials files (test property): https://docs.n8n.io/integrations/creating-nodes/build/reference/credentials-files
- S27d Vercel sensitive env vars: https://vercel.com/docs/environment-variables/sensitive-environment-variables
- S27e Stripe go-live: https://docs.stripe.com/get-started/checklist/go-live
- S27f Progressive disclosure: https://ixdf.org/literature/topics/progressive-disclosure
- S27g Onboarding checklist guidance: https://www.userflow.com/blog/the-ultimate-product-onboarding-checklist
- S28 edge-tts: https://github.com/rany2/edge-tts ; Microsoft Q&A: https://learn.microsoft.com/en-us/answers/questions/2088770/are-opensource-edge-tts-free-for-commercial-use

**Repo files cited** (all under `D:\Code\codexone-automation\`): `src/config.py`, `src/llm.py`, `src/upload.py`, `src/publish.py`, `src/publish_youtube.py`, `src/approve_bot.py`, `src/refresh_token.py`, `src/actions.py`, `src/github_actions.py`, `src/activity.py`, `src/db/__init__.py`, `src/db/models.py`, `src/fetch_topics.py`, `scripts/check_secrets.py`, `scripts/has_work.py`, `get_yt_token.py`, `main.py`, `api/app/settings.py`, `api/app/mailer.py`, `api/app/routes/generate.py`, `api/lambda_handler.py`, `infra/template.yaml`, `infra/put_secrets.py`, `infra/deploy.sh`, `infra/README.md`, `.github/workflows/{daily-generate,poll-approvals,check-secrets,refresh-token}.yml`, `brand/config.yaml`, `README.md`, `CLAUDE.md`, `web/src/components/app-shell.tsx`, `docs/specs/generate-section.md`. `.env` was read for **key names only**; no value was read or copied.
