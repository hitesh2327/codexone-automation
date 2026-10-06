# Spec: Dashboard "Generate" section

Status: Draft for owner review | Author: BA (Bruce Banner) | Date: 2026-10-05
Related: Posts (built), Logs and Profile (in progress by other engineers)

## 0. Evidence base (what the code does today)

- `python main.py generate` (main.py `cmd_generate`) does: pick slot (`--slot` or next slot) -> skip if slot already has a post ("taken") or is >12h past ("stale", `LATE_LIMIT_HOURS`) unless `--force` -> `fetch_topics` (HN, Reddit, dev.to, GitHub, arXiv; saves `data/topics_<date>.json`) -> `rank_topics.rank` (weighted-random category seeded by date+slot, avoids last category, Gemini picks 1 topic, avoids ~40 recent titles) -> `gen_content.generate` (Gemini, with review pass, model fallback chain in `src/llm.py`) -> render carousel (Chromium) + reel (edge-tts, FFmpeg) -> Cloudinary upload -> `approve_bot.send_preview` per item -> activity events `post.generated`.
- Output is ONE topic = 1 carousel item + 1 reel item, status `pending`. Nothing is published without approval (CLAUDE.md rule).
- Triggers today: cron-job.org (primary) and GitHub cron (backup, often hours late) hit `daily-generate.yml`. `workflow_dispatch` inputs today: `slot` (auto/10:00/19:00), `category`, `dry_run`, `force`. There is NO custom-topic input, NO request id.
- `actions.trigger_pipeline_run(workflow, inputs)` already dispatches any workflow using `GITHUB_DISPATCH_TOKEN`; returns only True/False. GitHub's dispatch API returns HTTP 204 with NO run id.
- Both `daily-generate.yml` and `poll-approvals.yml` share `concurrency: queue-state` with `cancel-in-progress: false`. GitHub keeps at most ONE running plus ONE pending run per group; a newer pending run silently cancels the older pending one. Consequence: a Generate dispatch queued behind a running poll can be cancelled by the next poll dispatch (Regenerate, Publish now and cron-job.org all dispatch poll). This is a real reliability risk (see R1).
- The workflow runs `alembic upgrade head` against the production DB (`DATABASE_URL`) on every run. Any new migration therefore reaches production on the next run, not only at "deploy".
- Config: categories + weights `AI 30, SystemDesign 20, DSA 20, Interview 15, OS 10, Dev 5`; `post_times_ist: [10:00, 19:00]`; one post (reel+carousel) per slot; previews expire after 36h without decision.
- Minor doc drift found: the daily-generate.yml header comment says "passed more than 2h ago is skipped"; code says 12h. Dev should fix the comment (not in scope of this spec's code freeze).
- Existing UI patterns: Posts page uses React Query + `sonner` toasts, shadcn `Sheet`/`Dialog`/`Badge`/`Skeleton`/`Table`, `StatusBadge`, `ProgressTrack`. Sidebar item `/generate` has `ready: false` ("soon").

## 1. Purpose and users

**Purpose.** Give the admin a safe, honest control surface for the content-generation pipeline: see what is (not) generated for upcoming slots, start generation on demand, watch it run, and land in Posts to review/approve.

**Users.** Today: one admin (the owner, @codexonebyhitesh), authenticated via the existing dashboard login. Future: more admins/editors. Design so every request records `requested_by` and the API enforces a role check in one place (today: any authenticated user = admin).

**Jobs to be done.**
1. "Did today's 10:00 and 19:00 posts get generated? If not, why not, and fix it now." (primary)
2. "I want a post about X (a topic I chose / a link I found), not what the ranker picked."
3. "Make an extra post, or one in a specific category (e.g. more DSA this week)."
4. "I started it - tell me where it is and when I can review it, without opening GitHub."
5. "Don't let me (or a double click) burn my Gemini quota or Actions minutes."

## 2. Scope

### 2.1 Reality check (challenging the brief)

| Idea | Verdict | Reason |
|---|---|---|
| Synchronous "Generate" button returning a post | Reject | Run takes minutes (install Chromium, Gemini x2-3, render, upload); needs Chromium+FFmpeg, impossible in Lambda. Must be async job. |
| Precise live step progress (fetching -> ranking -> ...) | Partially | GitHub API gives only job/step status for the steps defined in the workflow, not our internal phases. Two options: (a) split the workflow into named steps (coarse, free); (b) the pipeline writes a `phase` to the DB job row (precise, needs code in main.py). MVP: (b) minimal - 6 `phase` updates, plus GitHub run status as fallback. |
| Topic suggestions (ranked candidates) picked from a list | Later | Candidates only exist inside the Actions runner (`data/topics_<date>.json`, gitignored/ephemeral). Showing them needs a separate "fetch topics" job that persists to DB (new table, extra Actions minutes, free-source rate limits). MVP substitute: free-text topic + optional source URL. |
| Pasted source URL | MVP-lite | Pass the URL as the topic's `source_url`; Gemini writes from title/angle only unless we also fetch page text (later). Must state clearly in UI that the page is not read in MVP. Needs SSRF-safe validation (https only, no private hosts) even though the runner, not Lambda, fetches. |
| Custom topic | MVP | New `--topic` path that skips `rank_topics` (still category-validated, still checked against recent titles for duplicates, still Gemini review). |
| Realtime updates | Poll | No websockets on Lambda. Poll job status every 5-10s while active, 60s otherwise, pause when tab hidden. |
| Daily cap and quota warnings | MVP (cap) / Later (live quota) | Gemini free-tier remaining quota is not exposed by any API. We can only count our own requests and react to failures. |
| One run at a time | MVP | Enforced in API by DB (one non-terminal job) AND by workflow concurrency. |

### 2.2 MVP (can go live now)

1. **Slot board.** For today and tomorrow: each configured slot (10:00, 19:00 IST) shows state: `Generated` (link to Posts group, current status), `Generating` (job in progress), `Missing - slot upcoming`, `Missing - slot passed (late, still generates and publishes on approval)`, `Missing - too old (>12h, needs Force)`. Source: posts table `publish_at` + jobs table.
2. **Generate now form** (right-side panel or card): Slot (select: the two slots for today/tomorrow, or "Next available"), Category (Auto by weights / one of six), Topic (optional free text, 5-120 chars), Source URL (optional, https), "Allow extra post for a slot that already has one" (maps to `--force`, off by default, confirm dialog). Submit -> confirm dialog summarising what will happen ("~5-10 min, uses Gemini + Actions minutes, sends previews to Telegram, nothing is published until you approve").
3. **Run tracker.** Card for the active/most recent job: status chip, phase track (reuse `ProgressTrack`), elapsed time, "Open GitHub run" link, on success "Review in Posts" link (to resulting group), on failure a plain-language reason + "Retry" + link to Logs filtered to the request.
4. **Recent requests table** (last 20): time, requested by, params, trigger (dashboard / scheduled), status, duration, link to post and run.
5. **Guardrails.** One active job at a time; daily cap on dashboard-initiated generations (default 4/day IST, config `GENERATE_DAILY_CAP`); dispatch cooldown 60s; quota/failure banner when the last N runs failed with quota errors.
6. **Cross-links.** Posts rows/panels: "Generate another" is not needed; instead Generate shows "Regenerate from feedback happens in Posts" with deep link; Post panel shows "Generated by request #id". Regenerate remains in Posts (existing).
7. **Audit.** Events `generate.requested`, `generate.started`, `generate.finished`, `generate.failed`, `generate.cancelled` into the activity log (source `generate`).
8. **Cron-triggered runs are visible too** (job rows created by the workflow itself, trigger=`scheduled`), so the slot board explains "why is the 10:00 post missing" (skipped as taken/stale, failed, never ran).

### 2.3 Later (explicitly out of MVP)

- Ranked topic-suggestion list with pick-to-generate (needs persisted candidate table + "Refresh topics" job).
- Reading the pasted URL's content (article extraction) as grounding for Gemini.
- Cancel a queued/running job from the UI (GitHub `cancel` API; needs same token with write).
- Edit category weights / post times / voices from the dashboard (belongs to Profile/Settings, writes brand/config.yaml - git commit needed).
- Batch generation (N topics), generating reel-only or carousel-only (`--skip-reel` exists; carousel-only not).
- Live Gemini quota estimator; per-model fallback status.
- Webhook/`workflow_run` based status push instead of polling.
- Multi-user roles and per-user caps.
- Scheduled "generate for next week" planner.
- Dry-run toggle in UI (dev only; keep CLI/GitHub only).

## 3. User flows

### 3.1 Happy path: Generate now
1. Admin opens Generate. Page loads slot board + tracker + recent requests (skeletons while loading).
2. Board shows 19:00 "Missing - slot upcoming". Admin clicks "Generate for this slot" (pre-fills form) or uses the form.
3. Admin optionally sets category/topic/URL, clicks "Generate". Confirm dialog -> Confirm.
4. API validates, inserts job `queued` (generates `request_id`), dispatches workflow with inputs, records `generate.requested`. UI toast "Request sent" and tracker appears in `queued`.
5. API/UI reconciles the job to a GitHub run (run-name contains `request_id`); tracker shows run link and status `in_progress`.
6. Workflow reports phases: fetching topics -> ranking -> writing -> rendering -> uploading -> previews sent. Tracker advances.
7. On finish: job `succeeded`, tracker shows topic title, category, "Review in Posts" button; Telegram previews were sent; slot board turns `Generated (pending approval)`.
8. Admin reviews/approves in Posts or Telegram (unchanged flow).

### 3.2 Custom topic
Same as 3.1 with Topic filled. Category defaults to Auto (Gemini classifies is NOT done; require category when topic is given, default to "Dev"? - see OQ4; recommended: category required when topic given). Duplicate check runs in the API (fast, against recent titles, fuzzy) and again in the pipeline.

### 3.3 Failure and retry
Job `failed` -> tracker shows reason class (quota, source fetch, render, upload, unknown), "Retry" (pre-filled new request, new id; counts toward cap) and links to GitHub run and Logs.

### 3.4 State and edge-case matrix

| # | Situation | Detection | UI behaviour |
|---|---|---|---|
| E1 | `GITHUB_DISPATCH_TOKEN` not set | `GET /generate/config` -> `dispatch_configured=false` | Form disabled; banner "Generation can't be started from the dashboard until the GitHub token is configured. Scheduled runs still happen." with link to setup docs. No job row created. |
| E2 | Token invalid/expired/insufficient (401/403/404 from GitHub) | dispatch response | Job row not created (or marked `failed` with reason `dispatch_rejected`); message "GitHub refused the request (token expired or missing Actions permission)". No secret or raw body shown. |
| E3 | A job is already active (queued/running) | DB lookup | Form disabled; tracker shown; message "A generation is already running (started HH:MM by X)". API returns 409 with the active job id. |
| E4 | Workflow running from cron-job.org/scheduled trigger, not from dashboard | GitHub runs list (workflow_dispatch/schedule events) + job rows created by workflow | Treated as active; same as E3. |
| E5 | Slot already has a post | posts table `publish_at` match | Slot board shows `Generated`; form's slot option shows "(already has a post)"; selecting it requires the "extra post" checkbox + confirm; otherwise 409 `slot_taken`. |
| E6 | Slot passed <=12h | slot time vs now | Allowed with warning "This slot has passed; the post will publish as soon as you approve it". |
| E7 | Slot passed >12h | same | Option disabled unless "extra post/force" ticked, with warning. (Default: offer "Next available" instead.) |
| E8 | Topic duplicates a recent/posted topic | API fuzzy match (normalised title equality or high similarity vs `recent_titles` + posted) | Inline warning "Looks like '<title>' (posted DD Mon)". Allow override with checkbox (reasoning: admin may want a new angle). Pipeline must also not silently drop it. |
| E9 | Gemini quota exhausted / all fallback models fail | pipeline catches `llm` failure; job `failed`, `failure_reason=quota` | Banner "Gemini free quota exhausted - try again after midnight Pacific (about 12:30 IST) or tomorrow". Disable Generate for 1h after a quota failure unless user confirms. Telegram failure notice already exists (main.py). |
| E10 | GitHub API rate limit when polling status (403/429 with `x-ratelimit-remaining: 0`) | response headers | Keep last known state, show "Status temporarily unavailable, retrying" and back off using `retry-after`/reset. Poll no faster than every 10s; share one server-side cache (TTL 5s) so multiple tabs don't multiply calls. |
| E11 | Dispatched but no run appears within 90s | reconcile fails | Job -> `failed` reason `not_started` ("GitHub did not start the run"), with advice to check Actions; no auto re-dispatch (avoid duplicates). |
| E12 | Run queued behind poll job (concurrency group) | run status `queued`/`pending` | Show "Waiting for another job to finish (up to ~N min)". If cancelled by GitHub superseding it (R1) -> `cancelled` reason `superseded`, offer Retry. |
| E13 | Run failed/timed out (40 min) | conclusion `failure`/`timed_out` | `failed` with reason class; Telegram already notified by pipeline. |
| E14 | Pipeline ran but produced nothing (slot taken / stale skip, exit 0) | workflow reports `skipped:<reason>` | Job `skipped` (not "succeeded") with the reason; this is the case today where exit 0 hides a no-op. |
| E15 | Lost connection / API 5xx on submit | network error | Do not retry automatically; on next load, list shows whether the request was recorded (idempotency key from client prevents double submit). |
| E16 | Double click / two tabs | client disables button; server unique active job + idempotency key | Second request gets 409. |
| E17 | Daily cap reached | count of dashboard requests today (IST) | Disabled with "Daily limit (4) reached; resets at 00:00 IST". Scheduled runs do not count. |
| E18 | Chromium/FFmpeg problems, Cloudinary down | pipeline exception | `failed` reason `render`/`upload`. Partial files are not sent to Telegram (must remain true). |
| E19 | Empty state (no requests ever) | - | "No generation requests yet" with explanation and primary button. |
| E20 | `PUBLISH_ENABLED=false` / Telegram sync off (dev env) | config endpoint | Info chip "Publishing disabled in this environment"; generation still allowed. |
| E21 | Run succeeded but DB write of resulting post ids failed | job has no `post_ids` | Show `succeeded (post link unavailable)` with link to Posts filtered by date. |

## 4. Requirements

### 4.1 Functional (FR)

**Slot board**
- FR-1 The page shall list, for today and tomorrow (IST), every slot from `post_times_ist`, read from server config, not hard-coded in the UI.
- FR-2 Each slot shall show exactly one of: Generated, Generating, Missing (upcoming), Missing (passed <=12h), Missing (passed >12h), Failed (last attempt), Skipped.
- FR-3 A Generated slot shall link to its post group in Posts and show the status of its reel and carousel.

**Request**
- FR-4 The form shall offer: slot, category (Auto + the six configured categories), optional topic (5-120 chars), optional source URL (https, <=500 chars), optional "allow extra post" flag.
- FR-5 The API shall reject unknown categories, slots not in config, topics with control characters, non-https or private-network URLs (422) and shall strip/escape all values before passing them to the workflow (no shell interpolation of user text, see 5.3).
- FR-6 If a topic is given and category is Auto, the API shall return 422 (MVP) - category required with custom topic (see OQ4).
- FR-7 Submitting shall show a confirm dialog summarising the parameters and the "nothing is published until you approve" statement.
- FR-8 The API shall create the job row before dispatching and shall dispatch exactly once per request (idempotency key).
- FR-9 The API shall refuse (409) when another job is non-terminal, the slot is taken without the extra flag, or the daily cap is reached; each with a distinct machine code and human message.
- FR-10 If dispatch fails, the job shall be marked failed with a reason code and no run link; the user sees a clear message.

**Tracking**
- FR-11 The UI shall poll job status (5-10s while active; 60s otherwise; none when tab hidden) and show status, phase, elapsed time, and GitHub run link once known.
- FR-12 Status vocabulary: `queued`, `running`, `succeeded`, `failed`, `skipped`, `cancelled`. Phase vocabulary: `starting`, `fetching_topics`, `ranking`, `writing`, `rendering`, `uploading`, `sending_previews`, `done`.
- FR-13 On `succeeded`, the tracker shall show topic, category, and links to resulting posts; on `failed` a reason class and message; on `skipped` the skip reason.
- FR-14 Jobs created by scheduled/cron-job.org runs shall appear in the same list with trigger `scheduled`.
- FR-15 A job stuck non-terminal beyond 45 minutes (workflow timeout is 40) shall be reconciled against GitHub and marked failed/`timed_out` if the run is gone or finished (covers a crashed runner that never reported).

**Guardrails**
- FR-16 Max one non-terminal job at a time (DB-enforced, e.g. partial unique index).
- FR-17 Dashboard daily cap configurable via env (default 4 per IST day); scheduled runs excluded.
- FR-18 After a `quota` failure, new dashboard requests show a warning and require explicit confirmation for 60 minutes.
- FR-19 Dispatch cooldown of 60 seconds between requests per user.

**Cross-links**
- FR-20 Post panel shall show the generating request (if any); Generate shall link to Posts for review; Regenerate-from-feedback stays in Posts and its resulting poll-job runs are shown in Recent requests as type `regenerate` (nice-to-have; if cost is high, defer).

**Safety**
- FR-21 Generation shall never publish. Items are created `pending`; no code path in the Generate API or workflow may call publish.
- FR-22 Custom topics shall go through the same Gemini technical-accuracy review pass as ranked topics; the UI shall state that the admin remains responsible for accuracy review before approval.

**Audit**
- FR-23 Events (to `activity_log`): `generate.requested` (actor, params), `generate.started` (run id), `generate.finished` (post ids, duration), `generate.failed` (reason class, message<=300 chars), `generate.skipped`, `generate.cancelled`; each with `source="generate"` and `detail.request_id`. Level `error` for failed, `warning` for skipped/quota.

### 4.2 Non-functional (NFR)

- NFR-1 Latency: Generate page initial data <1s p95 (DB only, no GitHub call on load beyond cached status); submit returns <3s (one DB write + one GitHub call, 20s timeout already used).
- NFR-2 Security: GitHub token and all secrets stay server-side; API never returns tokens, GitHub response bodies, or env values. Endpoints behind the existing session auth + CSRF/rate-limit (`api/app/ratelimit.py`). Rate limit generate POST (e.g. 5/min/user).
- NFR-3 Input safety: user text is passed via workflow inputs and read in the job through `env:` variables, never inlined into shell (`${{ inputs.topic }}` in `run:` is a script-injection vector; today's workflow already inlines `inputs.category` - fix as part of this work).
- NFR-4 Least privilege: dispatch token fine-grained to this repo, `Actions: read & write` only, no contents write. Document rotation.
- NFR-5 Accessibility: WCAG 2.1 AA; form labels and error text associated; status conveyed by text not colour alone; live region (`aria-live=polite`) for phase changes; dialogs trap focus (shadcn); keyboard-complete.
- NFR-6 Mobile: usable at 360px width; form and tracker stack vertically; tables collapse to cards; tap targets >=44px.
- NFR-7 Reliability: polling failures never break the page; stale data is labelled with "as of" time.
- NFR-8 Timezone: all times shown in IST with explicit label; stored UTC.
- NFR-9 Cost: no extra Actions minutes spent by merely viewing the page; status polling uses cached GitHub calls only while a job is active.
- NFR-10 Observability: every job has request_id traceable across dashboard, workflow run-name, DB, Logs and Telegram failure messages.

## 5. Data and API (plain language)

### 5.1 What must be stored: "generation_jobs" (new table)
- `id` (request id, short unique string), `created_at`, `updated_at`
- `trigger`: dashboard | scheduled | regenerate
- `requested_by` (admin identity; null for scheduled)
- `params`: slot (timestamp of target slot), category, topic, source_url, force flag
- `idempotency_key` (unique)
- `status`, `phase`, `failure_reason` (quota | fetch | rank | write | render | upload | telegram | dispatch_rejected | not_started | timeout | unknown), `message`
- `github_run_id`, `github_run_url`, `started_at`, `finished_at`
- `topic_title`, `topic_category` (what was actually generated)
- `post_group_id` / resulting item ids
- Partial unique index: only one row with status in (queued, running).
Retention: 90 days (prune alongside activity prune in poll).

### 5.2 API (all behind login)
- `GET /generate/config`: slots, categories + weights, dispatch_configured, daily cap and used today, publish/telegram flags. Never secrets.
- `GET /generate/slots?days=2`: slot board data (slot, state, linked group, last job).
- `POST /generate`: create request (body = params + idempotency key). Returns job. Errors: 409 `job_active` | `slot_taken` | `cap_reached`; 422 validation; 502 `dispatch_failed`; 503 `not_configured`.
- `GET /generate/jobs?limit=20` and `GET /generate/jobs/{id}`: list/detail. Detail triggers (cached 5s) a reconcile against GitHub if non-terminal.
- (Later) `POST /generate/jobs/{id}/cancel`.

### 5.3 Workflow changes to daily-generate.yml (for the developer)
- New `workflow_dispatch` inputs: `topic` (string), `source_url` (string), `request_id` (string); keep `slot`, `category`, `dry_run`, `force`. (GitHub allows max 10 inputs; we use 7.)
- `run-name: "Generate ${{ inputs.request_id || github.event_name }}"` so the API can find the run (dispatch returns no run id): list runs for the workflow filtered by `event=workflow_dispatch` created after the request time and match name.
- Pass inputs through `env:` and quote them in the shell step; add `--topic`, `--source-url`, `--request-id` to `main.py generate` (new args; `--topic` skips rank, still runs duplicate check and `gen_content`).
- Remove the 2h/12h comment drift; slot choice list must stay in sync with `post_times_ist` (consider a free-text `slot` validated by main.py instead of a fixed choice).
- Concurrency: keep `queue-state`; mitigate R1 (see below).
- Status reporting back to DB: `main.py generate` receives `--request-id` and writes phase/status via a small `generation_jobs` helper (same DB, same `DATABASE_URL`), at: start (`running`, with `GITHUB_RUN_ID`, run URL), each phase, end (`succeeded` + post ids, `skipped:<reason>`, or `failed` + reason class). A final workflow step with `if: failure() || cancelled()` marks the job failed/cancelled if Python never got to report (OOM, install failure). The reconcile in FR-15 is the safety net when even that fails. Scheduled runs create their own job row at start (trigger=scheduled, request_id generated in-process).
- Also record the same transitions as activity events from the pipeline for `generate.started/finished/failed`; `generate.requested` is written by the API.

## 6. Acceptance criteria (MVP)

AC-1 Slot board
- Given it is 17:00 IST and the 10:00 slot has a pending reel+carousel and 19:00 has none, When I open Generate, Then 10:00 shows "Generated" with a link to the post, and 19:00 shows "Missing - upcoming".

AC-2 Happy path
- Given the token is configured, no job is active and the cap is not reached, When I submit slot 19:00, category DSA and confirm, Then a job row `queued` is created, the workflow is dispatched once with `request_id`, a `generate.requested` event appears in Logs, and the tracker shows `queued` within 3s.
- Given the run starts, When the pipeline reports phases, Then the tracker advances through each phase in order and shows the GitHub run link.
- Given the pipeline finishes, When previews are sent, Then the job is `succeeded`, links to the new post group, `generate.finished` is logged, and the new items have status `pending`.

AC-3 No publishing
- Given any generation completes (success or failure), When I inspect the posts, Then none has status `approved`/`publishing`/`published` as a result of it.

AC-4 Active job
- Given a job is `running`, When I open Generate or try POST /generate, Then the form is disabled with the active job's details and the API returns 409 `job_active`.

AC-5 Double submit
- Given I double-click Generate, When both requests reach the API, Then exactly one job and one dispatch exist.

AC-6 No token
- Given `GITHUB_DISPATCH_TOKEN` is unset, When I open Generate, Then the form is disabled with the configuration message, the slot board and history still load, and no request can create a job.

AC-7 Slot taken
- Given slot 10:00 already has a post, When I choose 10:00 without ticking "extra post", Then submission is blocked with `slot_taken`; When I tick it and confirm, Then the job runs with force.

AC-8 Duplicate topic
- Given a topic matching a post from 3 days ago, When I type it, Then I see the duplicate warning with date, and submission needs an explicit override.

AC-9 Quota
- Given Gemini returns quota errors on all models, When the run ends, Then the job is `failed` with reason `quota`, the banner explains the retry window, `generate.failed` (level error) is logged and no partial previews were sent.

AC-10 Run failure/timeouts
- Given the runner dies before reporting, When 45 minutes pass or the run is seen finished on GitHub, Then the job becomes `failed` with a reason and the form is re-enabled.

AC-11 GitHub rate limit
- Given GitHub returns a rate-limit response while polling, Then the UI keeps the last state labelled "as of HH:MM", backs off, and recovers without a page reload.

AC-12 Skipped run
- Given the workflow exits 0 because the slot was taken by another trigger, Then the job shows `skipped` with the reason, not `succeeded`.

AC-13 Cap
- Given 4 dashboard requests today (IST), When I open Generate, Then the form is disabled showing the reset time; scheduled runs are not counted.

AC-14 Security
- Given a browser session, When I inspect network responses and HTML, Then no token, secret, or raw GitHub error body is present; and a topic containing shell metacharacters (`"; rm -rf /`) is treated as plain text end to end.

AC-15 Accessibility/mobile
- Given a 360px viewport and keyboard only, Then the whole flow (open, fill, confirm, track) is operable, errors are announced, and status is readable without colour.

AC-16 Scheduled runs visible
- Given cron-job.org triggers the 19:00 run, Then a `scheduled` job appears in Recent requests and the slot board reflects it.

## 7. Risks, open questions, "live" checklist

### 7.1 Risks
- R1 Concurrency supersede: with `queue-state` group, a pending generate can be dropped when a newer run queues (poll runs are dispatched often). Mitigation options: (a) give Generate its own group and make the DB claim the real lock (state commits race only in file mode; production uses Postgres), (b) detect `cancelled` and offer Retry (MVP minimum). Recommend (a) after dev confirms DB mode is production-only; flag as dev decision.
- R2 Run correlation by run-name is best-effort; clock skew/parallel dispatches can mismatch (mitigated by one-active-job rule and request_id in name).
- R3 Gemini free-tier exhaustion competes with scheduled runs: extra manual posts can starve the 19:00 scheduled post. Cap + warning mitigate; consider a reserve rule (OQ3).
- R4 Actions minutes: each run ~5-10 min with Chromium install (`--with-deps`); 4 manual + 2 scheduled/day is ~60 min/day, ~1,800/month (free private-repo allowance is 2,000; public repos unlimited). Confirm repo visibility (OQ5).
- R5 Prompt-injection / bad content: a custom topic or URL can steer Gemini; the review pass reduces but does not remove inaccuracy. Human approval remains the control.
- R6 Token blast radius: a dispatch token can run workflows that hold production secrets; keep repo-scoped, no contents write, rotate every 90 days; never display it.
- R7 Status drift: job row says running while GitHub says done; handled by FR-15.
- R8 Production migration runs automatically via the workflow (`alembic upgrade head`) - a new table goes live on the next run of any workflow once merged to main.
- R9 Time handling: slot "tomorrow" generation relies on `--date` default `date.today()` in the runner (TZ set to Asia/Kolkata); verify the tomorrow-slot case (`slot_at(day, slot)` with the runner's date) before offering it. MVP can offer today's slots plus "Next available" only.

### 7.2 Open questions for the product owner (recommended default in bold)
- OQ1 Who may use Generate: only the admin login? **Yes, admin only; role check centralised for future.**
- OQ2 Daily cap for dashboard-initiated runs? **4 per day (on top of the 2 scheduled).**
- OQ3 Reserve capacity so manual runs cannot block scheduled slots (e.g. block manual runs 07:30-08:30 and 18:00-19:00 IST)? **No block, but warn when within 60 min before a scheduled trigger.**
- OQ4 Custom topic without category: auto-detect via Gemini or require category? **Require category in MVP (no extra Gemini call).**
- OQ5 Is the GitHub repo public or private (Actions minutes budget)? **Assume private/2,000 min; show cap accordingly.**
- OQ6 Should an extra post (slot already has one) be allowed at all, and publish at the same slot time? **Allowed with confirmation; it gets the slot time and the admin may reschedule in Posts.**
- OQ7 Source URL: acceptable that MVP does NOT read the page (only passes the link as a source reference)? **Yes; label it clearly. Reading pages is Later.**
- OQ8 Allow duplicate-topic override? **Yes, with explicit checkbox.**
- OQ9 Is Telegram preview still the preferred review channel, with Generate only deep-linking to Posts? **Yes.**
- OQ10 Retention of job history? **90 days.**
- OQ11 Should "Generate" also cover the Regenerate runs (poll workflow) in its history? **Show later; MVP shows only generate workflow runs.**

### 7.3 "What live requires" checklist
Owner approval is required before any of items 3-6 (deploy and production DB migration are NOT to be done by the developer on their own).
1. Dev work complete with tests (API, pipeline reporting, UI) and local verification against a throwaway DB, never the production Neon DB.
2. Create/rotate GitHub fine-grained PAT: repo-scoped, `Actions: read+write`; set `GITHUB_DISPATCH_TOKEN` (and `GITHUB_REPOSITORY`) in the Lambda environment. (Already referenced by `actions.trigger_pipeline_run`; confirm it exists in prod and has read permission, since poll status needs `actions:read`.)
3. OWNER APPROVAL: alembic migration for `generation_jobs` (reviewed SQL; take a Neon backup/branch first). Note the workflows auto-run `alembic upgrade head`, so merging to main effectively applies it - sequence the Lambda deploy so the API is deployed before or together with the table.
4. OWNER APPROVAL: merge/deploy of updated `daily-generate.yml` (new inputs, run-name, env-based input handling) - also check cron-job.org payloads still match (they send `slot`).
5. OWNER APPROVAL: deploy API (Lambda image) and web (set sidebar `ready: true` for Generate).
6. Env/config: `GENERATE_DAILY_CAP`, and the DB connection from the workflow (`DATABASE_URL` secret already present).
7. Smoke test in production (owner present): dry-run request via workflow, then one real request for a future slot; confirm Telegram preview, tracker, Logs events; confirm no publication without approval.
8. Rollback plan: revert workflow file; sidebar back to "soon"; table can remain unused.

## 8. Suggested build order

1. Migration + model `generation_jobs` + helper module (`src/generation.py`: create, update phase, finish, reconcile) with unit tests (partial unique index, idempotency).
2. `main.py generate`: new args (`--topic`, `--source-url`, `--request-id`), phase reporting, `skipped` outcomes, custom-topic path that skips ranking but keeps duplicate check; tests with `--dry-run` and mocked Gemini.
3. `daily-generate.yml`: new inputs, `run-name`, env-based inputs (fix injection), failure/cancel reporting step, scheduled-run job rows; test via dry-run dispatch in a fork or with `dry_run=true`.
4. API `routes/generate.py`: config, slots, POST, jobs list/detail, GitHub run lookup/reconcile with cache and rate-limit handling; activity events; tests with mocked GitHub (204, 401, 403 rate limit, no run found).
5. Web: `pages/Generate.tsx` (slot board, form + confirm, tracker, history), `lib/generate.ts`, reuse `ProgressTrack`/`StatusBadge`; empty/error states; mobile + a11y pass; Playwright tests in `web/tests/`.
6. Cross-links in Posts panel; Logs filter by `source=generate`.
7. Flip sidebar `ready: true` only at go-live (after the owner-approved steps in 7.3).
