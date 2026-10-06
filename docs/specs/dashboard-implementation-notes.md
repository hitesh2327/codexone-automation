# Dashboard: implementation notes and spec checklist

Spec: `docs/specs/dashboard-section.md` (BA, 2026-10-05). Status as of 2026-10-06: Phase A complete in the
working tree, not deployed. No migration, no new credentials, no new dependency.

Legend: **done** | **partial** (what is missing) | **missing** | **deviation** (what and why).

## Where things live

| Piece | File |
|---|---|
| Pure aggregator (rows + now + config -> every section) | `src/dashboard_metrics.py` (`build_overview`) |
| Demo workspace generator (in memory, seeded) | `src/dashboard_demo.py` (`build_demo`) |
| Endpoint `GET /api/dashboard/overview` | `api/app/routes/dashboard.py` (registered in `api/app/main.py`) |
| Tests (definitions, AC fixtures, API, privacy, demo isolation) | `api/tests/test_dashboard.py` |
| Web types + pure helpers (node-tested) | `web/src/lib/dashboard-format.ts`, `web/tests/dashboard.test.mts` |
| Fetch + 60 s refresh hook | `web/src/lib/dashboard.ts` |
| Page and widgets | `web/src/pages/Dashboard.tsx`, `web/src/components/dashboard/*.tsx` |

## Endpoint shape

`GET /api/dashboard/overview?range=30|90&workspace=live|demo` (admin session required; 30 req/min/user;
15 s in-process cache per (workspace, range); `ETag` + `Cache-Control: private, max-age=0, must-revalidate`;
304 on `If-None-Match`). Top level: `workspace, demo, handle, generated_at, window_days, config{slots,
expected_per_day, timezone, categories[{category, weight, target}], thresholds{min_n, min_mix_n, punctual_min,
max_attempts, expire_hours}, demo_enabled}, status, kpis, attention, next_slots, cadence, mix, funnel,
turnaround, pipeline{generation, slot_fill, publishing}, platforms, recent_posts, activity`. Every section
has `ok`; on failure `{ok:false, error:"unavailable"}` (never a stack trace or SQL). Every rate is
`{num, den, pct, judged}` (`judged = den >= 10`). Measured payload 14-19 KB raw, about 3 KB gzip.

## Functional requirements

| # | Requirement | Status | Notes |
|---|---|---|---|
| FR-1 | `/dashboard` in AppShell; sidebar `ready:true` at go-live | done | Route + catch-all `* -> /dashboard` in `App.tsx`, NAV `ready:true` in `app-shell.tsx` (both were already in place; nothing deployed). |
| FR-2 | One request; widgets render independently | done | Section-level `_guard`; posts/jobs/events each read in their own session. UI shows "X: unavailable right now. The rest of the page is unaffected." per widget. |
| FR-3 | 30/90 selector re-queries once; W2/W3 ignore it | done | |
| FR-4 | Exact definitions; num/den shown; n<10 "too few to judge" | done | See metric section below; every tile shows "N of M". |
| FR-5 | Attention conditions, high>medium>low then age, one action into Posts/Generate | done + deviation | Reel and carousel of the same topic with the same need are merged into one row ("Reel and carousel 'X'"), keeping the higher severity and older age. Different needs (e.g. different platforms failed) stay separate. Reason: two identical rows per topic doubled the count and the noise. Slot-empty and generation rows link to Logs (no post exists to open). |
| FR-6 | Status line first-match rule with text reason | done | `status.state` action/heads_up/ok/unknown; the hero sentence always spells it ("2 things need you." + "N of M posts live today · next goes out at 19:00 IST (in 3h 12m)"). `aria-live="polite"`. |
| FR-7 | Text alternative for heatmap, mix, funnel | done | Visually hidden tables (wrapped in an `sr-only` div; a bare `sr-only` table widened the page) + `role=img`/`aria-label` summaries; mix bars carry their numbers as text. |
| FR-8 | 60 s refresh while visible, pause hidden, "as of", manual refresh, stale label | done | `useOverview`: interval skips while `document.hidden`; catches up on becoming visible; last data kept with a "stale" tag; one in-flight request (AbortController). |
| FR-9 | Feed allowlist, masked actors, truncated + scrubbed | done | Allowlist adds `post.regenerated` (harmless, informative). Actors: You / Telegram / System. 140 chars, secrets and emails scrubbed. |
| FR-10 | External links https + host allowlist + noopener + new tab | done | `safe_url` (instagram.com, youtube.com, youtu.be, subdomains); tested against http, lookalike hosts, `javascript:`. |
| FR-11 | Demo workspace (banner, read-only, in-memory, same aggregator, sessionStorage, env switch) | done | See Demo section. |
| FR-12 | IST days/labels, UTC ISO on the wire | done | |
| FR-13 | Slots, categories, weights from server config | done + note | From `load_brand()`. Generation start times ("generation starts about 08:00") come from `GENERATE_AT` in `dashboard_metrics.py`, which mirrors the workflow crons (08:00 -> 10:00 slot, 18:00 -> 19:00 slot). A slot not in that map shows no start time rather than a guess. The previous code guessed slot minus 90 min, which was wrong for both slots. |
| FR-14 | Empty states (new install, empty window, no jobs, no activity) | done | "Your first day will show up here", "No posts in this period yet. Open Generate...", "tracking starts at go-live", "Activity will appear here". Screenshot-checked. |
| FR-15 | Page never writes, publishes, generates or calls out | done | GET only; API test spies on every SQL statement for the demo path. Live path only SELECTs (narrow columns). |

## Non-functional

| # | Requirement | Status | Notes |
|---|---|---|---|
| NFR-1 | p95 < 600 ms warm; skeletons < 100 ms | partial | Measured locally (docker Postgres, 20 calls each): p50 15-22 ms, p95 19-29 ms. **Not measured on Lambda + Neon** (not allowed from dev). Skeleton renders immediately; page is a lazy chunk. |
| NFR-2 | One aggregate request; < 40 KB | done | ~3 KB gzip. |
| NFR-3 | 360/390 px, no page scroll, heatmap scrolls inside its card | done | `scrollWidth == viewport` verified at 360 and 390 in both workspaces. Root causes fixed: `auto` grid tracks sized to the gallery's min-content; `sr-only` spans escaping the scroller (no positioned ancestor); `sr-only` tables. |
| NFR-4 | WCAG AA, text+icon+colour, reduced motion, keyboard | done (dashboard) | axe-core 4 (wcag2a/aa, 2.1 a/aa, best-practice) at 1440 and 360, live + demo: **0 violations in dashboard code**. 1 remaining, in the app shell (logo/profile link `label-content-name-mismatch`), owned by the Designer. Heatmap: one tab stop, arrows move by day/week, each cell announces "Tue 29 Sep: 4 of 4 published (2 topics)". Count-up plays once on first load and not under `prefers-reduced-motion` (verified frame by frame). |
| NFR-5 | Brand tokens, no chart library | done | SVG/CSS only. |
| NFR-6 | Read-only, idempotent, null-tolerant | done | Legacy rows without platforms/group/publish_at handled. |
| NFR-7 | Aggregator is a pure function, demo goes through it | done | |

## Security / privacy (4.3)

done: admin-only; response whitelist (no captions, post_dir, media beyond one https thumbnail, tg ids, feedback,
source_url, emails, IPs, tokens, raw errors; tested with planted secrets); actor masking; `login.*` never shown;
rate limit 30/min; `workspace` validated as an enum (422 otherwise), demo path selected server-side.

## Acceptance criteria

| AC | Status | Evidence |
|---|---|---|
| AC-1 10-second test | done | Screenshots at 1280x720 and 390x844 (live): status sentence, top attention item, next slot with countdown (in the sentence and the slot card), 4 KPI tiles with denominators, all above the fold. Phone order: sentence + top item -> KPIs -> slots. |
| AC-2 approval 7/9 | done | `test_approval_rate_ac2`: 78%, "7 of 9", 1 expired noted, not judged (n=9). |
| AC-3 publish success 3/3, first 2/3, skipped excluded | done | `test_publish_success_ac3_literal_fixture` (spec fixture as written) + `test_publish_success_ac3`. |
| AC-4 median 20 m, p90, upper bound | done | `test_time_to_approve_ac4` (median 20, p90 240 nearest-rank); tooltip states upper bound. |
| AC-5 punctuality | done | `test_punctuality_ac5`. |
| AC-6 attention order, all-clear, "couldn't check" | done | `test_attention_queue_ac6`, `test_attention_all_clear_and_error_state`, plus UI states screenshot-checked. |
| AC-7 heatmap states + text | done | `test_cadence_states_and_text_figures_ac7`; web test for cell summaries. |
| AC-8 mix 25% vs 20% (+5), suppression < 20 | done | `test_mix_ac8`. |
| AC-9 funnel integrity | done + deviation | Buckets sum to Generated (tested). "failed" is split into `failed` (gave up) and `retrying` so a temporary failure isn't shown as final; both are in the identity. |
| AC-10 partial failure | done | `test_validation_and_partial_failure`, `test_section_failure_is_isolated`; screenshot of the jobs/activity/funnel-unavailable state. |
| AC-11 privacy | done | `test_overview_privacy_and_shape`. |
| AC-12 demo isolation | done | Banner (sticky, non-dismissible), "[DEMO] Dashboard" title, SAMPLE marks on every card/section, actions disabled with tooltip, links inert, `test_demo_endpoint_zero_writes_and_no_live_tables` (SQL spy: 0 statements touching posts/activity_log/generation_jobs/posted_topics, 0 writes), `test_demo_builder_and_aggregation_never_touch_the_database` (db.session patched to raise). |
| AC-13 demo realism | done | Tested: approval 70-99%, rejections, regenerations, exactly 2 expiries, 2 retried publishes, 1 YouTube upload that gave up (publish success 99%, not 100%), a quota-failed run, banned words (follower/reach/likes/impression/hours saved/URLs) absent, coherent timeline (no future events, no approval after its publish). |
| AC-14 performance on Lambda | partial | Local numbers only (above). Needs the 20-call warm/cold measurement on the deployed stack. |
| AC-15 refresh | done | Hook logic reviewed + keyboard/refresh browser check; no requests while hidden by construction. |
| AC-16 mobile + a11y + axe | done (dashboard) | See NFR-3/NFR-4. |

## Metric definitions as implemented (`src/dashboard_metrics.py`)

- **Posts published** = status `published` with `published_at` >= window start (IST midnight, 30/90 days incl. today); topics = distinct `group_id`; deliveries = platform records `published`.
- **Approval** = approved-ever {approved, publishing, published, failed} / (approved-ever + {rejected, regenerate, replaced}), over posts created in window. First pass = same, `version = 1`. Pending and expired reported separately.
- **Publish success** = platform records `published` / (`published` + `failed`) over targets of posts whose final publish time (last platform `at`) is in window; `skipped` excluded and listed with reason. First attempt = `published` with `attempts == 1` over the same denominator. Per platform the same in W9.
- **Time to approve** = `decided_at - created_at` for approved-ever posts created in window; median (midpoint for even n); p90 nearest-rank. Flagged as an upper bound.
- **Punctuality** = published posts with `published_at - max(publish_at, decided_at) <= 30 min` / published posts with a slot.
- **Cadence** = posts with `published_at` per IST day; expected = 2 x slots; states full/partial/missed/today/none (none = before the first post ever created); streak = consecutive full days ending yesterday (today counts once full).
- **Mix** = topics (groups, current non-replaced version) created in window per category vs weight share; margin = 95% binomial interval; deviation coloured only when n >= 20 and outside the margin.
- **Turnaround** = W1 data in 5 bins; per channel (Telegram / dashboard) from `post.approved|scheduled` events (first per post) within window.
- **Pipeline** = slot fill (elapsed slots with >= 1 non-replaced topic, from posts); job success = succeeded/(succeeded+failed) in window, skipped/cancelled listed, streak, last run, last failure class, "tracking since".

## Demo behaviour

`?workspace=demo` or the Live | Demo control (sessionStorage only). Server switch `DASHBOARD_DEMO_ENABLED`
(unset = on when `COOKIE_SECURE` is false, i.e. local; off in production unless the owner sets it); when off,
the toggle hides and the API returns 404 for `workspace=demo`. Data: fictional handle `@demo_dev_daily`,
97 evergreen technically-correct topics, ids `demo-*`, no URLs, dates relative to now (seed 20261005), 42
days of history. Owner must review the topic list once (spec OQ5).

## Posts deep links

Verified: Posts reads `?status=` and `?post=` (opens the panel) and loads all rows, so `/posts?post=<id>` always
resolves. The dashboard does not use `?group=`. No Posts change was needed.

## Known limits / follow-ups

- AC-14 / NFR-1 on Lambda + Neon not measured (deploy not allowed from dev).
- Generation start times mirror the workflow crons by hand (`GENERATE_AT`); if `post_times_ist` changes, update the crons and this map together (README already says crons and slots move together).
- `decided_at` and Telegram stamping caveats remain (spec 5.2, Phase B fix).
- App shell axe finding belongs to the Designer.
