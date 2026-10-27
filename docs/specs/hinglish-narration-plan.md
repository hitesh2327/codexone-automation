# Hinglish narration: implementation plan

Status: plan, not started. Written 2026-10-27 against `main` @ 6901866.

## 1. Goal and scope

Reels are narrated in English today. Sometimes we want the voice in **Hinglish**: conversational Hindi with
English tech terms ("Socho, har request seedha database pe jaaye toh kya hoga? Yahin cache kaam aata hai.").

| Decision | Choice |
|---|---|
| Default narration | English, for every scheduled and auto run (no change) |
| How Hinglish is chosen | Manually, per run, on the dashboard's Generate page only |
| What is Hinglish | Only the reel's spoken narration |
| Stays English | Carousel, on-screen reel text (title, headings, diagram labels, counters, code, cheat sheet), IG caption, hashtags, YouTube title and description |
| Subtitles | None on Hinglish reels |
| Regenerate | Keeps the post's language |

Out of scope: Hindi on-screen text, Hindi captions, scheduling Hinglish automatically, a Telegram "in Hindi" switch.
Each is a small follow-up once this ships.

### How the script is written

The narration the model writes is **Devanagari for Hindi words, Latin script for tech terms**:
`सोचो, हर request सीधा database पे जाए तो क्या होगा? यहीं cache काम आता है।`
The Hindi voices pronounce Devanagari natively and read embedded English words as English. Hinglish
in Latin script ("socho, har request...") makes the Hindi voices guess, and comes out wrong. Since there are
no subtitles, nobody sees this text; it only decides how the voice sounds.

## 2. Where English is fixed today

| Place | What | Change |
|---|---|---|
| `brand/config.yaml:12` `voices` | English voices only | add `voices_hi` |
| `brand/config.yaml:20` `language` | "English, simple, beginner-friendly", used by the classic and ranking prompts | leave; per-post language overrides narration only |
| `src/reel_v2/spec.py` `_prompt` / `_review_prompt` | no language at all (English implied) | Hinglish block when `language="hi"` |
| `src/reel_v2/spec.py:33` `MAX_WORDS = 75` | tuned on English voices | per-language cap |
| `src/reel_v2/render.py:130` and `spec.validate` | trigger matching strips `.,?!'"` | also strip `।` |
| `src/hookscore.py:41` `WORD_RE` | Latin letters only | skip `pick_hook` for Hinglish |
| `src/render_reel.py:71` `pick_voice` | one rotation | rotate per language |
| `templates/reel_v2/reel.html` `#caption`, `templates/reel.html` `#sub` | word-highlight subtitles | off for Hinglish |
| `src/publish_youtube.py:135` | `defaultAudioLanguage: "en"` | `"hi"` for Hinglish reels |

## 3. Data flow after the change

```
Generate page (Narration: English | Hinglish)
  -> POST /api/generate {language}                      api/app/routes/generate.py
  -> generation_jobs.language                           src/generation.py create()
  -> workflow_dispatch (unchanged inputs, request_id)   .github/workflows/daily-generate.yml
  -> main.py generate: generation.job_language(request_id) -> "hi"
  -> gen_content.generate(topic, language=...)          Content.language, scene prompt in Hinglish
  -> render_reel(..., voice=pick_voice(language))       Hindi voice, no subtitles
  -> items_from_post -> Item.language / posts.language  Telegram preview shows "Narration: Hinglish"
  -> Regenerate reuses Item.language                    main.py cmd_regenerate
  -> publish: YouTube defaultAudioLanguage = "hi"
```

Scheduled runs never pass `language`, so they stay `en` at every step.

## 4. Steps

One commit per step, on a fresh branch from `main`. Every step keeps the suite green and adds its own tests.

### Step 0: probe the Hindi voices (blocks the numbers in step 4)

Edge TTS is blocked in the dev sandbox, so this runs in GitHub Actions (or on a laptop).

- New `scripts/tts_probe.py`: for `hi-IN-MadhurNeural`, `hi-IN-SwaraNeural` and, for comparison,
  `en-US-AndrewMultilingualNeural`, synthesize 3 sample Hinglish lines (Devanagari + English terms) at +6%, and print:
  duration, words per second, whether `WordBoundary` events come back, and the boundary texts (to see how
  English words inside Devanagari are split, and whether `।` arrives attached to the last word).
- Run it once via a temporary `workflow_dispatch` workflow, or locally. Delete the temporary workflow afterwards.
- **Outputs:** `MAX_WORDS_HI` (aim for ~27 s of speech at +6%, the same headroom as English) and a yes/no on word
  boundaries. If boundaries are missing, step 4's timing fallback becomes required, not optional.
- **Done when:** the numbers are written into this doc (section 7).

### Step 1: store the language

- `src/gen_content.py` `Content`: `language: Literal["en", "hi"] = "en"`. Saved in `content.json`, so a
  re-render from disk keeps it. Old `content.json` files load as `en`.
- `src/queue_store.py` `Item`: `language: Literal["en", "hi"] = "en"` (next to `voice`). Row mapping is by
  field name (`_to_row_values`/`_from_row`), so no mapping code changes.
- `src/db/models.py`:
  - `Post.language: Mapped[str] = mapped_column(String(2), default="en", server_default="en")`
  - `GenerationJob.language`: same.
- New Alembic migration in `api/migrations/versions/` (additive, single head; `tests/test_workflows.py`
  checks there is one head): add both columns with `server_default 'en'`. Existing rows read as English.
  Per the QA-M-02 policy, push the migration in its own commit before code that reads the column.
- `src/approve_bot.items_from_post`: copy `content.language` onto each new `Item`.
- `api/app/routes/posts.py:35`: return `language` with the post (next to `voice`).
- **Tests:** `Item` round-trips `language` through the DB and file modes; an old row without the column reads `en`;
  `alembic check` shows no drift.

### Step 2: carry the choice from the Generate page to the run

- `api/app/routes/generate.py` `GenerateBody`: `language: Literal["en", "hi"] = "en"`. Pass it to
  `generation.create(...)`, add it to the `generate.requested` activity detail, and add
  `"language": body.language` to the dispatch `inputs` (line ~320).
- `src/generation.py`: `create()` and `Reporter.begin()` take and store `language`; the job dict (line ~201)
  returns it, so the run tracker and history can show it.
- `.github/workflows/daily-generate.yml`: **no change** (as built). The workflow already has 10 inputs, the
  limit `tests/test_workflows.py` enforces, so the language is not a dispatch input. A dashboard run already
  passes `--request-id`, and its generation job carries `language`; `main.py` reads it with
  `generation.job_language(request_id)`.
- `main.py`:
  - `generate` gets `--language`, `choices=["en", "hi"]`, `default="en"`.
  - `cmd_generate` resolves `--language`, else `generation.job_language(--request-id)`, else `en`, and passes it to `gen_content.generate(topic, language=args.language)` (line ~149), to
    `render_reel.pick_voice(args.language)` (line ~162), and to `Reporter.begin`.
- **Tests:** an API body with `language: "hi"` is stored on the job and is not a dispatch input; a bad value is a
  422; omitted means `en`; a dashboard job's `hi` reaches the writer; a scheduled run is `en`; `--language xx` is
  rejected by argparse.

### Step 3: write the Hinglish script

New-design engine (`src/reel_v2/spec.py`):

- `generate(topic, category, angle, feedback, language="en")` and `_prompt(..., language)`. For `hi`, append a
  `NARRATION LANGUAGE (Hinglish)` block:
  - Narration only: conversational Hinglish, the way Indian tech creators talk. Hindi words in Devanagari; tech
    terms, product names, commands and numbers in Latin script (`cache`, `database`, `O(log n)`).
  - Every other field stays English: title, subtitle, cover_lead, headings, captions, slide text, cheat sheet,
    caption, hashtags.
  - `trigger` is one word copied exactly from the narration (often the English tech word, which also makes timing
    robust).
  - Short sentences, `।` or `?` to end them; spell symbols in words in Hindi (`O of n` stays English).
  - Last beat: the follow CTA in Hinglish ("Aise aur explainers ke liye follow karo @codexonebyhitesh").
- `_review_prompt`: add "The narration is in Hinglish (Devanagari + English terms): check that it says the same
  thing as the on-screen text and is technically correct."
- `MAX_WORDS`: becomes `MAX_WORDS = {"en": 75, "hi": <from step 0>}`; `validate(spec, language)` uses the cap
  for the language. `SceneSpec` gets no language field; the language lives on `Content` and is passed in.
- `validate` trigger check: strip `।` as well as `.,?!'"`.
- `validate` script checks for `hi`: every beat's narration contains Devanagari (so it is not Hinglish in Latin
  script), and no on-screen field (title, headings, captions, slide text, node labels, counters, cheat sheet)
  contains Devanagari. Both go through the existing rewrite-once loop in `generate()`.
- `src/reel_v2/pipeline.to_content(spec, title, category, language)`: sets `Content.language`.

Classic engine (`src/gen_content.py`, only reached when v2 fails):

- `generate(topic, feedback="", language="en")`: pass `language` to `_write_prompt`, which replaces the
  `Language: {brand['language']}` line with the Hinglish narration rule for `hi` (narration fields only:
  `hook_narration`, `points[].narration`, `demo.steps[].narration`, `cta_narration`).
- Skip `pick_hook` when `language == "hi"` (`hookscore` counts Latin words only, so it would score every hook
  as empty).
- Set `content.language = language` before returning, on both paths.

**Tests:** the Hinglish block is in the prompt only for `hi`; `validate` uses the right word cap; a Devanagari trigger
ending in `।` matches; the classic path skips `pick_hook` for `hi`; `Content.language` is set on both paths.

### Step 4: voice and rendering

Voices:

- `brand/config.yaml`: add
  ```yaml
  # Hinglish reels (Generate page > Narration: Hinglish) rotate through these.
  voices_hi:
    - hi-IN-MadhurNeural   # male
    - hi-IN-SwaraNeural    # female
  ```
  The production brand is a DB copy (`load_brand()`), so the code must not depend on the key existing:
  `DEFAULT_VOICES_HI` in `src/render_reel.py` is used when `voices_hi` is missing.
- `pick_voice(language="en")`: rotates over `voices` or `voices_hi`; the count is of queued reels with that
  language and a voice, so each rotation is independent.
- `voice_from_feedback(feedback, language="en")`: looks only in that language's list, so "use Swara" on a
  Hinglish reel works and never switches an English reel to a Hindi voice.
- `voice_short_name` already parses `hi-IN-MadhurNeural` to `Madhur`.
- `speakable()` (brand pronunciations) applies unchanged. Check in step 0 that "Code Xone By Hitesh" sounds right
  with the Hindi voices; add a `pronunciations_hi` map only if needed.

No subtitles:

- v2 (`src/reel_v2/render.py` `timeline()`): when the language is `hi`, emit `subs: []`. `reel.html` already
  treats missing subs as none (`TL.subs && TL.subs[bi]`), so the template needs no change. Word timings are
  still computed: trigger timing uses them.
- `render_reel(spec, out_dir, voice, preview, language="en")` in `src/reel_v2/render.py`, and the classic
  `src/render_reel.render_reel(content, ...)` reads `content.language`. Classic: skip the subtitle layers
  (`sub_layers`, line ~426) for `hi`.
- `MAX_RATE` speed-up loop stays as is; it already keeps the reel under 30 s whatever the language.

Timing fallback (required if step 0 shows no word boundaries for Hindi voices, otherwise a safety net):

- `_voice_beats` raises "no word boundaries" today, which skips the whole reel (`render_reel.py:377`). For
  `hi`, accept a beat with no boundaries and place its trigger at the fraction of the beat where the trigger word
  sits in the narration (word index / word count x beat duration). Log a warning.
- Classic `synthesize` (`render_reel.py:137`): same, for `hi` only; the demo pointer timing uses part starts,
  not words.

**Tests:** `pick_voice("hi")` rotates within `voices_hi` and falls back to the defaults when the key is missing;
`voice_from_feedback("use Swara", "hi")` finds Swara and `("use Swara", "en")` returns None; the v2 timeline for
`hi` has empty `subs` and correct triggers; the fallback places a trigger proportionally when boundaries are empty.

### Step 5: regenerate, preview, publish

- `main.py cmd_regenerate`: `content = gen_content.generate(topic, feedback, language=first.language)` and
  `pick_voice(first.language)`; `voice_from_feedback(..., first.language)`.
- `src/approve_bot.py` preview text (next to the voice line, ~185): add `🗣 Narration: Hinglish` when
  `item.language == "hi"`.
- `src/publish_youtube.py`: `_metadata(...)` takes `audio_language`; `publish_reel` passes `"hi"` for
  Hinglish items (`defaultAudioLanguage`); `defaultLanguage` stays `"en"` (title and description are English).
  Thread `item.language` through from `src/publish.py:207`.
- Instagram: no change.
- **Tests:** regenerating a Hinglish item produces a Hinglish item; the preview shows the line only for `hi`;
  YouTube metadata has `defaultAudioLanguage: "hi"` for a Hinglish reel and `"en"` otherwise.

### Step 6: Generate page UI (`web/`)

Follow CLAUDE.md: use the `mintly-ui` skill (and `frontend-design` if installed), copy the closest pattern from
`docs/design/design-system.md`, no "codexone" in UI text, and run the screenshot loop (at least twice, 390 px width,
keyboard focus).

- `web/src/components/generate-form.tsx`:
  - State `const [language, setLanguage] = useState<"en" | "hi">("en")`.
  - A "Narration" field after Category: a two-option radio group (`components/ui/radio-group.tsx`, already in the
    kit) with "English" (default) and "Hinglish". Hint under it: "Hinglish: Hindi voice, no subtitles. Carousel and
    caption stay English."
  - Send `language` in the POST body (line ~99); show it in the confirm summary (line ~250) as
    "Narration: English | Hinglish".
  - Reset to English after a run is requested; `Prefill` (Retry from history) carries the job's `language`.
- `web/src/lib/generate-format.ts`: the job label adds "· Hinglish" for `hi` jobs (run tracker and history).
- Posts page (optional, small): a "Hinglish" badge on reel cards whose `language` is `hi`.
- **Tests:** `web/tests` for the body and the label; `npx tsc -b` clean; `npm test` passes.

### Step 7: end-to-end checks

1. Full suite: `python -m pytest api/tests tests -q -p no:cacheprovider` (known: 3 date-dependent failures on
   `main`, unrelated).
2. Stubbed end to end (no network): the same harness used for the DSA and Interview check. Gemini returns a
   hand-written Hinglish scene; TTS returns silent audio with word timings, then a run with **no** word timings to
   exercise the fallback. Check: `Content.language == "hi"`, no subtitle layer in the frames, triggers in order,
   reel under 30 s, carousel is English.
3. Generate-page dry run (`dry_run=true` dispatch) with Hinglish: the workflow receives `--language hi` and the
   job shows "Hinglish".
4. One real Hinglish post: generate from the dashboard, listen to the reel in the Telegram preview, approve,
   check the YouTube audio language. Only then call it done.

## 5. Files touched

| File | Step |
|---|---|
| `scripts/tts_probe.py` (new, plus a temporary workflow) | 0 |
| `src/gen_content.py`, `src/queue_store.py`, `src/db/models.py`, new migration, `src/approve_bot.py`, `api/app/routes/posts.py` | 1 |
| `api/app/routes/generate.py`, `src/generation.py`, `.github/workflows/daily-generate.yml`, `main.py` | 2 |
| `src/reel_v2/spec.py`, `src/reel_v2/pipeline.py`, `src/gen_content.py` | 3 |
| `brand/config.yaml`, `src/render_reel.py`, `src/reel_v2/render.py` | 4 |
| `main.py`, `src/approve_bot.py`, `src/publish_youtube.py`, `src/publish.py` | 5 |
| `web/src/components/generate-form.tsx`, `web/src/lib/generate-format.ts`, optional Posts badge | 6 |
| tests: `tests/test_reel_v2_pipeline.py`, `tests/test_reel_v2_spec.py`, `tests/test_workflows.py`, `api/tests/test_generate.py`, `api/tests/test_posts.py`, `web/tests/generate.test.mts` | all |

## 6. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Hindi voices return no word boundaries | Reel skipped today | Step 4 timing fallback; step 0 tells us up front |
| Hinglish is longer when spoken than English | Reel over 30 s | Per-language `MAX_WORDS` from step 0; the existing speed-up loop (+30% max) |
| Model writes Hinglish in Latin script | Mispronounced narration | Prompt rule plus a validator check: `hi` narration must contain Devanagari; one rewrite, then fail over to classic with a Telegram warning |
| Model translates on-screen text too | Hindi in fonts without Devanagari (Inter, JetBrains Mono) | Prompt rule plus a validator check: on-screen fields must not contain Devanagari |
| Edge TTS blocked on a cloud IP | Reel skipped (as today for English) | Unchanged behaviour: carousel still publishes |
| Brand in DB lacks `voices_hi` | No Hindi voice | `DEFAULT_VOICES_HI` in code |

## 7. Step 0 results

Run 2026-10-27 on a GitHub-hosted runner (`scripts/tts_probe.py`, run 40472576756), 4 Hinglish lines
(Devanagari + English terms, 62 words) at +6%:

| Voice | Words/s | Word boundaries |
|---|---|---|
| hi-IN-MadhurNeural | 2.24 | 62/62 |
| hi-IN-SwaraNeural | 2.38 | 62/62 |
| en-US-AndrewMultilingualNeural (comparison) | 2.64 | 62/62 |
| English voices on English text (reference, MAX_WORDS=75 in ~27 s) | 2.78 | - |

- Edge TTS works from GitHub runners for both Hindi voices.
- Every word gets a boundary, Devanagari and English alike; punctuation (`,` `?` `।`) is not attached to the
  boundary text. The timing fallback in step 4 is a safety net, not required.
- English terms inside Devanagari come back as separate words (`Binary | search | हर | step`), so English
  trigger words match exactly.
- **`MAX_WORDS_HI = 60`** (27 s on the slower Madhur voice). The speed-up loop (+30% max) covers the rest.
- The brand pronunciation "Code Xone By Hitesh" is spoken as four words by both Hindi voices; listen to the
  run's `tts-probe` artifact to confirm it sounds right.
