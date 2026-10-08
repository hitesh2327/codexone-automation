# QA report: backend (HEAD b7dacd8)

QA: Natasha Romanoff. Date: 2026-10-06. Scope: Profile/OTP, Logs, Generate, Dashboard, Config, migrations, go-live.
Status: COMPLETE (all 8 areas).

**Counts: Critical 0 | High 3 | Medium 9 | Low 13**

| ID | Sev | Title |
|---|---|---|
| QA-H-01 | High | Dashboard "Publish now" (inline mode) can double-publish to Instagram while a poll run publishes the same item |
| QA-H-02 | High | Values saved on the Config page are never readable in GitHub Actions (no CONFIG_MASTER_KEY in any workflow) while readiness says ready |
| QA-H-03 | High | Env ADMIN_PASSWORD becomes a working login again after the admin renames the account (or lands on another password-less account) |
| QA-M-01 | Medium | Lambda deploy never provisions CONFIG_MASTER_KEY / GITHUB_REPOSITORY / GITHUB_DISPATCH_TOKEN |
| QA-M-02 | Medium | Pre-merge code (rollback / re-run) fails at `alembic upgrade head` against d74f5a08b3e6 |
| QA-M-03 | Medium | A read-only Config GET creates the data key under whatever master key the process has; right key locked out |
| QA-M-04 | Medium | Account enumeration via /password/reset (422 vs 400) and /forgot + /reset timing |
| QA-M-05 | Medium | Behind CloudFront all users share the edge IP for rate limits: lock-out of everyone on an edge; per-container limits |
| QA-M-06 | Medium | Removing a Google user from the allowlist doesn't revoke a password they set, nor live sessions |
| QA-M-07 | Medium | No production guard on MAIL_DRIVER=console: reset codes in CloudWatch / disk |
| QA-M-08 | Medium | /api/posts unpaginated (79 MB at 50k posts; Lambda 6 MB cap in ~2.5 years); slots/check load every post |
| QA-M-09 | Medium | Dashboard overview 1.2-1.3 s p50 / 3.0 s p95 at scale (budget 600 ms) |
| QA-L-01..13 | Low | see sections (check-secrets vars, old code ignores targets, save_unverified, paste cleaner, login timing, reset DoS, FORCE flag, failed-login usernames in logs, username race 500, auto slot resolved twice, run-name matching, unknown status bricks q.load, test isolation) |

Environment used for every repro (never Neon, never a real provider):
- Scratch DB `qa_scratch` in the local docker container `codexone-automation-db-1` (port 5433); `codexone` DB untouched.
- `SP=<scratchpad>/qa`, `source $SP/env.sh` overrides every `.env` key with SENTINEL values (load_dotenv(override=False)
  never sees the real ones) and sets `DATABASE_URL=postgresql+psycopg://codexone:codexone@localhost:5433/qa_scratch`.
- `$SP/guard/sitecustomize.py` (on PYTHONPATH via env.sh) blocks every non-loopback DNS lookup / socket connect.
- Worktrees: `$SP/oldwt` = 8a8b240, `$SP/oldwt2` = 0a086ac (what remote main actually ran before the merge), `$SP/newwt` = b7dacd8
  (no `.env` in it, so nothing can write the real `.env`).

Disclosure: one early run of `$SP/new_flow.py` (before the socket guard existed) had a broken monkeypatch and made two
real HTTPS requests with SENTINEL credentials (graph.instagram.com answered "Invalid OAuth access token - Cannot parse
access token"; a YouTube upload attempt failed on DNS for the fake media host `x`). No real credential was sent; the
guard was installed immediately after and every later run reports `blocked: []` or explicitly blocked hosts.

---

## Area 1: Go-live compatibility

### 1.1 Old code against the fully migrated schema (d74f5a08b3e6)

Setup: `cd api && alembic upgrade head` (new code) on an empty `qa_scratch`: all 7 revisions applied, `alembic current` = `d74f5a08b3e6 (head)`.

| Check | Script / command | Result |
|---|---|---|
| Old (8a8b240) queue_store load/upsert/save, `claim_for_publish`, `record_posted` against new columns | `$SP/seed_new.py` (new code seeds 5 posts incl. `targets=["ig"]`, `yt_title`) then `cd $SP/oldwt && python $SP/old_flow.py` | OK. All 5 rows load; old `s.merge(Post(...))` leaves `group_id`, `targets`, `yt_title` intact (verified with `select id,status,group_id,targets,yt_title from posts`). |
| Old `approve_bot.poll` with fake Telegram (approve callback + reply feedback) | same | OK: `poll: [('20261006-r-aaa004', 'approved')]`, offset saved `{'offset': 102}` in `settings`. |
| Old `expire_stale` | same | OK: 40h-old pending -> `expired`. |
| Old `publish_due` with fake IG/YT publishers | same | OK: 4 items published, `posted_topics` 4 rows. |
| New code `main.py poll` end-to-end (fake Telegram, fake publishers, guard on) | `cd $SP/newwt && python $SP/new_flow.py` | OK: rc 0, `targets=["ig"]` reel published only to IG, activity rows written (`post.approved`, `post.feedback`, `post.expired`, `post.published` x5), `blocked: []`. |
| New `src.refresh_token` with the refresh workflow's exact deps (`pip install python-dotenv PyYAML requests pydantic`, no sqlalchemy/cryptography) | `$SP/venv_min`, `HTTPS_PROXY=http://127.0.0.1:9 IG_ACCESS_TOKEN=SENTINEL_sk_live_123456 python -m src.refresh_token` in newwt | Imports fine; error text shows `access_token=[REDACTED]`. No finding. |
| Lambda image builds and serves | `docker build -f api/Dockerfile.lambda -t qa-api .` (1.33 GB), run with RIE, `$SP/lam.py`, `$SP/lam2.py` | health/login/me/profile/config/config readiness/schema/dashboard overview/generate config+slots+jobs/logs/posts all 200; request without `X-Origin-Verify` -> 403. |

### 1.2 Workflow / infra trace against the new code

| Workflow / component | New requirement | Present? | Effect on next scheduled run |
|---|---|---|---|
| poll-approvals.yml (unchanged) | `main.py poll` now also calls `activity.prune()`, `generation.expire_stuck()`, `generation.prune()`; tables exist after `alembic upgrade head` in the job | yes | Works (proved by `$SP/new_flow.py`). |
| daily-generate.yml | `GITHUB_RUN_ID`/`GITHUB_REPOSITORY` (Actions sets both), `job-end` step, `alembic upgrade head` | yes | Works for cron. Dashboard-dispatched runs need the Lambda to have `GITHUB_DISPATCH_TOKEN` + `GITHUB_REPOSITORY` (see QA-M-01). |
| refresh-token.yml | `src.redact` (stdlib) | yes | Works (venv_min repro above). |
| check-secrets.yml | `vars.EXPECTED_BOT_ID`, `vars.EXPECTED_IG_ID`, `vars.EXPECTED_FP_*` (repository variables) | unknown (cannot read repo settings) | If the variables were not created, every identity/fingerprint comparison is silently skipped (see QA-L-01). `gh_pat` needs `GITHUB_REPOSITORY`: set by Actions, fine. |
| All workflows | `CONFIG_MASTER_KEY` (config_store.py docstring: "both get CONFIG_MASTER_KEY") | NO, in no workflow env block | Nothing breaks today (env wins), but any value saved on the Config page is invisible to Actions (QA-H-02). |
| Lambda (template.yaml + put_secrets.py) | `CONFIG_MASTER_KEY`, `GITHUB_REPOSITORY`, `GITHUB_DISPATCH_TOKEN` | NOT in put_secrets.py REQUIRED/OPTIONAL; README step 4 mentions only the token | Config page cannot save any secret; readiness G1 reports "CONFIG_MASTER_KEY isn't set" (observed via `/api/config/readiness` on the RIE); Generate page reports `dispatch_configured:false`; publish-now / regenerate dispatch silently no-op (QA-M-01). |

Lambda cold start (RIE, image above): `INIT REPORT durationMs: 3779.97` + first invoke 366 ms (lifespan `sync_admin`).
Pure import of `api.lambda_handler` inside the image: 2076 / 1588 / 1606 ms (3 runs); top self-times: `api.app.security`
297 ms (bcrypt dummy hash at import), `google.genai.types` 200 ms (pulled in by routes.generate -> approve_bot -> gen_content -> llm).
RIE runs with 3008 MB; production is 1024 MB (less CPU), so expect a slower real cold start. Importing the app also
performs a config-store DB lookup (`WARNING config store unavailable (OperationalError)` printed at import when the DB is unreachable).

### Findings (Area 1)

**QA-H-01 (High) Dashboard "Publish now" can double-publish to Instagram while a poll run publishes the same item (inline mode)**
- Area: Go-live / publishing. Files: `src/actions.py:180-194` (`start_publish_now` sets `status="publishing"` with a plain `q.upsert`, no `claim_for_publish`), `src/publish.py:230-233` (`publish_item` now accepts `status=="publishing"` and then skips the claim: `if item.status != "publishing" and not q.claim_for_publish(...)`).
- Repro: `cd $SP/newwt && python $SP/race_publish.py dp 0.4` (approved carousel whose slot has passed; thread A = dashboard `start_publish_now` + `finish_publish`, with `approve_bot.mark_decided` taking 0.4 s like a real Telegram edit when TELEGRAM_SYNC=true; thread B = `publish.publish_due()` 0.1 s later).
- Observed (2/2 runs): `IG publish calls: [('ig', 'race-1', 'poll'), ('ig', 'race-1', 'dash1')]` -> two Instagram posts. Without the Telegram latency (`dp` without the 0.4) the window is narrower and the race was not hit in 3 runs.
- Expected: exactly one publisher (the guarantee commit e4aa587 added). The dashboard path must claim with the same compare-and-set (`approved -> publishing` WHERE status='approved') and `publish_item` must not treat an unclaimed `publishing` as permission.
- Same pattern: `start_retry` (`src/actions.py:213-214`) flips a `failed` item to `publishing` with a plain upsert while `publish_due` may be retrying it.
- Impact: production Lambda uses `PUBLISH_VIA=dispatch` (not affected); every docker-compose / self-hosted install (the default `PUBLISH_VIA=inline`), i.e. what customers would run, is affected. Duplicate public posts.
- Fix: `start_publish_now`/`start_retry`: `q.claim_for_publish(item_id, from_status=...)` returning False -> 409; remove `"publishing"` from the "skip claim" path or pass an explicit `claimed=True` token from the caller that claimed.

**QA-M-01 (Medium) Lambda deployment never receives CONFIG_MASTER_KEY / GITHUB_REPOSITORY / GITHUB_DISPATCH_TOKEN**
- Area: Go-live / infra. Files: `infra/put_secrets.py:24-28`, `infra/README.md` step 4, `src/github_actions.py:55`, `src/actions.py:239-244`.
- Repro: read `put_secrets.py` REQUIRED/OPTIONAL lists (none of the three names); RIE run without them: `GET /api/config/readiness` -> `"ready_to_generate":false ... "CONFIG_MASTER_KEY isn't set"`; `GET /api/generate/config` -> `"dispatch_configured":false`.
- Observed vs expected: after following the documented deploy (including README step 4, which adds only the token) the Generate page and dashboard dispatch stay disabled because `GITHUB_REPOSITORY` has no default any more; the Config page cannot store secrets. Expected: the deploy script/README list every runtime variable the new code needs.
- Impact: production dashboard features silently off (`trigger_pipeline_run` logs at INFO and returns False: regenerate/publish-now wait for the next cron poll).
- Fix: add the three names to `put_secrets.py` OPTIONAL (or generate CONFIG_MASTER_KEY), document them, and surface "dispatch not configured" as a warning in the UI response.

**QA-H-02 (High) Values saved on the Config page are never available to GitHub Actions (no CONFIG_MASTER_KEY in any workflow)**
- Area: Go-live / Config. Files: `.github/workflows/daily-generate.yml:58-66`, `poll-approvals.yml` env, `src/config_store.py:2` (docstring promises both runtimes get the key), `src/config.py:44-53` (`_from_store` swallows every error and returns None).
- Repro: `grep -n CONFIG_MASTER_KEY .github/workflows/*.yml` -> no match. With a Gemini key saved only in the store (scratch DB), `GITHUB_ACTIONS=true python -c "from src.config import get_env; get_env('GEMINI_API_KEY')"` in `$SP/newwt`: with CONFIG_MASTER_KEY -> `value from store, len 27`; without it (what every workflow has) -> `MissingSecretError Missing required setting 'GEMINI_API_KEY'`. `$SP/crypto.py` step 3 shows the same for missing/invalid keys.
- Impact: today none (env secrets still exist, env wins). For a customer who configures through the Config page (the product's onboarding path), generation and publishing fail at the first scheduled run while the Config page/readiness show everything "valid". Severity High because the readiness check tells the customer they are ready when the runner cannot read a single stored value.
- Fix: add `CONFIG_MASTER_KEY: ${{ secrets.CONFIG_MASTER_KEY }}` to the env of daily-generate, poll-approvals (and refresh-token if IG token moves to the store); make readiness include "runner has the key" (e.g. a check written by the runner).

**QA-M-02 (Medium) Rollback / re-run of pre-merge workflow code fails at `alembic upgrade head`**
- Area: Go-live. Repro: `cd $SP/oldwt/api && alembic upgrade head` and `cd $SP/oldwt2/api && alembic upgrade head` against the d74f5a08b3e6 DB.
- Observed (both): `FAILED: Can't locate revision identified by 'd74f5a08b3e6'`. The step fails, so `main.py poll` / `generate` never run.
- Expected: commit 6e8b79c pushed a41/b52/c63 ahead of the code "so CI's alembic upgrade head already knows these revisions"; d74f5a08b3e6 was applied to Neon but never pushed ahead the same way. Any "Re-run jobs" of a run created before the merge (Actions re-runs use the original SHA) or a revert to 0a086ac breaks every poll/generate run, i.e. approved posts stop publishing.
- Fix: for rollback safety keep a tiny "stub" revision policy (push migrations before code), or make the workflow step tolerate an unknown-but-newer DB revision (`alembic current` check, skip upgrade when the DB is ahead).

**QA-L-01 (Low) check-secrets identity/fingerprint checks silently disabled unless repository variables exist**
- File: `.github/workflows/check-secrets.yml:21-22,67,74,81`. Hard-coded expectations replaced by `vars.*`; unset variable -> empty string -> comparison skipped with no warning. Fix: print "SKIPPED: EXPECTED_x not set" so the step log shows it.

**QA-L-02 (Low) Old code ignores `targets` (relevant only on rollback)**
- Repro: `$SP/old_flow.py`: reel seeded by new code with `targets=["ig"]` -> old `publish_due` published it to IG **and** YT (`20261006-r-aaa001 published {'ig': 'published', 'yt': 'published'}`).

---

## Area 2: Config (customer secrets)

### Evidence

| Check | Script | Result |
|---|---|---|
| Secret leak sweep: SENTINEL Gemini key, Telegram token, Cloudinary secret, GitHub PAT through save (with `export NAME="..."` paste noise), failing verify where the fake provider echoes URL+headers+auth back in body and headers, network exceptions whose text holds URL/headers/basic-auth, a verifier crash whose exception holds the values, detect-chat, delete-webhook; then GET /api/config, readiness, every history, /api/logs, schema, dashboard overview, generate config | `cd $SP/newwt && python $SP/leak.py` | `any leak: False`. Searched full value, value core, last 5, last 8 and middle 6 chars in: every response body + headers, captured root log, `logs/*.log` files, `activity_log`, `config_checks`, `config_values`, `config_meta`, `config_keys`, `generation_jobs`. Only fingerprints exposed: 8 hex (`"4aa87cbc"`, ...). No length/prefix fields. Provider calls only to the 5 fixed hosts. Config GETs send `Cache-Control: no-store`, no ETag. |
| CLI never prints values | `python -m src.verify all`, `all --json`, `gemini --depth deep`, `python -m src.config_store status` with SENTINEL env | grep for SENTINEL/sk_live/token fragments in the outputs: no match. |
| Nonce uniqueness | `$SP/crypto.py` step 1 | 300 saves -> 300 distinct 12-byte nonces. |
| GCM tamper detection | step 2 | bit flip -> `value None, error database.key_mismatch`, get_env -> None; ciphertext moved to another name -> rejected (AAD binds name+version). |
| Wrong / missing / invalid / 16-byte key | step 3 | snapshot value None, canary and save refuse with `key_mismatch` / `master_key_missing` / `master_key_invalid`. |
| Rotation round trip | step 4 | K1->K2 re-wrap: value readable under K2, canary ok; old key now `key_mismatch`; rotating again with the stale key refused. |
| Half-written multi-field save | step 5 | exception on the 2nd value -> transaction rolled back, only the pre-existing row remains. |
| Concurrency on save (`expected`) | step 6 | 8 parallel saves expecting v1 -> 1 ok, 7 conflict; 8 parallel first-time saves -> 1 ok, 7 conflict (no IntegrityError leak). |
| Never overwrite a working value with a failed one | `$SP/cfg_semantics.py` | rejected key -> 422 `verify_failed`, fingerprint/version unchanged, get_env still the good key. Provider 503 -> 409 `verify_unknown`. |
| Stale `expected` | same | 409 `conflict`. |
| env-wins vs store | same | env set + store saved: field `source=env, conflict=True`; readiness G2 "Changed since it was last verified", G7 fails with the conflict: honest. |
| SSRF / host injection | `$SP/ssrf.py` (fake HTTP records every URL) | 18 Cloudinary cloud-name payloads (169.254.169.254, localhost, 127.0.0.1:8080, `..`, `%2F`, `#@`, `?x=@`, `@` stacking, backslash, IDN, `[::1]`, ideographic dot) -> either `cloudinary.format` (no request) or a request to `api.cloudinary.com/v1_1/<[A-Za-z0-9_-]+>/ping` only. 18 GitHub repo payloads -> `repo_format` or `api.github.com/repos/<quoted>/<quoted>`. 10 Telegram token/chat payloads -> `token_format`/`chat_format` or `api.telegram.org/bot<token>/getMe`. 9 Gemini model payloads -> `model_format` or the fixed Google host. Redirects disabled (`allow_redirects=False`), upload `secure_url` restricted to `*.cloudinary.com` without userinfo. No SSRF found. |

### Findings (Area 2)

**QA-M-03 (Medium) A read-only GET of the Config page creates the data key under whatever master key the process has; the right key is then locked out**
- Files: `src/config_store.py:349-359` (`fingerprint()` calls `_load_dek(..., create=True)`), called from `config_status.values_fp`/`field_state` on every `GET /api/config`, `GET /api/config/readiness`, dashboard/generate pages.
- Repro: `$SP/crypto.py` step 3b: empty store, process with key K2 calls `fingerprint("anything")` -> `config_keys` now has 1 row (wrapped under K2); the real key K1 then gets `check_canary -> database.key_mismatch` and `save -> database.key_mismatch`.
- Expected: reads never create key material; only the first save (an explicit, authenticated write) creates the DEK.
- Impact: any process pointed at the shared DB with a different/typo'd key that merely renders the Config page (a staging Lambda, a local dev API with `.env` pointing at Neon, a GitHub job running `python -m src.verify`) permanently claims the store; the production admin then cannot save any secret, and the UI's remedy ("re-enter the values") cannot work. Recovery requires manual SQL (`delete from config_keys`).
- Fix: `create=False` in `fingerprint()`/`values_fp()` (return None when no DEK); create the DEK only in `save()`.

**QA-L-03 (Low) "Save unverified" lets a wrong key replace a verified one whenever the provider is rate-limiting**
- Repro: `$SP/cfg_semantics.py`: verified key stored; provider answers 429 -> verify of a wrong-but-well-formed key returns `unknown`; with `save_unverified: true` the wrong key replaced the good one (`fingerprint f1edfece -> c8e7576a`, `get_env -> SENTINEL_unverified_abcdef`).
- File: `api/app/routes/config.py:223-225`. Spec intent is an explicit opt-in, so Low; suggest keeping the previous verified value as `previous` or refusing `save_unverified` when the current value has a valid check.

**QA-L-04 (Low) Paste cleaner misses common paste shapes**
- `clean_value("‘SENTINEL_smart’")` keeps the typographic quotes; `git@github.com:o/n.git` and `https://github.com/o/n/tree/main` are not turned into `owner/name` (both then fail format, so no wrong value is stored). File `src/verify/base.py:297-333`. NFC normalisation also rewrites a secret containing a combining character (`'é' -> 'é'`), changing the stored value (theoretical for API tokens).

### Verifier assumptions not backed by cited docs (from reading src/verify/*)
- Telegram `404` for a malformed token is "observed (U9)", not documented (`telegram.py:44`); token length >= 20 after the colon is a guess (`TOKEN_RE`, comment says "length is not documented").
- Telegram `getUpdates` without `offset` "confirms nothing": documented; but calling it concurrently with the poll job's `getUpdates` can return 409 to the *poll job* (the API documents only one active getUpdates consumer). `detect_chats` does not coordinate with the poll.
- Cloudinary: "HTML responses instead of JSON typically indicates an authentication issue" (quoted); Upload API "not rate-limited per the docs" for the self-test upload; the self-test upload consumes storage/transform credits on every live verify (not documented as free).
- GitHub: `GitHub-Authentication-Token-Expiration` header format parsed with two guessed formats; classic-token prefix rule from "GitHub's token formats" (documented).
- Gemini: classification of `400 + "api key" in message` as rejected and `"per day"/"daily"` text matching for quota are heuristics over free-text messages, not documented contracts.
- Database: `"-pooler."` in host as the Neon pooler marker is a naming convention, not an API contract; migration-head check reports `schema_behind` even when the DB is *ahead* of the app (rollback case, see QA-M-02).

---

## Area 3: Auth / sessions / OTP / reset / email

Live API for this area: my own uvicorn on :8011 (`$SP/api8011.log`, scratch DB, `MAIL_DRIVER=console`, `MAIL_OUTBOX_DIR=$SP/outbox`) and the Lambda image under RIE on :9011.

### Evidence (no finding)

| Check | Script | Result |
|---|---|---|
| CSRF on every non-GET route (from `app.openapi()`: 26 routes + catch-all) | `cd $SP/newwt && python $SP/csrf.py` | every protected write: no header -> 403, wrong token -> 403, no cookie -> 401. Catch-all `/api/{path}` -> 404. Public writes: login (JSON-only, 415 otherwise), forgot, reset. |
| Cookie flags | same + RIE login | local: `HttpOnly; Path=/; SameSite=lax`; Lambda (`COOKIE_SECURE=true`): `__Host-cx_session ... HttpOnly; Secure; SameSite=lax`. |
| token_version | same | two sessions; `/profile/sessions/revoke` from A -> A 200, B 401; logout -> A 401 (all sessions; documented). Password change/reset bump it (`$SP/sync_admin.py` shows tv increments). |
| OTP 5-try cap under 40 parallel guesses (identifier case/whitespace variants) | `python $SP/otp_race.py` | try-limiter key normalises case/whitespace (`strip().lower()`): 12 evaluated (400), 28 -> 429; the right code sent last got 429; row `attempts=5, used`. Cap held; no lost update observed at 40-way concurrency on Postgres. |
| OTP replay / cross-user / cross-purpose | code read `api/app/otp.py:42-75` | digest binds user_id + purpose + email; `used_at` set on success; a new code retires older ones. |
| Email header / HTML injection | code read; `name` normalised by `" ".join(split())` | `To` comes from `EMAIL_RE` (no whitespace/CRLF, exactly one `@`), subject fixed, name/handle/headline `html.escape`d in the HTML part. |
| X-Forwarded-For spoofing | RIE `$SP/lam.py` | ignored: the app keys on `requestContext.http.sourceIp` (see QA-M-05 for the consequence). |
| SMTP failure text | code read `api/app/mailer.py:106-123` | MailError messages are fixed strings; credentials never in them. Live SMTP-down test not run (no local SMTP server). |

### Findings (Area 3)

**QA-H-03 (High) The env ADMIN_PASSWORD comes back as a working login after the admin renames the account (and can be planted on another account)**
- File: `api/app/main.py:40-56` (`sync_admin` looks the admin up by `ADMIN_USERNAME` only).
- Repro: `cd $SP/newwt && python $SP/sync_admin.py`:
  - step 3: admin renames `qaadmin` -> `boss` and changes the password; next start-up (every Lambda cold start): users = `[(1,'boss',...), (2,'qaadmin',...,token_version 0)]`; `login qaadmin/ENV password -> 200`.
  - step 4: a Google-only account (no password) whose username is `qaadmin` gets the env password on the next start: `env pw login -> 200` into `google.user@example.com`'s account.
- Expected (docstring): "the env password only seeds the account ... a restart never overwrites it". Observed: the original password silently becomes valid again (a new admin account) after a rename; changing the password gives a false sense of revocation.
- Impact: production (Lambda cold starts happen many times a day): anyone who ever saw the initial ADMIN_PASSWORD (installer, vendor, `.env`, SSM reader) regains admin access. For a sold product the vendor/installer credential survives customer hand-over.
- Fix: seed once (e.g. `settings['admin_seeded']` or only when `users` is empty); never set a password on an existing password-less account unless it is the seeded admin id; make FORCE one-shot.

**QA-M-04 (Medium) Account enumeration through /api/auth/password/reset and /forgot (status code and timing)**
- Files: `api/app/routes/recovery.py:94-103` (strength is checked and reported with 422 only for real accounts; unknown ones run `burn_time()` and get 400), `recovery.py:66-75`.
- Repro (`$SP/otp_race.py` part 3 and a curl loop):
  - `/reset` with `new_password:"a"`: `qaadmin -> 422 12ms 'Choose a stronger password...'`; `nosuchuser -> 400 296ms`; `nobody@example.com -> 400 295ms`.
  - `/reset` with a strong password: known account 4 ms vs unknown 286 ms.
  - `/forgot`: `victim@example.com 200 0.014s`, `qaadmin 200 0.028s` vs `nobody@example.com 200 0.289s`, `nosuchuser 200 0.286s` (3 rounds, consistent). `burn_time()` makes the unknown path slow: the opposite of equalising.
- Expected: the module docstring promises /forgot "answers the same way whether or not an account matches". Impact: confirms admin usernames/emails for phishing and targeted guessing.
- Fix: in /reset check the code before password strength (or answer 400 for both); do equal work on both branches (no bcrypt-only branch for unknown users); send mail in a background task and answer after a fixed delay.

**QA-M-05 (Medium) Behind CloudFront all visitors of an edge share one rate-limit IP: 20 bad logins lock everyone on that edge out; limits are per Lambda container**
- Files: `api/app/routes/auth.py:79-81`, `recovery.py:42-43` (`request.client.host`), `api/app/ratelimit.py` (in-memory).
- Repro (RIE, `$SP/lam.py`, Function-URL events with `sourceIp=130.176.1.1` as CloudFront would present): 20 failed logins for `spray0..19` with `X-Forwarded-For: 198.51.100.66`, then the real admin with the correct password from viewer `203.0.113.200`: `429 "Too many failed attempts. Try again in 15 min."`. App log: `failed login for 'spray19' from 130.176.1.1`.
- Impact (production): an attacker reaching the same edge can keep the admin locked out (renewable every 15 min); the spray limit is shared by all users instead of per attacker; logged IPs are CloudFront's. Each warm Lambda container keeps its own counters, so effective limits multiply with concurrency.
- Fix: derive the viewer IP from `CloudFront-Viewer-Address` (added by an origin request policy), trusted only when `X-Origin-Verify` matched; keep limiter state in Postgres; do not let an IP-wide lock block a correct password indefinitely (per-account back-off).

**QA-M-06 (Medium) Removing a Google user from ALLOWED_GOOGLE_EMAILS does not revoke access once they set a password**
- Repro: `python $SP/google_gap.py`: allowlisted Google-only user -> `/profile/password/otp` 200 -> `/profile/password` with the emailed code 200 -> allowlist changed to someone else -> `email+password login: 200 qa@example.com`. Existing sessions also stay valid (`deps.current_user` never consults the allowlist, no token_version bump).
- Files: `api/app/routes/auth.py:73-107`, `api/app/deps.py:22-33`.
- Impact: production access control; the only documented way to remove a dashboard user leaves a working password and live 12 h sessions.
- Fix: for Google-origin accounts require `email in allowed_google_emails` at password login and in `current_user`, or add an explicit disable (`is_active=false`).

**QA-M-07 (Medium) No production guard on MAIL_DRIVER=console: password-reset codes go to CloudWatch and disk**
- Files: `api/app/mailer.py:46-63,140-149` (console is the default whenever SMTP_HOST/SMTP_USER are unset; nothing checks COOKIE_SECURE/SSM_PREFIX).
- Repro: Lambda RIE (`COOKIE_SECURE=true`, `ORIGIN_VERIFY` set, no SMTP vars) `POST /api/auth/password/forgot {"identifier":"qa@example.com"}` -> 200 "a 6-digit code is on its way"; `docker logs qa-lambda` contains `[mail:console] To: qa@example.com / Subject: Your password reset code / <the 6 digits>`; `/tmp/data/outbox/latest.txt` holds it as well.
- Impact: any production deployment without SMTP (put_secrets.py marks SMTP optional) writes working reset codes into CloudWatch (14-day retention): log readers can take over the admin account. The user is told an email was sent.
- Fix: refuse the console driver when `COOKIE_SECURE=true` or `SSM_PREFIX` is set unless explicitly configured; never log the code; tell signed-in users "email is not configured".

**QA-L-05 (Low) Login timing reveals Google-only and disabled accounts**
- Repro `$SP/google_gap.py`: wrong password for `googleonly@example.com` 20/13 ms vs password account 308/313 ms vs unknown 305/297 ms. File `api/app/routes/auth.py:94-95` (`is_active and verify_password(...)` short-circuits; `verify_password` returns before bcrypt when there is no hash). Fix: always run bcrypt against a dummy hash.

**QA-L-06 (Low) A third party can keep a victim's reset code invalid / lock the victim's reset for 15 min**
- `otp.issue` retires the live code on every new request (after the 60 s cooldown); `send:{ident}` (4/15 min) and `try:{ident}` (12/15 min) are keyed on the identifier only. Repro `$SP/otp_race.py` part 2: after another party's guesses the owner's correct code gets `429 Too many attempts. Try again in 14 min.` Fix: per (identifier, client) limits with a global per-account cap.

**QA-L-07 (Low) ADMIN_PASSWORD_FORCE left on silently reverts the user's password on cold starts**
- Repro `$SP/sync_admin.py` step 2: after a profile password change, a start with FORCE=true: `env pw -> 200, new pw -> 401`, token_version bumped (everyone signed out). On Lambda this happens at arbitrary cold starts. Fix: one-shot marker, or a WARNING every start while set.

**QA-L-08 (Low) Failed-login usernames (possibly a password typed in the username box) are written to the application log**
- `api/app/routes/auth.py:98` (`log.warning("failed login for %r from %s", body.username, ip)`) -> CloudWatch (RIE: `failed login for 'spray19' from 130.176.1.1`). The activity log avoids this; the app log does not.

---

## Area 4: Profile

Script: `$SP/profile_probe.py` against my uvicorn on :8011 (two real accounts: `boss` password admin, `qa@example.com` Google-origin with a password).

### Evidence (no finding)

| Check | Result |
|---|---|
| Avatar size limits | 100-byte JPEG 200; Content-Length 500 KB -> 413 before reading; chunked body without Content-Length (1 MB and 300 MB runs) -> 413, server RSS 139 MB before / 137 MB after the 300 MB run (peak not sampled). Lambda caps request payloads at 6 MB anyway. |
| Polyglot / SVG | `\xff\xd8\xff\xe0<html><script>...` accepted (magic bytes only) but served as `content-type: image/jpeg` + `x-content-type-options: nosniff`; SVG -> 415. Not executable in a browser. |
| Caching | `GET /api/profile/avatar`: `cache-control: private, max-age=86400` (overrides the `/api/*` no-store default, intended: URL carries `?v=`); CloudFront `/api/*` uses CachingDisabled + AllViewerExceptHostHeader (`infra/template.yaml:178-183`), so no shared-cache exposure. |
| IDOR | no profile route takes a user id; every route uses the session user (`_user(ses, cu)`); unauthenticated -> 401; the second account's GET returns its own (404 "No picture"). |
| Case / Unicode usernames | `BOSS2` stored as `boss2`; Cyrillic `bоss` -> 422 (`USERNAME_RE` is ASCII). |
| Header/CRLF/path payloads | phone `+1\r\n2` -> 422; timezone `../../etc/passwd` -> 422; `Asia/Kolkata\x00` -> 422. |
| Stored XSS | `<img src=x onerror=alert(1)>` stored raw in name/job title/bio (200); `grep dangerouslySetInnerHTML|innerHTML|document.write web/src` -> no matches (React escapes); the email template escapes `name`; activity rows use username/email, not name. No sink found. |

### Findings (Area 4)

**QA-L-09 (Low) Concurrent username (and email) changes to the same value return 500**
- Repro: `profile_probe.py` step 4 (two accounts PATCH `/api/profile {"username": "raceN"}` at the same time), 3/3 runs: `[500, 200]`; `$SP/api8011.log` shows `psycopg.errors.UniqueViolation ... users_username_key`.
- Files: `api/app/routes/profile.py:131-138` (check-then-write without catching IntegrityError); same pattern in `change_email` (`profile.py:255-262`).
- Expected 409 "That username is taken". Impact: cosmetic / log noise; uniqueness itself holds (DB constraint).

---

## Area 5: Generate

### Evidence (no finding)

| Check | Script / evidence | Result |
|---|---|---|
| Auth / CSRF | `$SP/csrf.py` | `POST /api/generate`: no CSRF 403, bad CSRF 403, no cookie 401. Router has `Depends(require_admin)` (= signed in). |
| Workflow input injection (read the YAML myself: `.github/workflows/daily-generate.yml:83-116`) | code read | every user-typed input (`slot`, `category`, `topic`, `source_url`, `request_id`, flags) reaches the shell only as `env:` variables, used quoted inside a bash array (`ARGS+=(--topic "$IN_TOPIC")`) and passed as one argv element; no `${{ inputs.* }}` inside any `run:` block (the `if:` expressions and `run-name` are not shell). `main.py:_generate_input_error` re-validates slot/category/topic/source_url in the runner. API-side: category enum, `clean_topic` (control chars rejected, 5-120 chars), `clean_source_url` (https, public host, no userinfo, no spaces). Dash-leading topics with spaces (`-5 ways ...`, `--force rebuild of caches`) reach `main.py generate` as values (run stopped only at the blocked Gemini call). |
| One-active-job invariant, DB level | `GENERATION_PG_URL=postgresql+psycopg://codexone:codexone@localhost:5433/qa_scratch pytest api/tests/test_generation_pipeline.py -k "postgres or race"` | 3 passed; `-k postgres` 5 more runs: 5/5 passed (8 parallel inserts -> exactly 1 succeeds, rest IntegrityError). |
| One-active-job invariant, API level on Postgres | `$SP/gen_probe.py` (10 TestClients, per-user rate limit and cooldown disabled to reach the DB lock) | 10 parallel `POST /api/generate` with distinct keys -> `[201, 409 x9]`, 1 active job, 1 dispatch. 6 parallel with the same idempotency key -> `[201, 200 x5]`, 1 job, 1 dispatch. |
| Can a dashboard request publish/approve? | code read `api/app/routes/generate.py:216-286`, `main.py:_generate` | it only dispatches `daily-generate.yml`; the pipeline ends at `send_preview`; nothing calls `apply_decision`/`publish_item`. No. |
| Reconcile / no token / rate limit | code read `src/generation.py:401-432`, `src/github_actions.py:85-105` | GitHubError -> `reachable=False`, job kept; rate limit pauses reads (`_blocked_until`, 30-300 s); no token or repo -> 503 `not_configured`; `not_started` after 90 s is revived by the runner (`Reporter.begin`). |

### Findings (Area 5)

**QA-L-10 (Low) "auto" slot is resolved twice (API at request time, runner at start time)**
- `api/app/routes/generate.py:248,276` sends `slot: "auto"` to the workflow after the API checked taken/stale for `next_slot(now)`; the runner recomputes `next_slot()` when it starts (`main.py:68`). A run that waits in the `generate-posts` concurrency group (up to `QUEUE_LIMIT` 90 min) across the 30-minute lead can generate for a different slot than the one the API validated and showed; `Reporter.begin` then silently rewrites the job's `slot_at`. Fix: send the resolved slot (and date) to the workflow.

**QA-L-11 (Low) Run matching by `display_title` alone**
- `src/github_actions.py:121-128`: any `workflow_dispatch` run titled `Generate <id>` created within the window is accepted (e.g. a manual run where someone pastes a request id). Low impact (needs repo write access). Fix: also match `head_sha`/actor or pass a random nonce input and compare it in the run's inputs.

---

## Area 6: Dashboard + Logs

Data: `$SP/seed_big.sql` into `qa_scratch`: 50,000 posts over 365 days (incl. 3,334 rows with an out-of-enum status, category `Bogus`, NULL `publish_at`/`decided_at`/`published_at`, rows created 30 days in the future, `targets=["ig"]`, failed/retry platform records), 200,000 activity rows over 120 days, 2,000 generation jobs.

### Evidence (no finding)

| Check | Script | Result |
|---|---|---|
| Auth | `$SP/csrf.py`, RIE | `/api/dashboard/overview`, `/api/logs*` need a session (401 without). |
| Demo mode writes nothing | `$SP/perf_compute.py` (SQLAlchemy `before_cursor_execute` listener) | 3 demo computes -> `SQL statements issued: 0`. |
| Demo cannot be forced on in production | RIE (`COOKIE_SECURE=true`, `DASHBOARD_DEMO_ENABLED` unset) | `workspace=demo` -> 404, `workspace=demo&range=90` -> 404; `range=7` -> 422. `DASHBOARD_DEMO_ENABLED` is not a Config-store name, so it can't be switched on from the dashboard. |
| Adversarial data in metrics | `$SP/metrics_fuzz.py`, `$SP/metrics_fuzz2.py` (300 random datasets + fixed cases: all sources None, empty, no slots/weights, 1 all-NULL row, naive datetimes, IST-midnight `now`, future dates, published-before-created, duplicate groups/ids, unknown statuses/platforms, negative attempts) | `failures: 0` (no exception escapes, no NaN/Infinity). Exceptions only arise when NOT NULL columns (`generation_jobs.created_at`, `activity_log.created_at`) are None, and then only that section reports "failed" (`_guard`). Division by zero: `rate()` guards `den == 0`. |
| Cache / ETag separation | code read `api/app/routes/dashboard.py:170-183` + RIE | cache key `(workspace, range)`; payload has no per-user data (single workspace, every user is admin); `ETag` + `Cache-Control: private, max-age=0, must-revalidate`; CloudFront `/api/*` CachingDisabled. Live and demo are separate entries. |
| Logs LIKE escaping / bounds / injection | `$SP/logs_probe.py` against :8011 with 200k rows | `q=%_` -> 0 rows (literal), `q=% _` -> matches, `event=post.%` -> 0 (literal), `event=post.` -> prefix match; `limit` 0/501 -> 422, 500 ok; `before_id` 0/-1 -> 422; bad date -> 422; `level=x' OR 1=1--` -> bound parameter, no effect; `source` > 24 chars -> 422; inverted date range -> 0. |
| Prune / PII | `activity.prune()` on the seeded table | deleted 49,980 rows older than 90 days in 318 ms; no IPv4 pattern in any `actor`/`message`; failed logins store `unknown` for non-accounts. |
| Redaction in activity rows | `$SP/leak.py` (Area 2) | no secret fragment in `activity_log`. |

### Performance (server time, local Postgres 16 in docker, 50k posts / 200k activity rows)

| Endpoint | p50 | p95 | Note |
|---|---|---|---|
| dashboard `compute("live", 30)` (cache bypassed, in-process, 8 runs) | 1321 ms | 2974 ms | budget 600 ms: **exceeded** |
| dashboard `compute("live", 90)` | 1164 ms | 1230 ms | exceeded |
| `GET /api/dashboard/overview` first call on Lambda RIE | 1346 ms | | then 34 ms from the 15 s cache |
| `GET /api/logs` | 62 ms | 78 ms | |
| `GET /api/logs?q=zzz_nomatch` | 206 ms | 220 ms | full-table ILIKE + facets |
| `GET /api/posts` | 5707 ms | 5743 ms | **79 MB** response |
| `GET /api/generate/slots` | 4134 ms | 4820 ms | `q.load()` of every post |
| `GET /api/generate/check?topic=...` | 4631 ms | 5367 ms | `q.load()` + full history |
| `GET /api/config` | 108 ms | 172 ms | |

### Findings (Area 6)

**QA-M-08 (Medium) Posts / Generate endpoints load every post ever made; /api/posts has no pagination and will exceed Lambda's 6 MB response limit**
- Files: `api/app/routes/posts.py:73-101` (`q.load()` + all groups returned), `api/app/routes/generate.py:139-175,202-213` and `src/generation.py:145-154` (`q.load()` and `posted_entries()` on every slots/check call; `/generate/check` runs on every keystroke pause in the form).
- Repro: `QA_GUARD=0 N=5 python $SP/perf.py` with the 50k-post seed: `/api/posts 200 78994 KB p50=5707ms`, `/api/generate/slots p50=4134ms`, `/api/generate/check p50=4631ms`.
- Impact (production): ~2 groups/day at ~3.2 KB per group in the response = ~2.3 MB/year; with Lambda's 6 MB synchronous response cap the Posts page starts failing after roughly 2.5 years (sooner with long captions), and latency grows linearly long before that (30 s Lambda timeout). Not a problem on day one; a time bomb for a sold product.
- Fix: paginate `/api/posts` (by publish_at) with server-side filters; query only needed columns for slots/check (`WHERE publish_at BETWEEN ...`, `SELECT topic, date ... ORDER BY created_at DESC LIMIT 200`).

**QA-M-09 (Medium) Dashboard overview misses the 600 ms budget at scale (1.2-1.3 s p50, 3.0 s p95)**
- Repro: `cd $SP/newwt && python $SP/perf_compute.py` -> `compute live range=30: p50=1321ms p95=2974ms`; RIE first call 1346 ms. File `api/app/routes/dashboard.py:61-84` (all posts in the window plus every pending/approved/failed post of all time, materialised as Python objects, then aggregated in Python).
- Impact: production at 50k posts; mitigated by the 15 s per-process cache (each Lambda container recomputes on its first hit). Fix: push the KPI aggregations into SQL, bound the "always include" statuses by age.

**QA-L-12 (Low) One row with an unknown status breaks Posts, Generate slots/check and the poll job**
- Repro: seeded rows with `status='weird_status'` -> `/api/posts`, `/api/generate/slots`, `/api/generate/check` all 500 (`$SP/api8011.log`: `ValidationError: 1 validation error for Item status Input should be 'pending', ...`); `main.py poll` uses the same `q.load()`. The new dashboard overview handled the same rows.
- File `src/queue_store.py:93-103` (`Item.model_validate` per row, no per-row isolation). Pre-existing behaviour, but now exposed by more endpoints. Fix: skip/flag invalid rows instead of failing the whole load.

---

## Area 7: Migrations

Scratch DB `qa_mig` (created for this; `codexone` untouched). Commands run from `$SP/newwt/api` with `DATABASE_URL=postgresql+psycopg://codexone:codexone@localhost:5433/qa_mig`.

| Check | Result |
|---|---|
| Clean DB: `alembic upgrade head`, then 3 cycles of `downgrade -1` x7 (to base) + `upgrade head` | no ERROR/FAILED in any step; ends at `d74f5a08b3e6 (head)` each cycle. |
| `alembic check` at head | `No new upgrade operations detected.` (no model/migration drift). |
| From the 6ea71f245945 schema with data written by OLD code (8a8b240: 20 posts + 1 user) -> `upgrade head` | 4 revisions applied; 20 posts kept; old user gets `job_title=''`, `timezone='Asia/Kolkata'` (server defaults). |
| With rows in every new table (otp_codes FK -> users, avatar bytes, activity_log, an active generation job, a config value) -> `downgrade -1` x4 back to 6ea71f245945 | all 4 downgrades succeed; posts 20, users 1 kept; old code `q.load()` -> 20. Re-`upgrade head`: 4 revisions applied. (Downgrade drops the new tables' data by design; documented in d74f5a08b3e6.) |
| Rollback safety of the CI step | see QA-M-02 (pre-merge code cannot run `alembic upgrade head` against a d74f5a08b3e6 database). |

No new findings in this area.

---

## Area 8: Test-suite health

All runs in `$SP/newwt` (no `.env`), with every `.env` key set to a SENTINEL (`$SP/env.sh`) so the suite sees "secrets present", and the socket guard on (`QA_GUARD_LOG` records blocked calls).

| Run | Command | Result |
|---|---|---|
| 1 | `python -m pytest api/tests tests -q -p no:cacheprovider -p qa_plugin -x` | 358 passed, 1 skipped, 72.8 s |
| 2 | same (no -x) | 358 passed, 1 skipped, 86.6 s |
| 3 | same | 358 passed, 1 skipped, 84.9 s |
| reversed | `pytest.main([... 359 node ids from --collect-only, reversed])` | 358 passed, 1 skipped, 85.6 s |
| PG lock test | `GENERATION_PG_URL=...qa_scratch pytest ... -k postgres` x6 | 6/6 passed (it is the 1 skip in the normal runs) |
| Network | guard logs `$SP/pytest_guard1.log`, `$SP/pytest_guard2.log` | no file written: zero outbound DNS/connect attempts in 4 full runs. |
| Rows left behind | plugin `$SP/guard/qa_rows.py` (row counts after every test) | 110 tests leave rows; final DB `claim.db`: `activity_log 73, posts 11, users 3, config_keys 1, config_meta 1, generation_jobs 1`. |

**QA-L-13 (Low) Test isolation: one module silently redirects the whole session's database, and tests share/leave rows**
- `tests/test_publish_claim.py:18-26` sets `os.environ["DATABASE_URL"]` to its own SQLite file and clears the engine caches at import time (collection), so every `api/tests` test after collection runs against `claim.db`, not the `test.db` that `api/tests/conftest.py` prepared (FINAL line above: `claim.db`). 110 tests add rows that later tests see (top: test_posts 33, test_profile 18, test_config 14, test_generate 11). The suite passes in forward and reverse order today, so no flake was observed, but any new count-based assertion becomes order-dependent. `conftest.py` also never removes its `mkdtemp()` directories. Fix: per-test transaction rollback or a fresh SQLite per module via a fixture; move the DB override in test_publish_claim into a fixture.
- Also note: `api/tests/conftest.py` overrides only some of the `.env` keys; real `GEMINI_API_KEY`, `TG_BOT_TOKEN`, `IG_ACCESS_TOKEN`, `YT_*`, `COUDNARY_API_ENV_VAR`, `SMTP_*` from a developer's `.env` stay in the test process. No test made a network call in my runs, but nothing (no socket guard in the suite) would stop a future regression from using production credentials. Suggest a session-wide socket guard fixture and sentinel overrides for every secret name in `src.redact.SECRET_ENV_NAMES`.

---

## Examined, no findings (summary; full evidence in each area's table)

| Area | What | Evidence |
|---|---|---|
| 1 | Old code (8a8b240) queue load/upsert/save, claim, poll with fake Telegram, expire_stale, publish with fake publishers against d74f5a08b3e6 | `$SP/seed_new.py` + `$SP/old_flow.py` |
| 1 | New `main.py poll` end-to-end; refresh-token with the workflow's minimal deps; Lambda image routes | `$SP/new_flow.py`, `$SP/venv_min`, `$SP/lam.py`, `$SP/lam2.py` |
| 2 | Secret leakage (responses, headers, logs, files, 6 tables), CLI output, AES-GCM nonces/tamper/wrong key/rotation/half-write, save concurrency, verify-then-store, env-wins, SSRF on all 4 verifiers | `$SP/leak.py`, `$SP/crypto.py`, `$SP/cfg_semantics.py`, `$SP/ssrf.py` |
| 3 | CSRF on all 26 write routes, cookie flags, token_version, OTP cap under 40-way concurrency, OTP binding, header/HTML injection, XFF spoofing | `$SP/csrf.py`, `$SP/otp_race.py`, code read |
| 4 | Avatar limits/sniffing/nosniff/caching, IDOR, Unicode usernames, CRLF/path payloads, stored-XSS sinks | `$SP/profile_probe.py`, grep of web/src |
| 5 | Workflow input injection, one-active-job (DB + API level), idempotency, no publish path from Generate | YAML read, `$SP/gen_probe.py`, PG race test x6 |
| 6 | Demo zero-writes + 404 in production, metrics fuzz (300 datasets), cache/ETag, Logs LIKE escaping/bounds, prune, no IPs | `$SP/perf_compute.py`, `$SP/metrics_fuzz*.py`, `$SP/logs_probe.py` |
| 7 | Upgrade/downgrade cycles from clean and from 6ea71f245945 with data; `alembic check` | Area 7 table |
| 8 | 3 forward runs + 1 reversed, no network, rows tracking | Area 8 table |

## Not tested

- Production Neon, AWS, GitHub repository settings (secrets/variables actually configured), real providers: excluded by the rules. Whether `vars.EXPECTED_*`, `CONFIG_MASTER_KEY`, `GITHUB_REPOSITORY` exist in the real GitHub/SSM configuration is unknown.
- A real CloudFront distribution: the "sourceIp = CloudFront origin-facing IP" behaviour behind a Function URL is taken from AWS documentation and simulated in the RIE event (QA-M-05).
- Lambda cold start at the production 1024 MB setting (RIE ran at 3008 MB).
- A live SMTP server (down / bad credentials / slow): mailer error handling verified by reading only.
- Google OAuth round trip: Google sessions were minted with `create_session_token` (what the callback issues) instead.
- Peak memory during a 300 MB chunked avatar upload (only before/after RSS sampled).
- OTP brute force across several concurrent Lambda containers (each has its own in-memory limiter; the DB 5-try cap was tested on one process).
- The web app (separate frontend QA); only a grep for raw-HTML sinks was done.
- Running `python -m src.config_store rotate` against GitHub/SSM copies of the key (only the library round trip).
- Dashboard p50/p95 measured on local docker Postgres, not Neon (network latency to Neon would add per-query time).

## Cleanup

- My uvicorn (:8011) and the `qa-lambda` container were stopped; worktrees `oldwt`, `oldwt2`, `newwt` removed. Left in place: scratch databases `qa_scratch`, `qa_mig` in the local docker Postgres (disposable), the image `qa-api`, and the worktree `$SP/headwt` (6e8b79c) created by the earlier, interrupted QA run.
