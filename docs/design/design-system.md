# codexone admin: design system

The rulebook for the dashboard in `web/`. It describes what already ships. Read it before you build a screen, and
when you are unsure, copy the closest existing pattern rather than inventing one. Tokens live in
`web/src/index.css`, primitives in `web/src/components/ui/*`, and the shell in `web/src/components/app-shell.tsx`.

## 1. Principles

1. **A desk, not a template.** The product is an editor's desk for a daily run of posts. Screens borrow from
   print and operations: mastheads, indexes, ledgers, run sheets. They do not borrow from SaaS card grids.
2. **Each section is shaped by its job.** A queue reads as a timeline, a record reads as a ledger, a form
   reads as a sheet of lines, a log reads as a terminal. If two sections look identical, one of them is
   probably wrong.
3. **Colour means state.** Cyan, amber, green, red and violet each have one role (section 4). Decoration is
   neutral. The one exception is the amber *signal* (rule, bookmark, index numeral), which marks "you are here".
4. **Quiet until it matters.** Hairlines and type do the structuring. Fills, borders and motion are kept for
   things that need attention: something waiting, failing, selected or focused.
5. **Say what happens next.** Every status comes with a sentence ("Approve it to post Tue 19:30"), every
   disabled action comes with a reason, every empty screen comes with the next step.

## 2. Typography

| Role | Face | Size / line | Weight | Tracking | Use |
|---|---|---|---|---|---|
| Display | Poppins (`font-heading`) | 38/40 (30 mobile) | 600 | -0.01em (`tracking-tight`) | Page title in `PageHeader`; profile name (60) |
| Section | Poppins | 22-24 | 600 | tight | Numbered section titles (`01 About you`) |
| Item title | Poppins | 15-16 / 1.35 | 500 | normal | A topic in the run of show, a dialog title (18) |
| Body | Inter (`font-sans`) | 14 / 1.5 | 400-500 | normal | Everything readable |
| Small | Inter | 12-13 / 1.4 | 400 | normal | Notes under a status, helper text |
| Mono label | JetBrains Mono (`label-mono`) | 11 / 16 | 500 | 0.14em, UPPERCASE | Field labels, column heads, eyebrows, section groups |
| Mono data | JetBrains Mono (`font-mono tabular-nums`) | 11-18 | 400-500 | normal | Times, counts, IDs, slot times, hashtags, log lines |
| Numeral | Poppins or Mono | 28-56 | 500-700 | tight | Day marks (`06`), summary counts (`04`), outlined section numbers |

Rules:
- Use mono for anything a machine produced or a person compares: times, IDs, counts, event names. Use sans for
  sentences. Never set a sentence in mono uppercase.
- Pad counts to two digits only in summary numerals (`04`), never in running text.
- Titles use `text-wrap: balance` (global for h1-h3). Do not hand-break lines.
- The brand fonts can be changed from Config at runtime (`--font-brand-*`), so never hard-code a family.

## 3. Layout and spacing rhythm

- Base unit 4px. Use 4 / 8 / 12 / 16 / 24 / 32 / 40 / 56. Section gaps are 28-40 (`gap-7`-`gap-10`); in-section gaps 8-16.
- Content width: `max-w-[78rem]` for operational pages (Posts, Dashboard, Logs), `max-w-5xl` for reading and
  forms (Profile), `max-w-[22rem]` for a single form (Login).
- Page padding: `px-4 py-6` on phones, `md:px-8 md:py-9` above.
- **Page header** (`components/page-header.tsx`): eyebrow `NN — purpose` in mono, a large title, one line of
  purpose, meta + actions on the right, a hairline signed by the amber rule. Every signed-in page uses it.
  `NN` is the page's number in the sidebar index.
- Asymmetry is intentional: a narrow label column next to a wide content column (Posts day marks, Profile
  index, ledger rows `9rem | 1fr | auto`). Avoid equal-width multi-column grids unless the items are true peers.

## 4. Colour roles

Always use the token, never the hex. Brand values can be re-themed from Config.

| Token | Default | Role |
|---|---|---|
| `--brand-bg` / `bg-background` | #0D1117 | The page |
| `--sidebar` | text 3% into bg | Shell column |
| `bg-card` (4%), `bg-raised` (5%), `bg-popover` (6%) | | Lists, hover, floating surfaces, one step each |
| `bg-sunken` | black 28% into bg | Media beds, code wells |
| `bg-selected` | cyan 8% into bg | The open or selected row |
| `text-foreground` | #FFFFFF | Primary text |
| `text-muted-foreground` | text 62% into bg | Secondary text (6.6:1 or better on every surface) |
| `border-border` (12%) | | Quiet dividers between peers |
| `border-rule` (22%) | | Hairlines that must be seen: ledgers, outline buttons, dialogs |
| `border-input` (34%) | | Field, checkbox and radio boundaries (3.1:1, meets WCAG 1.4.11) |
| `text-signal` / `bg-signal` | `--brand-accent` amber | "You are here": amber rule, nav bookmark, page index |

**Status colours** (each is text-safe, at least 4.5:1, on every surface above):

| Token | Meaning | Examples |
|---|---|---|
| `wait` (amber) | Needs a human | Waiting for approval, warnings |
| `go` (cyan) | In motion | Approved, scheduled, publishing, info |
| `ok` (#56D364) | Done | Live, published. `ok-solid` (#2EA043) is for fills only, never text |
| `bad` (#F85149) | Failed, destructive | Failed publish, errors, Reject |
| `ai` (#D2A8FF) | Machine work | Regenerating, "feedback applied" |
| muted | Off the path | Rejected, expired, replaced |

Use tints at 10% (`bg-wait/10`) behind status text and 35-45% for status borders. Never put white text on an
amber or green fill. Cyan (`bg-primary`) carries dark text (`text-primary-foreground`, 12.3:1).

## 5. Vocabulary: when to use which device

| Device | What it is | Use when | Do not use for |
|---|---|---|---|
| **Mono label** (`label-mono`) | 11px uppercase mono, 0.14em | Naming a field, a column, a group, an eyebrow | Sentences, buttons |
| **Amber rule** (`amber-rule`) | 40×3 amber bar | Signing the start of a page header, panel or dialog (one per surface) | Dividers, progress, emphasis inside content |
| **Numbered section** | Outlined `01`-`04` + title + lead | Long pages read top to bottom as a sequence: Profile's four parts, Dashboard's four questions | Queues and lists, which are scanned, not read |
| **Index numerals** | `01`-`06` beside nav items and page eyebrows | Wayfinding between pages | Counting things |
| **Ledger row** | `label ....... value` with a dotted `leader` | Read-only facts: account record, reel spec, publish plan | Editable fields, long text |
| **Ledger table** | Mono column heads, hairline rows | Lists of comparable records (Logs) | Fewer than about 4 rows |
| **Run of show** | Day mark + time-ordered rows | Anything scheduled (Posts) | Unscheduled collections |
| **Flow strip** | Connected segments with arrows | Counts that are stages of one process (Posts) | Unrelated KPIs |
| **Rail** | 4 short segments | Progress along a fixed path (Approval → Live) | Percentages, which use a meter |
| **Status tag** | Squared tag with a dot | Compact status beside a name (tabs, slot board) | Running text, which uses a coloured word |

Pages differ on purpose: Dashboard is a control room, Posts is a run of show, Generate is a work order,
Logs is a terminal, Profile is a dossier, Login is a desk. Keep each one that way.

## 6. Shape

- `--radius` is 10px. Controls (buttons, inputs, selects) use `rounded-md` (8px). Lists and panels use
  `rounded-xl` (14px). Media uses 12px for slides and 18px for the reel frame. Avatars are squircles (`rounded-[30%]`).
- Status tags, kbd-like marks and platform marks use 3-4px. **Fully round pills are reserved for** the floating
  save bar, dots and progress meters. They are not for tags or filters.
- Never put a rounded card inside a rounded card. Nest with hairlines (`divide-y`) or with spacing.

## 7. Elevation

Three levels and no more:
1. **Flat**: the page and lists (`bg-card/40` and a border).
2. **Raised**: hover and selected rows (`bg-raised`, `bg-selected`). This is a colour step, with no shadow.
3. **Floating**: popovers, dialogs, sheets and toasts. These use `border-rule` plus a single soft, dark shadow
   (`0 16-24px 40-64px -12px rgb(0 0 0 / .75)`), over a 62% black scrim with a 2px blur for modals.

Do not add glows, coloured shadows or glassmorphism to static surfaces.

## 8. Motion

| Token | Duration | Use |
|---|---|---|
| `--dur-fast` | 120ms | Hover, press, colour |
| `--dur-base` | 200ms | Reveal, toggle, chevrons, rail growth |
| `--dur-slow` | 320ms | Sheets, page-level entrances |

Easing is `--ease-out` (cubic-bezier(.22,1,.36,1)) for entrances and `--ease-in-out` for state swaps. Buttons
press down 1px. Skeletons use a slow light sweep (`skeleton-sweep`), not a pulse.
**Reduced motion:** a global rule in `index.css` cuts every animation and transition to about 0ms. Spinners
(`animate-spin`) are exempt because they mean "working". Motion never carries information on its own.

## 9. Iconography

- lucide-react only, 16px in controls (`size-4`) and 14px in dense rows. The stroke is lucide's default.
- An icon accompanies a label; it never replaces one, except for universally known icon buttons (close, sign
  out), which must have `aria-label`.
- Decorative icons get `aria-hidden`. External links use `ArrowUpRight`.

## 10. States: loading, empty, error

- **Loading:** skeletons shaped like the content that is coming (rows with a time block, title lines, lanes), with
  `role="status"` and an `aria-label`. Never a lone centred spinner for page content.
- **Empty:** an outlined `00` numeral, a one-line headline, one sentence that says why the screen is empty and
  what fills it, and the one action that helps (for example "Clear filters"). No illustrations.
- **Error (page level):** `role="alert"`, a 3px `bad` left edge on a `bad/10` tint, and the server's message.
  **Error (action level):** a toast. Toasts are dark slips with a coloured left edge per outcome.
- **Disabled:** 45% opacity, and the reason in words nearby or in `title`. A dead button with no explanation is a bug.

## 11. Density

- Default row height in lists is 44-56px. The run of show is roomier (about 110px) because each row carries two lanes.
- Controls are 36px on desktop and grow to 40px on touch (`touch:` variant = width under 768px or a coarse pointer).
- Tables: 36px mono column heads, `px-3 py-2.5` cells.

## 12. Accessibility rules

- **Contrast:** body text must reach at least 4.5:1 and large text or UI boundaries at least 3:1, measured on every surface where the
  pair appears. Text at reduced opacity (`/70`) does not meet this, so use `text-muted-foreground` at full strength.
  Disabled controls and purely decorative marks are exempt, but they still need a text equivalent.
- **Focus:** one language everywhere: a 2px `--ring` (cyan) outline offset by 2px (`:focus-visible` in base). Fields
  draw a cyan border plus a 3px ring at 20% instead. Do not add `outline-none` without a replacement. For stretched
  rows, put the outline on the `::after` overlay (see `TopicRow`).
- **Hit targets:** at least 40px on touch. Checkboxes sit inside a full-height clickable `<label>`.
- **Structure:** use one `h1` per page (inside `PageHeader`), landmark `nav` elements with `aria-label="Main"`, and
  `aria-pressed` on toggle buttons. Status is spelled out in text and never shown by colour alone (the rail has a
  title next to it, and dots have words next to them).
- **Modals:** focus lands on the panel or dialog itself rather than on the primary action. Esc closes it, and
  closing restores the URL.
- No horizontal scrolling at 390px. Check `scrollWidth <= innerWidth`.

## 13. Do and don't

| Don't (it reads as generated) | Do |
|---|---|
| A row of 4 identical stat cards with big numbers | A flow strip if the numbers are stages; a ledger if they are facts; or put the number where the thing is |
| Gradients on buttons, cards and headings | Flat fills; the only gradient is the logo tile |
| Centred card inside a card inside a page | Content on the page with hairlines; one container at most |
| Pills for every tag, filter and status | Squared status tags; plain text plus dot; segmented filters |
| The same radius on everything | 8 for controls, 14 for surfaces, 18 for media, squircles for people |
| Grey pill "active" state in navigation | An edge bookmark in the signal colour plus a numeral |
| Every section with an icon + title + description header | Headers shaped for the section (numbered, eyebrow, or none) |
| Emoji, sparkles, "AI-powered" badges | Plain verbs: Approve, Schedule, Regenerate |
| Spinners for page loads | Content-shaped skeletons |
| Status shown only by colour | Colour plus word plus position on the rail |
| Lorem-style helper text | The exact consequence: "Posts publicly right away", "Also updates Telegram" |
