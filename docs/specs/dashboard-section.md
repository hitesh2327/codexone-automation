# Spec: Dashboard section ("/dashboard")

Status: Draft for owner review | Author: BA (Bruce Banner) | Date: 2026-10-05
Related: Posts, Logs, Profile (built); Generate (`docs/specs/generate-section.md`, in progress). Not duplicated here: slot logic, generation jobs and their states are owned by Generate; Dashboard only reads them.

## 0. Evidence base (what exists today, verified in code)

| Fact | Source |
|---|---|
| 1 topic = 1 carousel item + 1 reel item (`posts` rows, own status each); `group_id` = "<date>/<slug>" ties them and their regenerations. 2 topics/day (slots 10:00, 19:00 IST) = 4 posts and 6 platform deliveries per day (carousel -> IG; reel -> IG + YT). | `brand/config.yaml`, `queue_store.Item` |
| Status flow: pending -> approved -> publishing -> published; also rejected, regenerate -> replaced, failed (retry until MAX_ATTEMPTS), expired (36 h without a decision). | `queue_store.py`, `main.py` (EXPIRE_HOURS) |
| Per post: `created_at`, `decided_at` (OVERWRITTEN on every re-approve/reschedule/revive), `publish_at` (slot), `published_at` (first successful platform only), `version`, `attempts`, `error`, `category`, `media` (Cloudinary URLs). | `models.Post` |
| Per platform result in `posts.platforms`: `{status: published/failed/skipped, id, url, error<=300 chars, at, attempts, privacy}`. IG url = permalink, YT url = youtube.com/shorts/<id>. Same data copied to `posted_topics`. | `publish.py` |
| `activity_log` (90-day retention): `post.generated/regenerated`, `post.approved/scheduled/rejected/regenerate/feedback/expired`, `publish.requested/retry/failed/skipped/released/crashed`, `post.published`, `generate.started/finished/failed/skipped/cancelled`, `login.success/failed`, `logout`. Levels info/warning/error. `actor` can hold an email; `message` can hold error text. | `src/activity.py`, call sites |
| `generation_jobs` (90-day retention): status, phase, `failure_reason` (incl. quota), trigger dashboard/scheduled, timings, resulting post ids. Table is NEW and unmigrated in production, so it is empty until go-live. | `models.GenerationJob`, Generate spec |
| `settings` table can hold brand config ("was brand/config.yaml"); weights today: AI 30, SystemDesign 20, DSA 20, Interview 15, OS 10, Dev 5. | `models.Setting`, `config.yaml` |
| Existing logs endpoint `/logs/summary` already gives 24 h level counts, last error, last publish. | `routes/logs.py` |
| Posts API loads ALL rows including captions via `q.load()` and groups in Python. Fine for Posts; too heavy for a landing page. | `routes/posts.py` |
| Web stack: React 19, Tailwind 4, shadcn/radix, sonner, lucide, react-router. NO react-query and NO chart library; pages use `useEffect` + `setInterval` polling (Logs). Visual language: `stage.ts` tones wait/go/ok/bad/idle, `StatusBadge`, `ProgressTrack`, brand CSS vars `--brand-*` loaded from `/api/public/brand`. | `web/package.json`, `Logs.tsx`, `stage.ts`, `brand.ts` |
| Lambda: 1024 MB, 30 s timeout, container image, Neon Postgres. Sidebar entry `/dashboard` is `ready: false`. | `infra/template.yaml`, `app-shell.tsx` |
| Credentials: IG Instagram-Login token (publish + `me`, `content_publishing_limit`, media `permalink`); YT OAuth with ONLY scope `youtube.upload`. No stored engagement data anywhere. | `publish.py`, `publish_youtube.py` |

Not present (so NOT promised): any reach/likes/views/followers number, per-post cost, "hours saved", multi-brand/multi-tenant, optimised posting times (slots are fixed config), poll-run heartbeat, token-expiry date, Gemini quota remaining.

## 1. Purpose, audiences, 10-second test

**Purpose.** One screen that answers "is my content operation healthy, what needs me, what is going out, and what has it delivered?" - truthfully, from data the system already records.

**Audiences.**
1. Owner (daily, 30 s on phone): "anything for me to do? is today going out?"
2. Prospective customer (demo, 3 min): "this runs my social presence reliably, I stay in control, I can see everything."
3. Later: a team (editors approving, a manager reviewing). Design for read-by-many, act-by-few; actor names masked (see 4.3).

**10-second test (must be true without scrolling at 1280x720 and on the first phone screen).**
- A single sentence of state: "All good: 4 posts live today, next goes out at 19:00 (in 3h 12m)" or "2 things need you".
- A needs-attention count with the top item and a button.
- 4 headline numbers, each with its denominator and window: Posts published, Approval rate, Publish success rate, Median time to approve.
- Where the next posts come from: the next two slots with their state.
Everything else supports the story below the fold.

## 2. The story and the widgets

Order on screen = order of the story: **Today at a glance -> What needs me -> What's going out next -> How the engine performs -> What has shipped.**

Global rules: window selector 30 / 90 days (default 30; applies to rate/mix/funnel widgets, not to "needs attention" or "next slots", which are always now). All days are IST. Every rate shows `n` (e.g. "86% (31 of 36)"). A rate with n < 10 shows the numbers but no colour judgement and the note "too few to judge". "Post" = one item (reel or carousel); "topic" = one group. Auto-refresh every 60 s while the tab is visible; "as of HH:MM IST" label and a refresh button; stale data stays visible on error.

### Band A - Today at a glance

**W1 Status line + KPI tiles**
- Question: is it healthy, and what has it delivered?
- Status line rule (first match wins): red "Action needed" if any needs-attention item has severity high; amber "Heads up" if any medium; else green "All running". Text always spells the reason; colour is never the only signal.
- Tiles (window-based; each tile has a text sub-line):
  1. **Posts published** = count of posts with status `published` and `published_at` in window; sub-line "N topics, M platform deliveries".
  2. **Approval rate** = approved-ever / decided. approved-ever = status in {approved, publishing, published, failed} (failed implies it was approved); decided = approved-ever + rejected + regenerate + replaced. Pending and expired are excluded from the denominator and shown separately ("3 expired = no decision"). Sub-line: "first-pass: X%" = same formula restricted to `version = 1`.
  3. **Publish success rate** = platform deliveries with final status `published` / (published + failed), over targets of posts that reached a final publish state in window; `skipped` excluded and listed ("1 skipped: YouTube not configured"). Sub-line: "first attempt: X%" = `published` with `attempts = 1` over the same denominator.
  4. **Median time to approve** = median of `decided_at - created_at` for approved-ever posts created in window (p90 in the sub-line). Caveats (shown in an info tooltip): `decided_at` is the LAST decision, and Telegram button presses are stamped when the poll runs (up to ~20 min after the tap). Treat as an upper bound.
  5. (Fifth tile, desktop only) **Punctuality** = published posts where `published_at - max(publish_at, decided_at) <= 30 min` / published posts. The `decided_at` clamp means a post you approved late is not blamed on the system. 30 min = poll cadence (15-20 min) plus margin; configurable constant.
- Source: `posts` (narrow columns only). Refresh: 60 s. Empty: "No posts in this period yet" + link to Generate. Error: tile shows "-" with "couldn't load".

### Band B - What needs me

**W2 Needs-attention queue** (always "now", not windowed; max 8 shown, "+N more")
- Question: what is waiting for my action, most urgent first?
- Items, each with severity, age, one primary action that deep-links to Posts (Posts must accept `?status=` / `?group=`; verify, small change if not):

| Condition (exact) | Severity | Text example |
|---|---|---|
| `status = failed` and every failed platform `attempts >= MAX_ATTEMPTS` (giving up) | high | "YouTube failed 3x: <short reason>. Retry" |
| `status = failed` still retryable | medium | "Retrying automatically at next poll" |
| `status = approved` and `publish_at + 30 min` passed (poller not publishing) | high | "Approved 10:00 post not published yet (45 min late)" |
| `status = publishing` and `updated_at` older than 30 min | high | "Publishing seems stuck" |
| `status = pending`; severity high when remaining time to expiry < 6 h (expiry = created_at + 36 h), else medium if its slot has passed, else low | per rule | "Reel 'X' waits for approval; slot 19:00; expires in 5h" |
| `status = expired` in last 7 days | low | "Expired unapproved; revive or ignore" |
| A slot that has passed with no non-replaced post (uses Generate's `slot_state`) | high if < 12 h ago | "10:00 slot has no post" |
| Latest `generation_jobs` failed (24 h), with `quota` called out | medium | "Generation failed: Gemini quota" |
| YouTube auth failure in a recent `publish.failed` (error text contains "refresh token rejected") | high | "YouTube login expired; reconnect" |
| Instagram token problem (error 190 / "token" in latest IG failure) | high | "Instagram token rejected" |

- Honest limit: there is NO stored token-expiry date, so "token expires in N days" is NOT shown today (Phase B: `refresh_token.py` writes `token.refreshed` / `token.failed` events; then show "last refreshed 3 days ago").
- Empty (best state, make it nice): green check "Nothing needs you. Last decision 2h ago."
- Error: "Couldn't check. Open Posts" (never claims all-clear when the query failed).

**W3 Next slots timeline** (next 4 slots, today and tomorrow)
- Question: what is going out next and is it ready?
- Per slot: time IST, countdown, topic + category if generated, one chip each for reel and carousel using `stageOf()` titles (Waiting for approval / Approved / Publishing / Live / Failed), or "Not generated yet" (+ "generation starts ~HH:MM"). Data: `posts` by `publish_at`, slot list from server config, state from `src.generation.slot_state`. Empty: "No upcoming slots configured" (config error).

### Band C - How the engine is performing

**W4 Cadence heatmap** (30 or 90 days; 7 rows x N weeks grid, SVG/CSS)
- Question: do we ship every day?
- Cell = IST day; value = number of posts with `published_at` that day (0..4 normally). States: full (>= expected = 2 x slots), partial, none-while-expected (outlined, "missed"), no-expectation (future/before first post, neutral). Tooltip + keyboard focus: "Tue 29 Sep: 4 of 4 published (2 topics)". Header: "27 of 30 days fully published; current streak 12 days" (streak = consecutive full days ending yesterday or today if complete).
- Text alternative: a visually hidden table/summary of the same figures. Empty: first-day message.

**W5 Content mix vs target**
- Question: does the content follow the strategy?
- Count TOPICS (groups, using their non-replaced current version) per `category` in window; share % vs configured `topics_weight` (read via server `load_brand()` / settings, never hard-coded). Render horizontal bars with a target tick; delta text "DSA 28% vs target 20% (+8)".
- Honesty: targets are applied as weighted random selection that avoids repeating the last category, so short windows deviate by chance. Show "n = 24 topics; expect +/- 10 points at this size" and suppress deviation colouring below n = 20.

**W6 Funnel (generated -> approved -> published)**
- Question: how much of what the AI makes becomes a live post, and why does the rest drop?
- Stages over posts created in window: Generated (all rows incl. regenerated versions) -> Decided -> Approved -> Published; side-leak counts: rejected, regenerated (replaced+regenerate), expired, failed-final, still pending. Every post lands in exactly one bucket (reuse `bucketOf` idea; add `rejected`, `regenerated`, `expired`). Bars sum to total; show counts and %.
- Note: "Regenerated" shows how much the human steers quality; present as control, not failure.

**W7 Approval turnaround**
- Question: how fast do I (or my team) respond?
- Median / p90 and a 5-bin histogram (< 30 min, < 2 h, < 6 h, < 24 h, >= 24 h) of the W1 tile-4 data, split by decision channel when derivable (dashboard vs Telegram from `activity_log` `source`, within its 90-day retention). Same caveats as W1.

**W8 Pipeline health**
- Question: is the engine itself reliable?
- Generation: from `generation_jobs` in window (this includes scheduled runs): succeeded / (succeeded + failed) (skipped and cancelled excluded and listed), last run time + result, last failure reason class, current success streak (consecutive succeeded since last failed). **Slot fill rate** = slots in window (elapsed only) with >= 1 non-replaced post / elapsed slots. This works from `posts` alone, so it has data from day 1 even though `generation_jobs` is empty before go-live; the job-based figures show "tracking since <date>".
- Publishing: last successful publish time (from `posts.published_at`), failed deliveries in window.
- "Last poll run": NOT available (no heartbeat). Use the overdue-approved check in W2 as the symptom-based substitute; heartbeat is a Phase B option (see 5.2).
- Empty/error as W1; each sub-figure fails independently.

### Band D - What has shipped

**W9 Platform results**
- Question: where did it land, can I open it?
- Two columns (Instagram, YouTube Shorts): published count, failed count, skipped count, success rate (W1 definition per platform), last 5 published with link (`platforms[p].url`). Links open in a new tab with `rel="noopener noreferrer"`; only https URLs on instagram.com / youtube.com are rendered as links (else plain text). YouTube rows show the privacy value (`private/unlisted/public`) because the default is `private` and a private video is not public (flag it so nobody claims it is).

**W10 Recently shipped (gallery)**
- Last 8 topics: first carousel slide thumbnail (from `media.carousel[0]`, public Cloudinary URL; skeleton if missing), topic, category, platforms with status, time. Clicking opens that post in Posts. Reel thumbnails are not guaranteed to exist; do not promise them.

**W11 Recent activity feed**
- Last 15 events from `activity_log` where event is in a curated allowlist (`post.generated`, `post.approved/scheduled/rejected`, `post.published`, `publish.failed`, `post.expired`, `generate.finished/failed`). Excluded: login.*, logout, feedback text. Actor shown as role label ("You", "Telegram", "System"), never email; message truncated to 140 chars and passed through the existing scrub. "View all" -> Logs. Empty: "Activity will appear here".

**W12 Engagement (see 2.1)** - Phase B. Until built, a single quiet roadmap tile, not fake numbers.

### 2.1 Engagement analytics: what is feasible

| Signal | Source | Token / scope needed | Available now? | Cost / limits |
|---|---|---|---|---|
| IG likes, comments count, timestamp per media | `GET graph.instagram.com/v21.0/{ig_media_id}?fields=like_count,comments_count,timestamp,permalink` | basic read, already implied by the working token (`me`, `permalink` calls succeed) | Likely YES (verify with a 10-minute spike on the real token) | Free; well under rate limits at ~200 media |
| IG reach, saves, shares, views (reels), total interactions | `GET /{ig_media_id}/insights?metric=...` | `instagram_business_manage_insights`; NOT evidenced in repo; current token may lack it | UNKNOWN: needs spike; if missing, re-authorise (new token flow, owner action) | Free. Metric names changed between API versions (impressions/plays -> views): pin to v21 behaviour in the spike. Insights exist only for business/creator accounts |
| IG follower count (daily snapshot) | `GET /me?fields=followers_count` | basic | Likely YES | Free; this is the only way to chart growth, and history starts the day we begin snapshotting |
| YT views, likes, comments per Short | `videos.list?part=statistics&id=<up to 50 ids>` | needs `youtube.readonly` (or force-ssl); today's token has ONLY `youtube.upload` | NO: needs re-consent via `get_yt_token.py` and a new `YT_REFRESH_TOKEN` | 1 quota unit per call (default 10,000/day; an upload costs 1,600). Free |
| YT watch time, retention | YouTube Analytics API | `yt-analytics.readonly` + extra consent | Later | Free but more setup |

Design if built (Phase B): never call IG/YT from the dashboard request. A scheduled job (reuse poll or a daily workflow) snapshots metrics into a new `post_metrics` table for posts published in the last 30 days at roughly +1 d, +3 d, +7 d, +28 d, plus a daily `account_snapshots` row (followers). The dashboard reads only those tables. Show "as of <snapshot time>" and per-post deltas. Risk to state: a young account gives small numbers, and YouTube `private` uploads show nothing meaningful.

**MVP recommendation.** Phase A ships W1-W11 and the Demo workspace, all from existing tables, no new credentials, no new cost. Phase B (after a spike confirms scopes) adds IG likes/comments + followers first, then YT views. Do not show engagement placeholders with numbers anywhere, including the demo, until real integration exists (section 3).

## 3. Demo strategy (selling)

**Principle.** The demo must show true capabilities with clearly synthetic data, and the owner must be able to say "this exact screen, computed by the same code, runs on my real account".

**Demo workspace design**
- A toggle in the Dashboard header: segmented control `Live | Demo workspace`. Default Live. Selection kept in `sessionStorage` only (resets on a new session, so the owner cannot leave it on by accident); `?workspace=demo` in the URL also works for rehearsal.
- Implementation rule: the backend builds synthetic `Post`-shaped and `ActivityLog`/`GenerationJob`-shaped rows IN MEMORY (deterministic generator seeded by a constant; dates relative to today so it is always fresh) and passes them through the SAME aggregation function as live data. No rows written to Postgres, no change to `posts`, `posted_topics`, `activity_log`, `generation_jobs`; no code path from demo to publish, Telegram, Cloudinary, GitHub or Gemini. Demo is read-only: every action button is disabled with the tooltip "Sample data - actions are off". The generator lives in one module and is covered by a test asserting zero DB writes.
- Guardrails against being mistaken for real numbers:
  1. Persistent, non-dismissible top banner: "DEMO WORKSPACE - sample data, not a real account" in the accent colour; also in the browser tab title ("[DEMO] Dashboard") and a "SAMPLE" corner mark on each card.
  2. Fictional handle (e.g. "@demo_dev_daily"), not the real brand; no real names, emails, topics from real posts, thumbnails, Cloudinary/IG/YT URLs. Links in demo rows are disabled (no `href`) and IDs are prefixed `demo-`.
  3. Topics are fictional but technically correct (the repo rule "no clickbait lies" applies to demo content too); reviewed once by the owner.
  4. Realistic, unglamorous numbers: roughly 80-85% approval, a few rejections and regenerations, 2 expired, 2 failed publishes that recovered on retry, one quota-failed generation, some days partially published. A flawless 100% would look fake and invite scepticism.
  5. No engagement, follower, reach or "hours saved" numbers in demo (none exist in the product). A tile "Engagement analytics - on the roadmap" is acceptable, labelled roadmap.
  6. Screenshot/print safety: the banner and SAMPLE marks are part of the page and the exported image.
- Who sees it: admins only (same auth as everything). Customers must NOT get an admin login to production (they would see the real Posts, Logs and Profile). MVP: the owner shares their screen. Later: a separate hosted read-only demo (own deployment or a `demo` role confined to this endpoint) - out of scope.
- Env switch `DASHBOARD_DEMO_ENABLED` (default true in dev, owner decides for prod): when off, the toggle is hidden and the API returns 404 for `workspace=demo`.

**3-minute demo script**
1. (0:00) Open Dashboard in Demo. Say: "This is a sample workspace with synthetic data so I can show you everything safely. The calculations are the same as on my live account."
2. (0:20) Status line + KPIs: "At a glance: how many posts went out this month, how often I approve what the AI drafts, and that publishing succeeded X of Y times."
3. (0:50) Needs attention: "Nothing is ever published without a human approval. These are the items waiting for me; one tap takes me to review. If something fails, it appears here with the reason and a retry."
4. (1:20) Next slots and heatmap: "Two scheduled slots a day; here is a month of consistency, including the days it missed."
5. (1:50) Mix vs target and funnel: "I set the strategy (30% AI, 20% DSA...). The system follows it on average, and this funnel shows what I rejected or asked to regenerate - the AI proposes, I decide."
6. (2:20) Pipeline health + activity feed: "Every action is logged: who approved, what published, what failed."
7. (2:45) Switch to Live (the owner's own account, only if comfortable): "Same screen, my real numbers." Close with next step.

**What to say is real vs sample (and what not to claim)**
- Real/provable: the workflow (trend sourcing, AI drafting with a review pass, Telegram/dashboard approval, scheduled publishing to Instagram and YouTube Shorts), the audit log, the failure handling and retries, the metrics' definitions.
- Sample: every number, topic and date in the Demo workspace.
- Do NOT claim: "fully hands-off" (human approval is mandatory by design - sell that as control); guaranteed accuracy (a Gemini review pass reduces but does not remove errors); reach, followers or growth results (not measured today); "best-time optimisation" (slots are fixed); "works for any brand/many accounts" (single-brand configuration today); "hours saved" (not measured: if the owner quotes one, it must be labelled their own estimate); YouTube public reach while `YT_PRIVACY=private`.

## 4. Requirements

### 4.1 Functional (FR)
- FR-1 `/dashboard` renders in the existing `AppShell`; sidebar entry becomes `ready: true` only at go-live.
- FR-2 One request loads all widgets (section 5); each widget renders independently when its section is `ok: false` (partial failure never blanks the page).
- FR-3 Window selector (30/90 days) re-queries once; "now" widgets (W2, W3) ignore it.
- FR-4 All metrics use exactly the definitions in section 2; each rate shows numerator and denominator; n < 10 shows "too few to judge".
- FR-5 W2 lists the conditions in the table, ordered high > medium > low, then by age; each item has a single primary action linking into Posts or Generate.
- FR-6 Status line follows the first-match rule in W1 and always includes a text reason.
- FR-7 Heatmap, mix and funnel include a text alternative (visually hidden summary or table) carrying the same figures.
- FR-8 Auto-refresh 60 s while the tab is visible; pauses when hidden; shows "as of"; manual refresh; on failure keeps last data with a "stale" label.
- FR-9 The feed shows only allowlisted events with masked actors and truncated, scrubbed messages.
- FR-10 External links: https only, host allowlist (instagram.com, youtube.com, youtu.be), `rel="noopener noreferrer"`, new tab.
- FR-11 Demo workspace per section 3: banner, read-only, in-memory, same aggregator, toggle in sessionStorage, env switch.
- FR-12 Time zone: day boundaries and labels in IST with the label "IST"; timestamps stored/returned in UTC ISO.
- FR-13 Slot times, categories and target weights come from server config, never hard-coded in the UI.
- FR-14 Empty states exist for: brand-new install (no posts), window with no posts, no `generation_jobs` yet ("tracking since go-live"), no activity.
- FR-15 The page never triggers a write, a publish, a generation or an external API call.

### 4.2 Non-functional (NFR)
- NFR-1 Performance: warm Lambda + Neon, `GET /api/dashboard/overview` p95 < 600 ms server time and page usable < 1.5 s on a normal connection; first paint shows skeletons within 100 ms. Cold start (Lambda image or Neon compute resume) may exceed this; skeletons cover it and it is measured and reported separately, not hidden.
- NFR-2 One aggregate request per load/refresh (plus brand and auth calls already made); response < 40 KB gzip-friendly JSON.
- NFR-3 Works at 360 px: tiles 2 across, widgets stack, heatmap scrolls horizontally inside its card (no page scroll), tap targets >= 44 px, bottom nav not covered (page padding exists).
- NFR-4 Accessibility (WCAG 2.1 AA): status by text + icon + colour; contrast >= 4.5:1 on the dark theme; charts are SVG/CSS with `role="img"` + `aria-label` summary and a text table equivalent; focusable heatmap cells with tooltips; `aria-live="polite"` on the status line; respects `prefers-reduced-motion`; keyboard-complete.
- NFR-5 Visuals: dark theme brand tokens (`--brand-bg #0D1117`, `--brand-primary #00E5FF`, `--brand-accent #FFB800`) via existing Tailwind/CSS variables; tone mapping reuses `stage.ts` tones (ok/go/wait/bad/idle). No chart library: heatmap = CSS grid, bars = div widths, funnel = bars, optional sparkline = inline SVG path (< 2 KB code each). Add a library only if a requirement appears that SVG/CSS cannot meet; that needs owner approval.
- NFR-6 Reliability: aggregation is read-only, idempotent, tolerant of nulls (legacy rows without `platforms`, `group_id`, `publish_at`).
- NFR-7 Testability: the aggregator is a pure function of (rows, now, config) so it is unit-testable with fixed fixtures; demo data goes through it.

### 4.3 Security and privacy
- Admin-only: the router sits under the existing `protected` dependency; demo endpoint included (no anonymous demo).
- Response whitelist: no captions, `post_dir`, `media` URLs beyond one thumbnail URL, `tg_*` ids, feedback text, `source_url`, emails, IPs, tokens, raw error bodies. Error text goes through `generation.scrub` and a 140-char cut.
- Actor masking in the feed (role labels only). `login.*` events never shown.
- No secrets or env values in any response (also not "token present: true/false" beyond a boolean needed for warnings).
- Read-only GET; no CSRF surface; rate limit with the existing limiter (e.g. 30/min/user) because the refresh loop and multiple tabs add load.
- Demo mode cannot be used to reach live data (separate code path chosen server-side from the `workspace` parameter, validated against an enum).

## 5. Data and API needs (plain language)

### 5.1 Endpoint
`GET /api/dashboard/overview?range=30|90&workspace=live|demo` returns one JSON with sections: `generated_at`, `config` (slots, categories + target weights, expected posts per day, thresholds), `kpis`, `attention[]`, `next_slots[]`, `cadence[]` (per-day counts), `mix[]`, `funnel`, `turnaround`, `pipeline`, `platforms`, `recent_posts[]`, `activity[]`. Each section carries `ok` and, on failure, a short `error`. An `ETag` + `Cache-Control: private, max-age=0` lets the browser revalidate cheaply; a 15 s in-process cache per (range, workspace) protects the DB from multi-tab refresh loops (warm Lambda only; acceptable because it is only a cache).

### 5.2 Data
Phase A needs NO new columns, tables or credentials:
- `posts`: read narrow columns only (`id, kind, group_id, category, status, version, publish_at, created_at, decided_at, published_at, attempts, platforms, error, updated_at`, plus `media` only for the first carousel URL of 8 recent topics). Scope: rows with `created_at` in window plus rows whose status is pending/approved/publishing/failed/expired in last 7 days regardless of age. Volume: ~4 rows/day, so <= ~400 rows at 90 days; aggregate in Python for exact IST bucketing and median/p90 (SQL `percentile_cont` is not needed at this size).
- `generation_jobs`: last 90 days (read-only, <= a few hundred rows).
- `activity_log`: last 15 allowlisted events (`ORDER BY id DESC`, existing PK ordering) plus, for W7, `post.approved|rejected` sources in window.
- Config: slots and weights from `load_brand()`/settings.
- Existing indexes (`posts.created_at`, `date`, `status`, `publish_at`; `activity_log.created_at`; `generation_jobs.created_at`) suffice; add none unless the load test says otherwise. (Candidate if needed: partial index on `posts(status)` for non-terminal statuses.)

Known data weaknesses (documented in tooltips, optionally fixed later; none blocks Phase A):
1. `decided_at` is overwritten on re-decisions and, for Telegram, stamped at poll time. Fix later: immutable `approved_at` + `decided_via` on `posts` (one migration), or derive from `activity_log` while inside its 90-day retention.
2. `published_at` is the first platform's time; per-platform times live in `platforms[p].at` (used for per-platform views).
3. No poll heartbeat. Optional later: write a `settings` row (`heartbeat.poll`) or a `poll.ran` event on each `main.py poll` run (note `has_work.py` exits before Python when idle, so a heartbeat would only appear on busy runs; keep the overdue-approved check as the primary signal).
4. No token-lifecycle events. Later: `refresh_token.py` records `token.refreshed` / `token.failed` into the activity log (needs DB access in that workflow; today it only has the repo secret flow) to enable "last refreshed N days ago".
5. History starts where data starts: `generation_jobs` at go-live, `activity_log` max 90 days.

Phase B (engagement, only after owner approval): new tables `post_metrics(post_id, platform, fetched_at, metrics jsonb)` and `account_snapshots(day, platform, followers)`; an additional scheduled fetch job; the YT re-consent; possibly the IG insights re-authorisation. All behind a spike that proves the token scopes first.

### 5.3 Performance plan
1. Single aggregate query set executed on one DB session: 3 narrow selects (posts, jobs, activity) + config; no per-row queries, no N+1; avoid `q.load()` (loads captions/media).
2. Python aggregation O(n), n <= ~500; target aggregation < 50 ms.
3. 15 s in-process cache + ETag; frontend request has `AbortController` and one in-flight request at a time.
4. Frontend renders skeletons immediately; code-split the page; no chart bundle.
5. Measure: locust-style 20 sequential calls against Lambda warm and after a 6-minute idle (Neon resume); record p50/p95 in the PR. If p95 warm > 600 ms, add the partial index and trim columns before anything else.
6. Neon free tier connection limits: reuse the app's existing pooled session helper; one session per request.

## 6. Acceptance criteria (MVP = Phase A)

AC-1 10-second test. Given live data with 2 pending, 0 failed, When I open /dashboard at 1280x720 and on a 390x844 phone, Then without scrolling I see the status line ("2 things need you"), 4 KPI tiles with denominators, the top attention item and the next slot with countdown.

AC-2 Approval-rate definition. Given a fixture of 10 posts (5 published, 1 failed, 1 approved, 1 rejected, 1 replaced, 1 expired), When KPIs compute, Then approval rate = 7/9 (approved-ever 7 incl. failed; decided 9; expired excluded) and the tile shows "78% (7 of 9)" with "1 expired" noted.

AC-3 Publish success. Given IG published, YT failed twice then published on attempt 3, carousel IG published on attempt 1, YT skipped on another reel, When computed, Then success = 3/3 over final states with first-attempt = 2/3, and the skipped delivery is listed separately and excluded.

AC-4 Time to approve. Given approved posts with decision delays 10 m, 20 m, 4 h, When computed, Then median = 20 m and p90 shown; the tooltip states that it is an upper bound.

AC-5 Punctuality. Given a post with slot 19:00 approved at 20:10 and published at 20:25, Then it counts as on time (published within 30 min of max(slot, decision)); a post approved at 18:00 and published at 19:50 is not.

AC-6 Attention queue. Given an approved post whose slot passed 45 minutes ago and is unpublished, And a failed post at max attempts, And a pending post expiring in 4 h, Then the queue lists them high, high, high in that order with actions linking to Posts; with none of these it shows the green all-clear; if the query fails it shows "Couldn't check", not all-clear.

AC-7 Heatmap and text alternative. Given 30 days where 27 days have all 4 posts published, 2 partial, 1 none, Then the grid shows 27 full cells, 2 partial, 1 missed, the header says "27 of 30 days fully published", and a screen reader hears an equivalent summary; focusing a cell announces its date and count.

AC-8 Mix vs target. Given 24 topics (6 DSA) and DSA target 20%, Then DSA shows 25% vs 20% (+5) with the sample-size note; given only 12 topics, deviation colouring is suppressed.

AC-9 Funnel integrity. Given any dataset, Then Generated = published + failed-final + approved-waiting + pending + rejected + regenerated + expired, with no post counted twice.

AC-10 Partial failure. Given the `generation_jobs` query errors, When the page loads, Then pipeline health shows "unavailable" while every other widget renders, and no stack trace or SQL text reaches the browser.

AC-11 Privacy. Given the network response, Then it contains no email address, IP, token, caption, feedback or raw error body; activity actors appear only as "You/Telegram/System".

AC-12 Demo isolation. Given I switch to Demo, Then the banner "DEMO WORKSPACE - sample data" is visible and cannot be dismissed, the tab title has "[DEMO]", all actions are disabled, links are inert, and a database write-counter assertion in tests shows 0 writes and 0 outbound calls; switching back to Live shows real data and no demo item appears in Posts or Logs.

AC-13 Demo realism and honesty. Given the Demo data, Then it includes failures, rejections, an expiry and a quota-failed run, contains no engagement/follower/hours-saved figure, and the demo's KPI values are produced by the same aggregator (same function called in the unit tests with the fixture).

AC-14 Performance. Given a warm Lambda, When I load /dashboard 20 times, Then the endpoint p95 is < 600 ms and time-to-interactive < 1.5 s; cold start is measured and documented.

AC-15 Refresh. Given the tab is visible, Then data refreshes every 60 s and shows "as of"; Given it is hidden, Then no requests are made; Given the network drops, Then last data stays with a "stale" label and recovers by itself.

AC-16 Mobile and accessibility. Given 360 px width and keyboard only, Then all widgets are reachable, nothing overflows the page horizontally, status never relies on colour alone, and an automated axe check reports no serious violations.

## 7. Risks, open questions, "what live requires"

### 7.1 Risks
- R1 Misleading customers: numbers read as results ("approval rate 86%") may be mistaken for audience performance. Mitigation: wording ("of drafts you approved"), no engagement claims, the claim list in section 3.
- R2 Metric drift: `decided_at` overwritten and poll-time stamped makes time-to-approve imprecise. Mitigation: tooltips now; `approved_at` column later.
- R3 Small samples early (daily rate = 2 topics): ratios jump. Mitigation: n shown, n < 10 / < 20 suppression rules.
- R4 Demo leakage: demo data stored or shown as real. Mitigation: in-memory generation, banner, tests; owner reviews the demo data once.
- R5 Admin session shared with a customer exposes real data. Mitigation: screen-share only; separate demo deployment later.
- R6 Load: auto-refresh x tabs x Neon cold starts. Mitigation: 15 s cache, visibility pause, rate limit, skeletons.
- R7 Telegram-side decisions are only visible after the next poll (<= ~20 min), so "needs me" can briefly show items already decided in Telegram. Mitigation: "as of" label; the Posts page already has "sync Telegram".
- R8 Engagement integrations depend on scopes we do not hold (IG insights, YT readonly) and on Google's consent-screen mode (a "Testing" consent screen expires refresh tokens after 7 days; already warned in code).
- R9 Generate spec drift: it assumes React Query, which is not in `web/package.json`. Dashboard follows the real stack (hooks + interval). Align before build.

### 7.2 Open questions (recommended default in bold)
- OQ1 Default landing page after login: **/dashboard** once live.
- OQ2 Default window: **30 days** (selector 30/90).
- OQ3 Punctuality threshold: **30 min** (constant).
- OQ4 Is a Demo workspace in production acceptable, or dev/staging only? **Allowed in production behind `DASHBOARD_DEMO_ENABLED`, off by default until the owner flips it.**
- OQ5 Demo content: who writes the 12-15 fictional topics? **BA drafts, owner approves; technically accurate, no real brands.**
- OQ6 Fictional demo handle: **"@demo_dev_daily"**; owner may prefer the real brand name shown as presenter; not recommended (confusion risk).
- OQ7 Engagement: build in Phase B? **Yes, after a 1-day scope spike; IG likes/comments/followers first, YT after re-consent.**
- OQ8 Show YouTube privacy on cards? **Yes (honesty).**
- OQ9 Do we want a downloadable "monthly report" (PNG/PDF) for customers? **Later; out of MVP.**
- OQ10 Make approvals possible from the Dashboard attention list (not just deep-link)? **No in MVP; links to Posts keep one place of action.**
- OQ11 Add heartbeat/token events now (small backend change) or later? **Later (Phase B); symptom-based checks cover MVP.**

### 7.3 What live requires (owner approvals marked OWNER)
1. Dev complete with unit tests (aggregator fixtures, demo no-write test), API tests, web build, axe + 360 px check; verified against a throwaway DB, never the production Neon.
2. Generate's migration (`generation_jobs`) is already part of the Generate go-live; Dashboard Phase A adds NO migration. If Generate is not live yet, the dashboard must degrade gracefully (pipeline health from `posts` only).
3. OWNER: approve the Demo workspace content and the claim list in section 3.
4. OWNER: decide `DASHBOARD_DEMO_ENABLED` for production.
5. OWNER: approve deploy of the API (Lambda image) and web (sidebar `ready: true`); developer does not deploy by themselves.
6. Smoke test with the owner present: Live view numbers cross-checked against Posts counts; Demo toggle behaviour; confirm nothing published/generated by viewing.
7. Rollback: sidebar back to "soon"; endpoint is read-only so no data rollback.
8. Phase B only: OWNER approvals for any token re-authorisation (IG insights scope, YT `youtube.readonly`), the new tables' migration (Neon branch/backup first, note the workflows run `alembic upgrade head` automatically), and the scheduled metrics job.

## 8. Build order for the developer
1. Pure aggregator module (`src/dashboard_metrics.py`): input narrow rows + config + now, output all sections; unit tests for every definition and AC-2/3/4/5/8/9. Include the status-line/attention rules.
2. Demo generator module producing the same row shapes in memory + tests (0 DB writes, realism checks).
3. API `routes/dashboard.py`: auth, enum-validated params, narrow queries, section-level error isolation, 15 s cache + ETag, scrub/mask; API tests (privacy AC-11, partial failure AC-10).
4. Web: `lib/dashboard.ts` (types + fetch + refresh hook with visibility pause), `pages/Dashboard.tsx`, small components: `KpiTile`, `AttentionList`, `SlotTimeline`, `Heatmap`, `MixBars`, `FunnelBars`, `ActivityFeed`, `DemoBanner`; reuse `StatusBadge`, `ProgressTrack`, `stage.ts` tones; skeletons, empty and error states; route + sidebar flag (flag flipped only at go-live).
5. Cross-link checks: Posts accepts `?status=` / `?group=`; Logs link. Add small Posts change only if needed.
6. Accessibility + mobile pass, performance measurement (NFR-1), Playwright smoke in `web/tests`.
7. Owner review in Demo workspace, then go-live checklist (7.3).
8. Phase B (separate ticket): scope spike (IG basic + insights, YT readonly), `post_metrics` / `account_snapshots`, fetch job, Engagement widget, token/heartbeat events.
