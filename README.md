# codexonebyhitesh content automation

Daily pipeline: trending topics → reel + carousel → Telegram approval → Instagram,
plus YouTube Shorts for every approved reel.
See `CLAUDE.md` for the full design. Brand settings live in `brand/config.yaml`.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
.venv/Scripts/python -m playwright install chromium       # needed for slide rendering
```

FFmpeg must be on PATH for reel rendering (MoviePy downloads its own via imageio-ffmpeg if missing).

Create `.env` in the project root (never committed):

```
GEMINI_API_KEY=
IG_APP_ID=
IG_APP_SECRET=
IG_USER_ID=
IG_ACCESS_TOKEN=
TG_BOT_TOKEN=
TG_BOT_NAME=
TG_CHAT_ID=
CLOUDINARY_URL=cloudinary://<key>:<secret>@<cloud_name>
GITHUB_TOKEN=            # optional, raises GitHub API rate limit
```

## Admin dashboard

FastAPI in `api/` (it reuses `src/`) and React + Vite + TypeScript + Tailwind + shadcn/ui in `web/`.

**Run it locally.** Either use Docker for everything:
```bash
docker compose up --build            # http://localhost:5173
```
Or run it without Docker for the app, with Postgres still from Docker:
```bash
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://codexone:codexone@localhost:5433/codexone
(cd api && alembic upgrade head)
uvicorn api.app.main:app --reload --port 8000     # API
npm --prefix web install && npm --prefix web run dev   # web on :5173 (proxies /api to :8000)
python -m pytest api/tests -q                         # API tests (SQLite, no Postgres needed)
```

**Sign-in.** There are two ways to sign in:
- **Username + password**: bcrypt-hashed. The admin account is created (or its password updated) from
  `ADMIN_USERNAME` / `ADMIN_PASSWORD` every time the API starts.
- **Sign in with Google**: set `GOOGLE_WEB_CLIENT_ID` / `GOOGLE_WEB_CLIENT_SECRET` (a *Web application* OAuth
  client) and `ALLOWED_GOOGLE_EMAILS` (comma-separated). Only those emails, and only verified ones, can sign in.
  In the client's **Authorized redirect URIs**, register `<PUBLIC_URL>/api/auth/google/callback` for each
  environment, e.g. `http://localhost:5173/api/auth/google/callback`.

How sessions are protected:
- The session is a JWT in an httpOnly cookie: Secure and `__Host-` prefixed in production, SameSite=Lax.
- CSRF: non-GET requests need the `X-CSRF-Token` header. The token is bound to the session and returned
  by `/api/auth/me`.
- Login is rate-limited to 5 failures per IP+username and 20 per IP, per 15 minutes.
- Logout invalidates every session for that user.

| Env var | Purpose |
| --- | --- |
| `JWT_SECRET` | session signing key, 32+ chars (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `SESSION_SECRET` | signs the short-lived OAuth state cookie |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | password admin |
| `GOOGLE_WEB_CLIENT_ID`, `GOOGLE_WEB_CLIENT_SECRET`, `ALLOWED_GOOGLE_EMAILS` | Google sign-in |
| `PUBLIC_URL` | browser-facing URL (OAuth redirects), default `http://localhost:5173` |
| `COOKIE_SECURE` | `false` only for local http; default `true` |
| `WEB_ORIGIN` | only if the web app is on a different origin than the API (enables CORS and SameSite=None) |
| `SESSION_HOURS` | session length, default 12 |

## Database (Postgres)

State (the approval queue, publishing history, brand config, Telegram offset) lives in Postgres when
`DATABASE_URL` is set. Without it, the pipeline uses the JSON files in `data/` and `brand/config.yaml`.
GitHub Actions switches automatically when the `DATABASE_URL` secret exists: it runs migrations and
stops committing `data/*.json`.

Local:
```bash
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://codexone:codexone@localhost:5433/codexone
cd api && alembic upgrade head && cd ..
python scripts/migrate_json_to_db.py --dry-run    # preview
python scripts/migrate_json_to_db.py              # import JSON state (safe to re-run)
```

- **Schema**: `src/db/models.py` (shared by the pipeline and the admin API). Tables: `posts` (queue items),
  `posted_topics` (history and dedupe), `settings` (`brand`, `tg_offset`).
- **Changing the schema**: edit the models, then run `cd api && alembic revision --autogenerate -m "..."` and
  `alembic upgrade head`.
- **Switching production over**:
  1. Create the hosted database.
  2. Run the migrations and the migration script against it, using the latest `data/*.json` from `main`.
  3. Add the `DATABASE_URL` secret.

  After that, the database is the source of truth. The migration script never overwrites a brand config
  that already exists in the database (`--overwrite-brand` to force).

## Run

```bash
python main.py generate            # fetch → rank → write → render → upload → Telegram previews
python main.py poll                # apply button presses, publish approved items after 19:00 IST
python main.py regenerate          # rebuild items where Regenerate was pressed
python main.py refresh-token       # refresh the IG long-lived token
python main.py status              # show the approval queue
```

Every command (and every `src/*.py` module) takes `--dry-run`.

Individual steps:

| Step | Command |
| --- | --- |
| Fetch topics | `python -m src.fetch_topics` |
| Pick topic (Gemini) | `python -m src.rank_topics [--category DSA]` |
| Write content (Gemini, with an accuracy review pass) | `python -m src.gen_content` |
| Render carousel | `python -m src.render_post output/<date>/<slug>/content.json` |
| Render reel | `python -m src.render_reel output/<date>/<slug>/content.json [--music bgm.mp3]` |
| Upload to Cloudinary | `python -m src.upload output/<date>/<slug>` |
| Send previews | `python -m src.approve_bot preview output/<date>/<slug>` |
| Read button presses | `python -m src.approve_bot poll` |
| Check IG token/quota (read-only) | `python -m src.publish check` |
| Publish one approved item | `python -m src.publish item <item_id> [--dry-run]` |

## Approval flow

There are two posting slots a day (`post_times_ist` in `brand/config.yaml`, default **10:00** and **19:00 IST**).
Each slot gets one topic, which becomes one reel and one carousel. Each is approved separately in Telegram:

- **Approve**: publishes at the item's slot time, or within about 20 minutes if the slot has already passed.
- **Reject**: the item is never published.
- **Regenerate**: Gemini rewrites the content, it's re-rendered, and a new preview arrives for the same slot. To
  steer it, reply to the preview message with feedback *before* tapping Regenerate.
- **No decision within 36h**: the preview expires and nothing is posted.

`src/publish.py` refuses anything whose status isn't `approved` (or `failed` after an approval).
Nothing is ever published without an Approve tap.

## YouTube Shorts

Every approved reel is also uploaded to YouTube Shorts: the same MP4, via the YouTube Data API v3.
Instagram goes first, then YouTube. If one fails, the other still happens, each platform's status
is logged in `data/posted.json`, and a retry only redoes the platform that failed. Telegram gets both links.

- **Metadata**: the title is the caption's hook plus `#Shorts` (max 100 chars). The description is caption +
  CTA + hashtags, tags come from the hashtags, the category is 28 (Science & Technology), and
  `selfDeclaredMadeForKids=false`. Privacy comes from `YT_PRIVACY` (default `private`).
- **Choose platforms**: `python main.py poll --platform ig|yt|all` (also on `python -m src.publish item|due`).
- **One-time token**: put the Google OAuth *Desktop* client in `client_secret.json` (gitignored), then run
  `python get_yt_token.py --write-env`. It opens a browser to sign in and writes
  `YT_CLIENT_ID`, `YT_CLIENT_SECRET` and `YT_REFRESH_TOKEN` to `.env` (existing values are kept).
- **Check**: `python -m src.publish_youtube check` and `python -m src.publish_youtube metadata <item_id>`.
- **Record a post made elsewhere**: `python -m src.publish mark <item_id> yt <video-id-or-url>`.
- **Google limits to know**:
  - While the OAuth consent screen is in **Testing**, refresh tokens expire after **7 days**.
    Set it to **In production** in Google Cloud Console.
  - Videos uploaded by an **unverified** API project are locked to **private**, whatever `YT_PRIVACY` says,
    until the project passes Google's YouTube API audit.
  - Each upload costs 1,600 of the 10,000 daily quota units, so about 6 uploads a day.

## Animated walkthroughs

For algorithm and data-structure topics, Gemini adds a `demo`: a small concrete input traced step by step.

- **Kinds**: `array`, `string` (one character per cell), `linked_list` (optionally with a cycle), `stack`.
- **Each step** has pointers (`i`, `lo`, `slow`, …), highlighted cells, done cells, optional new values,
  a short caption, and one narrated sentence.
- **Reel**: a "Watch it run" scene after point 1. Each step gets its own voiceover clip, state changes
  crossfade, pointer labels glide between cells, and linked-list pointers hop node by node along
  the `next` links, so a wrap around a cycle is visible.
- **Carousel**: `visual` slides show 2 frozen steps each.
- **Accuracy**: code checks indices and sizes, and the review pass re-simulates the trace step by step.

The shared drawing code is in `templates/viz.js` and `templates/viz.css`.

Voiceover: reels rotate through the `voices` list in `brand/config.yaml` in order, one voice per reel. The Telegram preview shows which voice was used. Edit the list to add or drop voices (`python -c "import asyncio, edge_tts; print([v['ShortName'] for v in asyncio.run(edge_tts.list_voices()) if v['Locale'].startswith('en-')])"` lists them).

Background music is optional: set `reel.music` in `brand/config.yaml` to an mp3 file or a folder of mp3s.

## GitHub Actions

| Workflow | When (IST) | What |
| --- | --- | --- |
| `daily-generate.yml` | 08:00 (for the 10:00 slot) and 18:00 (for the 19:00 slot) | `main.py generate --slot …` |
| `poll-approvals.yml` | every 20 min, 07:30–13:10 and 17:30–00:10 | `main.py poll`, and `regenerate` if needed |
| `refresh-token.yml` | Mondays 08:30 | refreshes the token and rewrites the `IG_ACCESS_TOKEN` secret |

The job state (`data/*.json`) is committed back to the repo by `codexone-bot`.
Poll runs with nothing waiting exit within seconds (`scripts/has_work.py`), which keeps Actions minutes low.
Each slot's topic avoids anything queued or posted recently, so the two daily posts never repeat.
To post at different times, change `post_times_ist` and the two crons in `daily-generate.yml` together.

### On-time scheduling with cron-job.org

GitHub's own `schedule:` triggers can run hours late. [cron-job.org](https://cron-job.org) (free) starts the
workflows at exact times through GitHub's `workflow_dispatch` API instead. The GitHub schedules stay on as a
backup. Double triggers are harmless: a slot that already has a post, or that passed more than 2h ago, is skipped.

1. **GitHub token for cron-job.org**: go to github.com → Settings → Developer settings → Fine-grained tokens →
   Generate. Repository access: only `codexone-automation`. Permissions: **Actions: Read and write**.
2. **cron-job.org**: set your account time zone (Settings) to **Asia/Kolkata**, then create 3 jobs. All of them are
   `POST` requests with these headers:
   `Accept: application/vnd.github+json`, `Authorization: Bearer <token>`,
   `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`.

| Job | URL (`https://api.github.com/repos/hitesh2327/codexone-automation/actions/workflows/…`) | Schedule (IST) | Body |
| --- | --- | --- | --- |
| Generate 10:00 post | `…/daily-generate.yml/dispatches` | daily 08:00 | `{"ref":"main","inputs":{"slot":"10:00"}}` |
| Generate 19:00 post | `…/daily-generate.yml/dispatches` | daily 18:00 | `{"ref":"main","inputs":{"slot":"19:00"}}` |
| Poll approvals | `…/poll-approvals.yml/dispatches` | every 15 min, hours 7–13 and 17–23 | `{"ref":"main"}` |

A successful trigger returns **HTTP 204** and a new `workflow_dispatch` run appears under Actions.

### Secrets

| Secret | Value |
| --- | --- |
| `GEMINI_API_KEY` | Google AI Studio key |
| `IG_USER_ID` | numeric IG user id (`python -m src.publish check` prints it) |
| `IG_ACCESS_TOKEN` | long-lived Instagram token |
| `YT_CLIENT_ID` | Google OAuth Desktop client id (from `.env`) |
| `YT_CLIENT_SECRET` | Google OAuth client secret (from `.env`) |
| `YT_REFRESH_TOKEN` | from `get_yt_token.py` (in `.env`) |
| `CLOUDINARY_URL` | `cloudinary://<key>:<secret>@<cloud>` |
| `TG_BOT_TOKEN` | Telegram bot token |
| `TG_CHAT_ID` | your chat id (only presses from this chat count) |
| `DATABASE_URL` | hosted Postgres URL (optional; enables DB mode, see Database) |
| `GH_PAT` | fine-grained PAT for this repo with **Secrets: read/write** (used by the token refresh) |

## Modules

- `src/config.py`: paths, `.env`/Secrets loading (`get_env`), and brand config
- `src/logger.py`: console logging plus `logs/run_<date>.log`
- `src/llm.py`: Gemini structured-JSON calls with retries and fallback models (`GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`)
- `src/html_render.py`: Jinja2 templates, Pygments highlighting, and Playwright screenshots
- `src/queue_store.py`: the approval queue and `posted.json` (per-platform status)
- `src/publish_youtube.py`: YouTube Shorts upload (resumable, with retries) and its metadata
- `templates/`: `title.html`, `content.html` (with code support), `cta.html`, `reel.html`
