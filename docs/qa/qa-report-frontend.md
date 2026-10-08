# QA report: frontend (web/, HEAD b7dacd8 + working tree of 2026-10-07)

QA: Natasha Romanoff. Date: 2026-10-07. Scope: web/src (React 19 + Vite 8 + react-router 7), first adversarial pass.
Status: IN PROGRESS (sections are appended as each area completes).

**Counts: (filled in at the end)**

## Environment used for every repro

- Backend: the repo's FastAPI app run from the working tree with `uvicorn` on `127.0.0.1:8012`, against a throwaway
  database `qa_front` in the local docker container `codexone-automation-db-1` (port 5433). Never Neon, never AWS.
  `SP=<scratchpad>/qa`; `$SP/qaenv.py` is imported first: every secret name in `src.redact.SECRET_ENV_NAMES` is replaced by a
  `SENTINEL-...` value, SMTP/Google/admin settings are blanked, `MAIL_DRIVER=console`, `COOKIE_SECURE=false`, and
  every non-loopback socket connect / DNS lookup is blocked in-process.
- Users: `qa_front` and `qa_other`, created by `$SP/seed.py` with a random password written to `$SP/pw.txt`
  (bcrypt via `api.app.security.hash_password`, never printed).
- Frontend: `cd web && API_PROXY_TARGET=http://127.0.0.1:8012 npx vite --port 5182 --strictPort` (real dev server).
- Browser: Playwright 1.x + Chromium (headless) from `.venv`. Scripts are `$SP/*.py`; helpers in `$SP/h.py`.
- Each finding says whether it was reproduced against the REAL dev server + API ("real") or with `page.route("**/api/**")`
  mocks for a specific backend state ("mock"; the mock bodies are modified copies of real responses saved by `$SP/grab.py`).

---

## Area 1: XSS / injection surfaces

Static audit first: `grep -rn "dangerouslySetInnerHTML\|innerHTML\|outerHTML\|insertAdjacentHTML\|document.write\|eval(\|new Function" web/src`
returns **nothing**. Every API string is rendered as a React text child or attribute. The only non-React DOM writes
are `lib/brand.ts` (`style.setProperty` behind `HEX`/`FONT` regexes; a `<link>` to fonts.googleapis.com built with
`encodeURIComponent`). Hrefs built from data: Posts platform marks (`r.url`), post panel "Open" + slide links, the reel
`<video src/poster>`, Dashboard `Platforms` "Open" (`r.url`), Generate history + RunTracker (`github_run_url`), Config
"Fix" (`m.fix`), Telegram bot button (`https://t.me/${bot}`), router `Link`s with ids interpolated.

Dynamic test: `$SP/x1.py` (real server for profile fields; mocks for everything else). Payloads:
`<img src=x onerror="window.__xss=...">`, `<svg/onload=...>`, `javascript:window.__xss=777`,
`data:text/html,<script>...`, markdown `[click](javascript:alert(1))`, RTL override U+202E, zero-width U+200B, BEL,
200 000-character strings. After every page the probe checks `window.__xss`, `img[src="x"]`, any `[onerror]/[onload]`
element, and every `a[href]` with a `javascript:/data:/vbscript:` scheme.

Observed (excerpt of `x1.py` output):

```
PATCH profile -> 200 {"name":"<img src=x onerror=\"window.__xss=...\">","job_title":"<svg/onload=...>", ...}   (real server stores it)
PATCH username html -> 422 (server rejects)
real /profile        {"xss": null, "injectedImg": 0, "onerrorAttrs": 0, "svg": 0, "jsHrefs": []}   h1 shows the literal text
real /dashboard      {"xss": null, ...}                                                           sidebar name is literal text
mock /posts panel    jsHrefs: ["javascript:throw new Error('React has blocked a javascript: URL as a security precaution.')",
                               "data:text/html,<script>opener&&(opener.__xss=5)</script>", ...]   xss: null
video src/poster:    ["javascript:throw new Error('React has blocked ...')", "javascript:x"]   (poster is not a script sink)
mock /logs expanded  xss: null; post link href: /posts?post=x%22%3E%3Cimg%20... (encoded)
mock /dashboard live xss: null; 10 "Open" links -> React's blocked-URL stub
mock /generate       xss: null; github_run_url javascript: -> blocked stub
mock /config         xss: null; Fix href javascript: -> blocked stub; t.me link https://t.me/x%22%20onmouseover=...?start=setup
/login?error=        xss: null; alert text: "Your account is locked. Call support on +1-800-SCAM <img ...>"
long strings         list 0.63 s, panel 0.33 s, scrollWidth 1280 == innerWidth 1280 (no horizontal overflow)
```

`$SP/x1b.py`: clicking a Posts platform mark whose `url` is a `data:text/html,...` phishing page opens **no tab** in
Chromium (top-frame data: navigation is blocked; `ctx.pages` stays at 1, opener title unchanged).

### Findings (Area 1)

**FE-L-01 (Low) Login page renders any text from `?error=` as an official red alert (content spoofing)**
- Area: Login. File: `web/src/pages/Login.tsx:54` (`useState(params.get("error"))`), rendered at `:137-141`.
- Repro (real): open `http://localhost:5182/login?error=Your%20account%20is%20locked.%20Call%20support%20on%20%2B1-800-SCAM`.
- Observed: the sign-in card shows a `role="alert"` box "Your account is locked. Call support on +1-800-SCAM" in the
  product's error style (screenshot `$SP/shots/x1_login_error.png`). Text only, no script.
- Expected: only messages the product wrote. The backend (`api/app/routes/auth.py:131-165`) sends four fixed messages
  (one embeds the refused email).
- Impact: a phishing link on the customer's real domain can show attacker-chosen instructions on the real login page.
- Fix: redirect with an error code (`?error=google_cancelled|no_verified_email|not_allowed|disabled`), map codes to
  fixed strings client-side, ignore unknown codes, and drop `error` from the URL after reading it.

**FE-L-02 (Low) URLs from API data are used as hrefs/src with no scheme allowlist**
- Files: `web/src/pages/Posts.tsx:36`, `web/src/components/post-panel.tsx:103, 460-461, 491`,
  `web/src/components/dashboard/shipped.tsx:44, 84`, `web/src/pages/Generate.tsx:72`, `web/src/components/run-tracker.tsx:111`,
  `web/src/pages/Config.tsx:62`.
- Repro (mock): `x1.py` sections 2/4/5/6 serve `javascript:` and `data:` values in `platforms.*.url`, `media.carousel[]`,
  `media.reel`, `recent[].url`, `github_run_url`, `readiness.missing[].fix`.
- Observed: nothing executes today, but only because React 19 rewrites `javascript:` hrefs/src to a throwing stub and
  Chromium refuses top-frame `data:` navigations. `data:` hrefs are rendered as-is, and any `https://attacker/...` would
  be a live link labelled "Open on Instagram".
- Expected: links built from stored data are `https:` (platform links: the platform's host).
- Impact: defence in depth. The backend writes these (Graph API permalinks, Cloudinary URLs, GitHub run URLs), but
  generated content starts from untrusted internet text (HN/Reddit/dev.to), so a future backend bug that copies a source
  URL into one of these fields would surface as a clickable link with no client check.
- Fix: one helper `safeHref(url, hosts?)` returning the URL only for `https:` (optionally host-allowlisted: instagram.com,
  youtube.com/youtu.be, res.cloudinary.com, github.com), used at every site above.

**FE-L-03 (Low) Router links interpolate server ids into query strings without encoding**
- Files: `web/src/components/generated-by.tsx:21` (`/logs?q=${job.id}`), `web/src/components/run-tracker.tsx:97,121`,
  `web/src/pages/Generate.tsx:70`, `web/src/components/dashboard/shipped.tsx:104` (`/posts?post=${it.post_id}`).
- Repro (mock): `x1.py` section 2: job id `<img ...>` produced href `/logs?q=<img src=x onerror="window.__xss=...">`
  (inert text). An id containing `&status=failed` would add a second filter parameter.
- Expected: `encodeURIComponent`, as `Logs.tsx:74` already does.
- Impact: none today (ids are server-generated); robustness only.

### Examined, no findings (Area 1)

| Surface | Check that proves it |
|---|---|
| Profile name / job title / bio (stored HTML) | real server stores `<img onerror>`/`<svg onload>`; `/profile` + sidebar: `xss:null, injectedImg:0, onerrorAttrs:0` |
| Post topic, caption (incl. markdown link), hashtags, feedback, platform error, YouTube title/description/tags, category | mock `/posts` list + panel, both tabs: `xss:null`, no injected elements; markdown shown literally |
| Logs message, source, event, actor, post_id, detail JSON (`<pre>` via `JSON.stringify`) | mock `/logs`, row expanded: `xss:null`; post link encoded |
| Dashboard handle, recent post titles, activity message/actor, gallery thumb `javascript:` | mock live overview: `xss:null` |
| Generate topic, requested_by, failure message, source_url | mock `/generate`: `xss:null` |
| Config readiness label/detail, check label/evidence/message/hint, Telegram bot name in t.me URL | mock `/config`: `xss:null`; quotes percent-encoded inside the t.me path |
| `javascript:` in any href/src | React 19 replaced each with its blocked-URL stub; clicking "Open" ran nothing |
| RTL override / zero-width / BEL | rendered inside their own text node; the U+202E reversal does not leak into neighbouring UI. Cosmetic only |
| 200 000-character topic/caption, 50 000-char hashtag | list 0.63 s, panel 0.33 s, no horizontal overflow (`break-words`/`truncate` hold) |
| Brand colours/fonts injected into CSS | `HEX = /^#[0-9a-f]{3,8}$/i` and `FONT = /^[\w\s-]{1,40}$/` gate every value before `setProperty` (code audit) |

