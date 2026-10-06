# Config section: implementation notes (milestone 1 = spec phases P1 + P2 Tier 1 + Docs)

Status: built, tested locally, NOT deployed | Date: 2026-10-06 | Spec: `docs/specs/config-section.md`

## 1. What exists now

| Area | Where |
|---|---|
| Redaction (R-05) | `src/redact.py` (`redact`, `redact_exc`, `redact_obj`, `register`, `RedactingFilter`, `install`); installed by `src/logger.py` (codexone + root handlers + `logging.lastResort`) and `api/app/main.py:create_app`; applied in `approve_bot.notify`, `activity.record`, `publish._call`, `refresh_token.refresh/save_token`, `actions.trigger_pipeline_run` |
| Owner defaults removed (R-20) | `src/github_actions.py` (`repository()`, no default; `configured()` needs token AND repo), `src/actions.py`, `main.py`, `scripts/check_secrets.py`, `.github/workflows/check-secrets.yml` (ids/fingerprints now optional repo *variables*), README cron table |
| Settings schema | `src/config_schema.py` (fields, integrations, `STORE_NAMES`, `BOOTSTRAP`) |
| Encrypted store | `src/config_store.py` (+ CLI: `generate-key`, `status`, `import-env [--apply]`, `rotate`) |
| Resolver | `src/config.py`: `resolve(name) -> (value, source)`; `get_env` unchanged signature, env wins, `CONFIG_PRECEDENCE=store` flips |
| Verifiers | `src/verify/` (`base.py` result model + code catalogue + paste cleaner + HTTP helper; `gemini`, `telegram`, `cloudinary`, `github`, `database`, `stubs`; CLI `python -m src.verify`) |
| Status / readiness | `src/config_status.py` (`record`, `history`, `latest`, `integration_state`, `readiness`, `overview`) |
| API | `api/app/routes/config.py`, mounted in `api/app/main.py` under the protected `/api` router |
| UI | `web/src/pages/Config.tsx`, `web/src/pages/ConfigGuide.tsx`, `web/src/components/config/parts.tsx`, `web/src/lib/config.ts`, `web/src/lib/config-format.ts`, `web/src/lib/config-guides.ts`; routes `/config`, `/config/guide/:topic?`; nav `ready: true` |
| Migration | `api/migrations/versions/20261006_d74f5a08b3e6_config_store.py` (revision `d74f5a08b3e6`, down `c63e49f7a2d5`) |
| Deps | `cryptography>=42` in `requirements.txt` and `api/requirements-lambda.txt`; `api/Dockerfile.lambda` copies `api/migrations/versions` (read-only, for the schema check) |
| Tests | `tests/test_redact.py`, `tests/test_verify.py`, `tests/test_verify_catalogue.py`, `tests/fake_http.py`, `api/tests/test_config.py`, `web/tests/config.test.mts`; `api/tests/conftest.py` gained `GITHUB_REPOSITORY` and an empty `CONFIG_MASTER_KEY` |

Not built (later phases, by design): system test / `preflight.yml` (G6), Instagram/YouTube/SMTP/Google live verifiers (listed as "not verified yet"), health alerts, Connect flows, wizard progress persisted server-side, `refresh_token.py` writing to the store.

## 2. Design decisions taken here (where the spec left room)

- Status vocabulary: verifier results are `not_set | valid | warning | invalid | unknown`; the UI adds `checking`, and integration cards add `stale` (verified before, value changed since) and `unverified` (never verified). `unknown` (provider outage) is kept distinct from `invalid` (spec R-36).
- **Binding results to values:** every stored check carries `values_fp` = HMAC (under a DEK-derived key) of the integration's effective values. Readiness counts a check only if it matches the values in effect *now*, so a change anywhere (Config page, `.env`, SSM) makes it stale. `config_version` is an integer bumped on any store change of a required field (shown in the UI, recorded per check).
- **No "last 4" ever:** the spec (R-01) forbids it; the API returns only a keyed 8-hex fingerprint. Non-secret values (repository, chat id, model) are shown.
- **Verify-then-store:** `PUT /api/config/{integration}` verifies the merged candidate (current values + submitted ones) and stores only on `valid`/`warning`; `unknown` requires `save_unverified: true` (UI confirm); `invalid` returns 422 and changes nothing. Optimistic concurrency: the client must send the version it saw for every field (`expected`), else 422; mismatch → 409.
- **Archived repository** is a warning, not a failure (its effect on dispatch is unconfirmed).
- **G6 (system test)** is reported with `ok: null, blocking: false` because it isn't built; `ready_to_generate` is computed over G1-G5, G7, G8. The UI says so.

## 3. API (all under `/api/config`, signed-in admin, CSRF on writes)

| Method / path | Body | Response |
|---|---|---|
| `GET /api/config` | | `{integrations: Integration[], readiness: Readiness, precedence: "env"\|"store", master_key: "ok"\|"empty"\|<code>, store_error, digest}` |
| `GET /api/config/schema` | | `{integrations, fields, error_classes, codes: {code: {error_class, message, hint}}}` |
| `GET /api/config/readiness` | | `Readiness` (below) |
| `GET /api/config/{integration}/history?limit=10` | | `{checks: StoredCheck[]}` |
| `POST /api/config/{integration}/verify` | `{values?: {NAME: str}, depth?: "format"\|"live"\|"deep", consent?: bool}` | `{result: VerifyResult, cleaned: {NAME: [notes]}}`; deep needs `consent` (400 `consent_required`), 60 s cooldown (429 `cooldown`) |
| `PUT /api/config/{integration}` | `{values: {NAME: str}, expected: {NAME: version}, save_unverified?: bool}` | 200 `{result, cleaned, integration, readiness}`; 422 `verify_failed` `{result}`; 409 `verify_unknown` `{result, can_force}`; 409 `conflict` `{fields}`; 422 `unknown_field`/`required_field`/`expected_versions`; 400 `not_editable` |
| `DELETE /api/config/{integration}/{field}?version=N` | | 204; 409 `conflict` |
| `POST /api/config/telegram/detect` | `{token?: str}` | `{chats: [{id, type, title}], code: null}` or `{chats: [], code, message, hint, docs}` |
| `POST /api/config/telegram/delete-webhook` | `{token?: str, confirm: true}` | `{ok: true}`; 400 without confirm |

Limits: 20 provider-touching calls / user / minute; identical values re-verified within 10 s reuse the stored result (`reused: true`); one check per integration at a time per process (409 `check_running`).

`VerifyResult = {integration, status, depth, checks: [{name, label, ok: true|false|null, depth, evidence, code, soft}], error_class, code, message, hint, docs, evidence: {}, latency_ms, checked_at, expires_at, implemented}`

`Integration = {name, title, tier, blurb, minutes, implemented, editable, state, required_set, conflict, check: StoredCheck|null (current values), last_check, fields: [{name, label, secret, required, shape, help, advanced, is_set, source: "env"|"store"|null, in_env, in_store, overridden, conflict, value (non-secret only), fingerprint (secret only, 8 hex), version, updated_at, updated_by, undecryptable}]}`

## 4. Verifier catalogue

Depths: **format** (local), **live** (read-only provider calls), **deep** (explicit consent: Gemini 1 request, Telegram 1 plain message).

| Integration | Checks | Codes (each has a troubleshooting entry, enforced by `tests/test_verify_catalogue.py`) |
|---|---|---|
| Gemini | `key_format`, `model_format` (format); `key_accepted` = `GET /v1beta/models`; `model_available` = `POST /v1beta/models/{m}:countTokens`; `generation` (deep) = `generateContent` with a 1-field JSON schema. Key in `x-goog-api-key` header only | `gemini.format, model_format, key_rejected, key_blocked, forbidden, billing, model_not_found, rate_limited, quota (warning), unavailable, unreachable, generation_empty` |
| Telegram | `token_format`, `chat_format`; `token_valid` = getMe; `no_webhook` = getWebhookInfo (url must be empty); `chat_reachable` = getChat; `delivery` (deep) = sendMessage without reply_markup. `detect_chats`: getWebhookInfo then getUpdates with **no offset, no allowed_updates, timeout 0**, limit 100 | `telegram.token_format, chat_format, token_rejected, webhook_set, chat_not_found, blocked, no_chat_found, poll_conflict, rate_limited, unavailable, unreachable` |
| Cloudinary | `format` (+ template placeholder detection); `credentials` = Admin `GET /v1_1/{cloud}/ping`; `upload` = Upload API, 633-byte JPEG to `codexone/_selftest/<random>`; `public_link` = HEAD of `secure_url` (only `*.cloudinary.com` https); `cleanup` = destroy (always attempted, in `finally`). Basic auth header only | `cloudinary.format, placeholder, rejected, forbidden, not_found, rate_limited, upload_failed, delivery_failed, cleanup_failed (warning), unavailable, unreachable` |
| GitHub | `repo_format`, `token_format`, `token_kind` (ghp_ warns); `repo_visible` = `GET /repos/{o}/{r}` (+ archived, default branch, `GitHub-Authentication-Token-Expiration`); `workflow:daily-generate.yml`, `workflow:poll-approvals.yml` = `GET .../actions/workflows/{file}` state must be `active`; `actions_write` reported as not exercised (never dispatches) | `github.repo_format, token_format, token_rejected, not_found, forbidden, workflow_missing, workflow_disabled, archived, branch, classic_token, token_expiring, write_unconfirmed, rate_limited, unavailable, unreachable` |
| Database | `format`, `direct` (warns on `-pooler`); `connect` (1 retry); `schema` (tables); `migrations` (alembic_version vs heads parsed from `api/migrations/versions`); `write` (UPDATE touching no row, rolled back); `master_key` (canary) | `database.not_set, format, unreachable, rejected, schema_behind, read_only, pooled_url, master_key_missing, master_key_invalid, key_mismatch` |
| Instagram, YouTube, Email, Google | stub: `unknown` + `verify.not_implemented` when set, `not_set` otherwise | `verify.not_set, verify.not_implemented, verify.crashed` |

Error classes: `not_set, format, rejected, forbidden, expired, quota, rate_limited, mismatch, not_found, unreachable, misconfigured, unknown, not_implemented`. Provider-side (`unreachable, unknown, rate_limited`) ⇒ status `unknown`; `quota` ⇒ `warning`.

## 5. Generate gating contract (for the Generate dev; I did not edit Generate files)

**Server (recommended, authoritative):** in `api/app/routes/generate.py` `request_generation`, before creating a job:

```python
from src import config_status
r = config_status.readiness()
if not r["ready_to_generate"]:
    raise _fail(409, "not_ready", "Setup isn't complete: " + "; ".join(m["label"] for m in r["missing"]),
                missing=r["missing"])
```
`readiness()` never raises, makes no provider calls, and does one live database check (a few queries; call it once per POST, not per poll).

**Client:** `GET /api/config/readiness` →
```json
{"ready_to_generate": false, "config_version": 7, "checked_at": "2026-10-06T10:00:00+00:00",
 "conditions": [{"id": "G1", "label": "Database and master key", "ok": true, "blocking": true, "detail": "...",
                 "integration": "database", "code": null, "fix": "/config#database"}, ...],
 "missing": [{"id": "G3", "label": "Telegram works", "detail": "A webhook is set ...", "fix": "/config#telegram"}],
 "not_covered": ["Provider outages", "..."]}
```
Disable the Generate button when `ready_to_generate` is false and list `missing[]` with links to `fix` (anchors on `/config`). `ok: null` means "not available" (G6), never "passed".

**Rollout caution:** readiness requires `CONFIG_MASTER_KEY` (G1) and verified values for the *current* settings. Enabling the gate before the owner's deployment is green (section 9) would block the owner's own Generate. Gate behind a flag or ship it after step 9.5.

## 6. Instagram token in URLs (task item 1)

Official docs fetched 2026-10-06 with curl:
- https://developers.facebook.com/docs/instagram-platform/content-publishing documents `-H "Authorization: Bearer <ACCESS_TOKEN>"` for `POST /<IG_ID>/media` and `POST /<IG_ID>/media_publish` (also `Authorization: OAuth` on rupload).
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/get-started documents `GET /me` with `access_token` as a **query** parameter only; https://developers.facebook.com/docs/instagram-platform/reference/refresh_access_token likewise (query only).

Decision: `src/publish.py` already sends the token in the **form body** for POST (never in a URL); GET calls (`/me`, container status, publishing limit) and the refresh keep the documented query parameter, because a header on those GET endpoints is not documented and switching the owner's working publisher on a guess is the wrong trade. Instead the URL can no longer escape: network-error text is scrubbed (`redact_exc`), the refresh error is raised `from None` (no chained exception holding the URL), the new refreshed token is `register()`ed, `gh secret set` failures no longer quote the command line, and every log handler / `notify` / activity row runs through the redactor (tests in `tests/test_redact.py`). See U-IG1 for moving GET calls to a header.

## 7. Sources fetched (2026-10-06, curl) and what each settles

| Claim used in code/docs | Source |
|---|---|
| Gemini key in `x-goog-api-key` header; auth vs standard keys; dormant unrestricted keys blocked; AI Studio API keys page URL; default project for new users | https://ai.google.dev/gemini-api/docs/api-key |
| `GET /v1beta/models`, `pageSize`, model `name` format | https://ai.google.dev/api/models |
| `models.countTokens` endpoint | https://ai.google.dev/api/tokens |
| Leaked keys message; retry only 429/408/5xx | https://ai.google.dev/gemini-api/docs/troubleshooting |
| 401 authentication, 402 payment_required, 403 permission_denied, 404 model_not_found, 429 rate_limit_exceeded vs quota_exceeded (Interactions API table) | https://ai.google.dev/gemini-api/docs/api-errors |
| Limits per project, RPD resets midnight Pacific | https://ai.google.dev/gemini-api/docs/rate-limits |
| Paid Tier prompts not used to improve products | https://ai.google.dev/gemini-api/docs/billing |
| Bot API URL form, getUpdates offset/confirmation, allowed_updates persistence, webhook exclusivity, getWebhookInfo url empty for polling, 24 h retention, error shape | https://core.telegram.org/bots/api |
| /newbot, token revocable via BotFather | https://core.telegram.org/bots/tutorial |
| Start button, `t.me/<bot>?start=` deep link | https://core.telegram.org/bots/features |
| Admin API basic auth, ping, 401/403/404/420, 500/h free, Upload API not rate-limited | https://cloudinary.com/documentation/admin_api |
| Upload API basic auth in Authorization header, destroy, status codes | https://cloudinary.com/documentation/image_upload_api_reference |
| API Keys page, roles, environment variable shown as a template to fill | https://cloudinary.com/documentation/product_environment_settings |
| Get workflow needs Actions read; dispatch needs Actions write | https://docs.github.com/en/rest/actions/workflows |
| Workflow `state` enum | https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.yaml |
| 404 instead of 403 for private resources; "Resource not accessible by personal access token" | https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api |
| Fine-grained token creation steps, prefill URL | https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens |
| Token prefixes `github_pat_`, `ghp_` | https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github |
| Forks / 60-day inactivity disable schedules | https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows |
| `GitHub-Authentication-Token-Expiration` header exists | https://github.blog/changelog/2021-07-26-expiration-options-for-personal-access-tokens/ |
| Pooled string default with `-pooler`; toggle for direct | https://neon.com/docs/connect/connect-from-any-app |
| Scale to zero after 5 min; wakes in a few hundred ms | https://neon.com/docs/introduction/scale-to-zero |

## 8. UNVERIFIED (labelled in code/UI; each with the spike that settles it)

Run spikes on a machine with real keys in the environment (never paste output containing values; the CLIs print none).

| ID | Statement (not asserted as fact) | Where it matters | Spike |
|---|---|---|---|
| U1 | How Gemini errors look for a *rejected standard key* vs an invalid key on `v1beta/models` (classic `google.rpc` shape `error.status/details[].reason` is parsed defensively; the fetched error table is the Interactions API's) | `gemini.classify` | `python -m src.verify gemini --json` with the owner key, a deleted key, and a garbage key; record status codes/codes |
| U4 | Whether `models.list` / `countTokens` count toward rate limits | guide wording ("not documented") | Run `python -m src.verify gemini` 30 times in a minute with a free key; watch AI Studio > Rate limit |
| U-G2 | Whether `generateContent` with `maxOutputTokens: 256` and a schema returns JSON on thinking models | `gemini.generation_empty` | `python -m src.verify gemini --depth deep --json` |
| U9 | Telegram token length/charset beyond the documented example; 404 vs 401 for malformed vs revoked tokens | `TOKEN_RE`, `telegram.classify` | `python -m src.verify telegram --json` with the real token, then with one character changed |
| U18 | getUpdates without offset neither confirms updates nor collides (409) with the poll job in practice | chat detection | Press a preview button, don't let the poll run, call `POST /api/config/telegram/detect` (or `python -c "from src.verify.telegram import detect_chats; import os; print(len(detect_chats(os.environ['TG_BOT_TOKEN'])[0]))"`), then run `python -m src.approve_bot poll --dry-run` and confirm the press is still applied |
| U-TG2 | A bot can't message a user until they press Start; group bots with privacy mode see `/start@bot` | guide step (tagged Unverified) | Create a bot, call sendMessage to your user id before Start; add to a group and send `/start@bot`, then Detect |
| U19 | Cloudinary exact status/body for bad key, bad cloud name, exhausted credits; whether destroy returns `{"result":"ok"}` on all plans | `cloudinary.classify`, cleanup | `python -m src.verify cloudinary --json` with the real URL, with the secret altered, with the cloud name altered |
| U-CL2 | Console deep link `https://console.cloudinary.com/settings/api-keys` | guide step (tagged) | open it signed in |
| U-CL3 | Free/paid delivery settings never block a HEAD on `res.cloudinary.com` | `public_link` | part of the cloudinary spike |
| U20 | Fine-grained token without Actions read: 403 on `actions/workflows/{file}` (docs say "Resource not accessible") | `github.forbidden` | Token with only Metadata: read, then `python -m src.verify github --json` |
| U-GH2 | Format of `GitHub-Authentication-Token-Expiration` (parser accepts `YYYY-MM-DD HH:MM:SS UTC` and `... +0000`; else "not reported") | expiry warning | `curl -sI -H "Authorization: Bearer $GITHUB_DISPATCH_TOKEN" https://api.github.com/repos/$GITHUB_REPOSITORY \| grep -i expiration` |
| U-GH3 | Prefill parameter name `actions=write` on the token page (not used in links yet) | future convenience link | open `https://github.com/settings/personal-access-tokens/new?name=content+dashboard&actions=write` |
| U-GH4 | Archived repository refuses workflow_dispatch | `github.archived` (warning only) | archive a scratch repo, dispatch, unarchive |
| U-GH5 | "Metadata: read is added automatically" | guide step (tagged) | create the token and read its permission list |
| U28 | A template-generated repo isn't treated as a fork for scheduled workflows | `workflow_disabled` | create from template, `python -m src.verify github` |
| U-IG1 | `Authorization: Bearer` works for GET `graph.instagram.com/me` and container status (documented only for POST /media, /media_publish) | moving the IG token out of GET URLs | `curl -s -H "Authorization: Bearer $IG_ACCESS_TOKEN" "https://graph.instagram.com/v21.0/me?fields=user_id,username"` (expect the same JSON as the query form) |
| U-ARCH | `Neon` cold start + one 2 s retry is enough from the Lambda | `database.unreachable` | after 10 idle minutes, `GET /api/config/readiness` from the deployed API |
| U10 | `cryptography` fits the Lambda image | **settled**: `docker build -f api/Dockerfile.lambda` succeeded, image 298 MB, `cryptography 50.0.2` imports inside it | (done 2026-10-06) |

## 9. Threat model (what was considered and how it is tested)

| Threat | Mitigation | Test |
|---|---|---|
| Secret returned to the browser | API returns only `is_set`, source, 8-hex HMAC fingerprint; no last-4; non-secrets only | `test_save_cleans_verifies_encrypts_and_never_echoes` (sentinel scan over every endpoint) |
| Secret in logs / exceptions / Telegram / activity | `src/redact.py` known-value + shape scrubbing on all handlers, `notify`, `activity.record`, `Result.to_dict`; IG URLs scrubbed | `tests/test_redact.py` |
| Secret in URLs sent to providers | Gemini header, Cloudinary basic auth header, GitHub bearer; Telegram path by design (docs) | `everything_sent()` assertions in `tests/test_verify.py` |
| DB dump | AES-256-GCM, DEK wrapped by master key outside DB, AAD binds ciphertext to name+version | `test_ciphertext_cannot_be_moved_between_settings`, dump scan |
| Key loss / mismatch | canary, `database.key_mismatch`, re-entry documented; rotation by re-wrap | `test_wrong_or_missing_master_key`, `test_rotation_rewraps_and_old_key_stops_working` |
| A typo replacing a working value | verify-then-store; failed verify never writes | `test_failed_verify_never_replaces_a_working_value` |
| Races on save | `expected` versions, `SELECT … FOR UPDATE` on Postgres, unique PK on first insert → 409 | `test_concurrent_edit_gets_409` |
| Duplicate / abusive checks | per-user 20/min, per-integration single-flight, 10 s dedupe, 60 s deep cooldown, consent for deep | `test_deep_check_needs_consent_and_has_a_cooldown`, `test_per_user_rate_limit`, `test_same_values_within_10s_reuse_the_result` |
| SSRF / path injection | fixed hosts; token/cloud/repo/model validated before entering URLs; no redirects followed; Cloudinary `secure_url` must be https `*.cloudinary.com` | `test_telegram_format_blocks_path_injection`, `test_cloudinary_never_fetches_foreign_hosts`, `test_github_format` |
| CSRF / authz | protected router + `require_admin` | `test_requires_sign_in_and_csrf`, `test_csrf_required_on_writes` |
| Side effects from checks | no publish/dispatch/setWebhook/offset; recording fakes assert it | `test_github_valid_never_dispatches`, `test_detect_chat_never_confirms_updates`, `test_telegram_valid` |
| Store outage breaking the pipeline | resolver never raises; env wins; negative cache 60 s | `test_resolver_never_breaks_when_the_store_is_unavailable` |
| Runner logs leaking store secrets | `::add-mask::` on first resolution in Actions + `register()` | `test_runner_masks_store_secrets` |
| Browser storage | nothing persisted client-side; inputs `autocomplete=off`, password managers told to ignore | review |

## 10. Residual risks (honest)

1. **Env-wins split brain:** the Lambda verifies what *it* would use; the GitHub runner uses its own repository secrets until they are removed. Until the system test (P3) exists, a green Config page does not prove the runner's copy. The UI says so.
2. Cooldown/dedupe/locks are per process; several Lambda instances could each run one check concurrently (harmless: read-only calls; Cloudinary test assets have random ids and are deleted).
3. `GET /api/config` may create the store's data key on first use when a master key is present (a write on a GET; idempotent; a concurrent first-time creation loses with an IntegrityError that is swallowed and retried next call).
4. Readiness does a live DB check per call; on Neon cold start the first call can take a few seconds (one 2 s retry).
5. Redaction is pattern + known-value based; a novel secret format logged before it is ever resolved could slip through. Values resolved from the store are registered automatically.
6. `scripts/check_secrets.py` was not yet turned into a thin CLI over `src/verify` (its workflow installs a reduced dependency set); it keeps working as before.
7. The fixture script used for screenshots parsed `.env` key names with `dotenv_values` (values were loaded in memory by the parser, never printed, stored or used).
8. G6 is not built: "ready" cannot yet promise rendering/upload will work.

## 11. Go-live steps (not done; each needs the owner's approval)

1. **Before deploying this build**, set `GITHUB_REPOSITORY` for the API (there is no default any more; without it the dashboard can't start Generate/Publish-now): `aws ssm put-parameter --name /codexone/GITHUB_REPOSITORY --type String --value <owner>/<repo>` (or save it on the Config page after step 3).
2. Optionally set repository *variables* `EXPECTED_BOT_ID`, `EXPECTED_IG_ID`, `EXPECTED_FP_YT_*` to keep the weekly check-secrets comparisons (previous values are in git history of `check-secrets.yml`).
3. Generate a master key once: `python -m src.config_store generate-key`; store it as SSM `/codexone/CONFIG_MASTER_KEY` (SecureString) and as GitHub secret `CONFIG_MASTER_KEY`; keep a copy in a password manager. Add `CONFIG_MASTER_KEY: ${{ secrets.CONFIG_MASTER_KEY }}` next to `DATABASE_URL` in the workflows' env when the runner should read store values (not needed while env wins and all secrets are in GitHub).
4. Run the migration through CI (`poll-approvals` runs `alembic upgrade head`) or locally against the target DB, then deploy the API image (now includes `cryptography`) and the web build.
5. On the owner's deployment: open `/config`, click Verify again on each Tier-1 card (or run `python -m src.verify all` locally with real keys) and settle the spikes in section 8.
6. Only after all Tier-1 cards are green: let the Generate dev enable the gating (section 5).
7. Later (spec 3.8): `python -m src.config_store import-env` (dry run) → `--apply`, verify, flip `CONFIG_PRECEDENCE=store`, then remove old secrets one integration at a time.
