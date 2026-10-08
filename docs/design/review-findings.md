# Design review findings: pages outside the Posts and shell redesign

> **Status, second pass (2026-10-06): all 29 findings are fixed; none are deferred.** Most Generate, Logs, Profile,
> Login and Recover items had already been fixed in commit 9755e35. Pass 2 fixed every Dashboard item and the
> leftovers noted per finding, and re-verified everything with screenshots at 1440/768/390 and mocked-API behaviour
> checks. Each finding below carries a **Status** line. Config was built after this review; it uses `PageHeader index="05"`.

Reviewed on 2026-10-06 against `docs/design/design-system.md`. The pages were rendered with a mocked API at 1440×900,
768×1024 and 390×844. Line numbers refer to the working tree on that date. The pages and engineers move fast, so search
for the quoted code if a line has shifted.

**Already applied (class-level only, no behaviour change):** hard-coded `#56d364` / `#2ea043` / `var(--brand-accent)`
status classes were swapped for the `ok` / `ok-solid` / `wait` / `signal` tokens in `pages/Profile.tsx`,
`pages/Logs.tsx`, `pages/Login.tsx`, `pages/Recover.tsx` and `components/password-field.tsx`. The colours are
identical; they now follow a Config re-theme and the documented roles.

**Inherited automatically by every page:** the restyled primitives (buttons, fields, selects, checkbox and radio,
tabs, table, dialogs, sheet, tooltip, toast, skeleton), the new shell (sidebar index, Today strip, mobile top and
bottom bars) and the stronger `--input` boundary (34%, 3.1:1).

Severity: **H** = a customer would notice, or it breaks a rule in the system. **M** = inconsistency. **L** = polish.

| Page | H | M | L | Total |
|---|---|---|---|---|
| Dashboard | 1 | 4 | 2 | 7 |
| Generate | 2 | 4 | 2 | 8 |
| Config | – | – | – | not built yet |
| Logs | 1 | 3 | 1 | 5 |
| Profile | 1 | 2 | 1 | 4 |
| Login | 0 | 2 | 1 | 3 |
| Recover | 0 | 1 | 1 | 2 |
| **All** | **5** | **16** | **8** | **29** |

---

## Dashboard (edited in pass 2)

1. **H: The page header is not the shared masthead.** `pages/Dashboard.tsx:146-149` hand-builds a `CONTROL ROOM`
   eyebrow and an `h1` at `text-2xl/3xl`. Every other signed-in page now opens with
   `<PageHeader index="01" eyebrow="Control room" title="Dashboard" meta={…as of…} actions={<Segmented…/>…} />`
   (`components/page-header.tsx`), which adds the index numeral, the larger display size and the amber-signed hairline.
   The segmented controls fit in `actions` as they are.
   **Status:** Fixed (pass 2): `PageHeader index="01" eyebrow="Control room · handle"`, the segmented controls and refresh as `actions`; content width `max-w-[78rem]` like the other operational pages. `PageHeader` now wraps wide actions below the title instead of squeezing it.
2. **M: Hard-coded status hexes.** `components/dashboard/primitives.tsx:17,20` (`text-[#56d364]`, `bg-[#2ea043]`),
   `right-now.tsx:57-58,163`, `shipped.tsx:121`, `engine.tsx:9` (green glow shadow). Use `text-ok`, `bg-ok-solid`,
   `border-ok/30`, `bg-wait` and `text-signal`. Drop the glow shadow on the engine dot (section 7: no coloured glows).
   **Status:** Fixed (pass 2): all dashboard components use `ok` / `ok-solid` / `wait` / `bad` / `go` tokens; the engine LED glow is gone; status amber is `wait`, the Sample marks stay `signal`; rejected/expired feed tags are muted (off the path).
3. **M: The KPI strip comes close to the "identical stat cards" pattern.** `kpi-strip.tsx:79` gives five equal cells
   (`lg:grid-cols-5`). The micro-visuals help, but the five cells share one silhouette. Suggestion: weight the cells
   by importance (`lg:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]`, with "Posts published" first), or set the two rate cells
   as one ledger cell ("Approval 86% · On time 94%").
   **Status:** Fixed (pass 2): the strip is now three shapes: a lead numeral (Posts published, 5-6xl, with the 30-day pulse), a ledger of the three rates (Approval, Publish success, On time; label .... value, ratio and note, rail), and the turnaround figure with its bins. On time is no longer hidden on phones.
4. **M: Saturated calendar blocks.** In the cadence heatmap (`cadence.tsx`), fully published days are solid
   `bg-primary` squares. Nineteen bright cyan squares are the loudest thing on the page and compete with "2 things
   need you". Use `bg-go/70` for "all published", hatched for partial (as now) and `bg-border` for missed, and
   keep full cyan for today only.
   **Status:** Fixed (pass 2): fully published days are `bg-go/35`; partial stays hatched (its numbers sit on a small plate so they read); missed stays a dashed `wait` cell with ×, because it needs attention; today is the only solid-cyan outline. Week bars stepped to `go/70` / `go/40`.
5. **M: Cards inside sections, everywhere.** `cadence.tsx:51`, `engine.tsx:77`, `funnel-mix.tsx:16,63`,
   `shipped.tsx:17,131` all use `rounded-xl border bg-card p-5/6`. Four numbered sections that each contain the same
   card make the page uniform. Let one section per screen sit on the page with no card (for example the Engine
   ledger, which is a ledger and reads better without a box), and keep cards for the two side-by-side comparisons.
   **Status:** Fixed (pass 2): section 01 (cadence) and section 03 (engine console + turnaround, split by one hairline) now sit on the page with no card; the side-by-side comparisons (funnel/mix) and the platform cards keep theirs.
6. **L: Funnel bars.** `funnel-mix.tsx:20`: four identical cyan bars plus a green one. Step the cyan down as the
   funnel narrows (100% → 70% → 55% opacity) so the eye reads loss rather than four equal things.
   **Status:** Fixed (pass 2): funnel bars step `go` → `go/70` → `go/55`, live stays `ok-solid`; leak tags are 4px tags, not pills.
7. **L: Live workspace while loading.** With `workspace=live` and an API that never answers, the page shows four
   large skeleton blocks and nothing else (seen on the first capture). Add `role="status"` with a label and one
   line of text ("Loading the last 30 days…") so that a slow Neon cold start doesn't look broken.
   **Status:** Fixed (pass 2): `DashSkeleton` is `role="status"` with a label and one line, "Loading the last 30/90 days…".

## Generate

1. **H: The header is not the shared masthead.** `pages/Generate.tsx:180-197`: a hand-placed `amber-rule` above a
   `text-2xl` `h1`, and the "Updated" text and Refresh button are separate siblings. Use
   `<PageHeader index="03" eyebrow="Work order" title="Generate" lead={…} meta={updated} actions={refresh} />`.
   **Status:** Fixed (before pass 2): `PageHeader index="03" eyebrow="Work order"` with meta and actions.
2. **H: The form is a card in a sidebar, the classic generated layout.** `components/generate-form.tsx:123`
   (`rounded-xl border bg-card p-4 lg:sticky`), sitting next to `run-tracker.tsx:47` (another `rounded-xl border
   bg-card p-4`). Two equal cards side by side read as a template. Suggestion: make the form a "work order": no
   card, a left hairline (`border-l border-rule pl-6`), mono field labels (`label-mono`, as on Profile and Login)
   and lines between fields. Keep the tracker as the only boxed element, because it is a live object.
   **Status:** Fixed (before pass 2): the form is a work order with no card (left hairline on wide screens, top rule on phones, lines between fields); the tracker is the only boxed element.
3. **M: Field labels use the sans `Label`.** `generate-form.tsx:148,171,185,211` use the sentence-case 14px label,
   while Profile, Login and the Posts panel use mono labels. Pass `className="label-mono"` (or match Posts' `MONO`).
   **Status:** Fixed (before pass 2): mono labels.
4. **M: Status pills.** `components/phase-track.tsx:36` defines a separate fully round badge (`rounded-full …`).
   Reuse `StatusBadge`'s squared-tag look (3-4px radius plus a dot), or import `StatusBadge` where the status is a post status.
   **Status:** Fixed (before pass 2): `JobStatusBadge` is a 4px squared tag with icon + word.
5. **M: Error and notice banners.** `Generate.tsx:200,210` and `generate-form.tsx:140,232` use
   `rounded-lg border border-destructive/40 bg-destructive/10`. The system pattern for a page-level error is a 3px
   `bad` left edge on `bad/10` with no rounded box (see Posts). `quotaOut` is a warning, so use `wait`, not `destructive`.
   **Status:** Fixed: page and form banners use the 3px left-edge pattern; quota is `wait`. Pass 2 also moved the quota line inside the confirm dialog from `text-destructive` to `text-wait`.
6. **M: Empty state.** `Generate.tsx:39,220`: a dashed centred box with "Nothing is running". Use the system
   empty state (an outlined `00`, one line, one sentence, one action such as "Generate for the next slot").
   **Status:** Fixed (before pass 2): outlined `00` empty state with one action, "Generate for the next slot".
7. **L: Slot board dots.** `slot-board.tsx:34` uses a 21px circle with a 2px border; with the timeline it looks
   heavier than the Posts rail. Use `size-[15px] border` with a filled centre for "generated".
   **Status:** Fixed (before pass 2): 15px dot with a filled centre.
8. **L: "Generate for this slot" repeats three times** at the same weight. Make the next upcoming slot's button
   `outline` and the later ones `ghost`, so there is one obvious next step.
   **Status:** Fixed (before pass 2): next slot is `outline`, later slots `ghost`, the picked one `secondary`.

## Config: not built yet

There is no `pages/Config*.tsx` in the tree on this date. When it lands, use `PageHeader index="05"`, the
Profile-style numbered sections (it is a long form read top to bottom), mono labels, ledger rows for read-only
values, and the floating save bar pattern from `Profile.tsx:166` for unsaved changes.

## Logs (class-level fixes applied; layout items below)

1. **H: The summary strip is four identical stat cards.** `pages/Logs.tsx:205,236-263` (`pill` cells in
   `grid-cols-2 sm:grid-cols-4`). This is the pattern the system bans. Suggestion: one terminal status line above the
   ledger, e.g. `24h  ERR 1  ·  WARN 1  ·  last publish 40m ago (carousel to Instagram)  ·  last error 1h ago (post.failed)`,
   with each segment a toggle button (`aria-pressed`) that keeps today's filters. That fits the terminal character
   of the page.
   **Status:** Fixed (before pass 2): one terminal status line (`24h ERR · WARN · last publish · last error`), each segment an `aria-pressed` toggle that keeps the other filters; 44px on touch.
2. **M: The header is not the shared masthead.** `Logs.tsx:210-233`. Use `PageHeader index="06" eyebrow="Record"`
   with the tail/refresh buttons as `actions` and the IST clock as `meta`.
   **Status:** Fixed (before pass 2): `PageHeader index="06" eyebrow="Record"`, live tail + refresh as actions, IST time as meta.
3. **M: Level chips are full pills.** `Logs.tsx:273,284`. Use 4px-radius tags (as with `StatusBadge`), and
   remove the duplicated "Errors only" chip, which does the same as toggling only "Errors".
   **Status:** Fixed (before pass 2): 4px level tags; the duplicate "Errors only" chip is gone (the ERR segment does it).
4. **M: Focus.** `Logs.tsx:205,273,284` use `outline-none focus-visible:ring-2 focus-visible:ring-ring/60`, a
   second focus language. Delete those classes and the global 2px outline applies.
   **Status:** Fixed (before pass 2): no ring-only focus; the global outline applies.
5. **L: The error banner** (`Logs.tsx:318`) uses a rounded box. Use the `bad` left-edge pattern.
   **Status:** Fixed (before pass 2): 3px `bad` left edge.

## Profile (class-level fixes applied)

1. **H: A dead gap under "About you".** `Profile.tsx:134,166`: the floating save bar is invisible (`opacity-0`)
   but still takes up its height plus `gap-9`, leaving about 120px of empty space before section 02 (visible at
   1440). Render it `fixed`/`sticky` outside the grid flow, or collapse it with `h-0 overflow-visible` while it is
   not dirty.
   **Status:** Fixed (before pass 2; verified in pass 2): the save bar is `fixed`, out of the grid flow, so it takes no room while hidden. Measured: 50px from the bio rule to the section 02 title at 1440 (the normal `gap-9` rhythm).
2. **M: A second focus language.** `Profile.tsx:72` (`focus-visible:ring-3 focus-visible:ring-ring/60` on the
   avatar button). Use the global outline (remove `outline-none` and the ring classes).
   **Status:** Fixed (before pass 2): the avatar button uses the global outline.
3. **M: Pills.** `Profile.tsx:190-193` (`Pill`) are fully round tags. Use 4px radius to match `StatusBadge`.
   **Status:** Fixed (before pass 2): `Pill` is a 4px tag.
4. **L: The step rail.** `Profile.tsx:341` mixes `ok-solid` for done steps with `signal` for the current one.
   That is fine, but the done circle has dark text on green; keep the check icon only (as it is) and make sure no
   text is ever placed there.
   **Status:** Fixed: done steps show only the check (with sr-only "(done)"). Pass 2 also raised future steps from `muted-foreground/60` (below 4.5:1) to `muted-foreground` (7.66:1).

## Login

1. **M: The slot times are hard-coded.** `Login.tsx:25` has `["Morning slot","10:00"],["Evening slot","19:00"]`.
   They match `brand/config.yaml:26` today, but they will drift when `post_times_ist` changes from Config. Expose
   the times on `/api/public/brand` (it is already public) and read them from there.
   **Status:** Fixed (before pass 2; verified in pass 2): the times come from `post_times_ist` on `/api/public/brand` (the API field exists in `api/app/routes/public.py`). A mocked brand of 09:15/18:45 renders those times and no hard-coded 10:00.
2. **M: The primary button is disabled until both fields are filled**, so on first paint the only call to action is
   a dimmed cyan bar. This is acceptable, but add `aria-describedby` hint text or keep the button enabled and
   validate on submit (the pattern used elsewhere).
   **Status:** Fixed (before pass 2): the button is enabled and the form validates on submit with inline reasons (`aria-describedby`).
3. **L: The success notice** (`Login.tsx:119`) uses a 2px left edge where the system uses 3px. Align it.
   **Status:** Fixed: the success notice is 3px. Pass 2 also gave the error alert the 3px `bad` edge (it was 2px `destructive`), made the Google-offline notice a 3px `wait` warning, and gave the "Forgot password?" and "Try again" links a 44px touch hit area without moving the layout. The Google retry/offline behaviour is unchanged (verified: 4 tries with back-off, then the notice, and Try again restores the button).

## Recover

1. **M: The steps list** (`Recover.tsx:~100-110`) uses check icons with `aria-label="done"` on an SVG. Use
   `aria-hidden` on the icon and put "(done)" as sr-only text in the list item.
   **Status:** Fixed (before pass 2): icons are `aria-hidden` and the list item carries sr-only "(done)" / "(current step)".
2. **L: The success mark** (`Recover.tsx:81`) is a squircle with a green tint, which is fine. Add the amber rule
   above the success headline so that the moment is "signed" the same way as the panel and dialogs.
   **Status:** Fixed (before pass 2): the amber rule signs the success headline. Pass 2 also gave "Send a new code" and "Change account" a 44px touch hit area.
