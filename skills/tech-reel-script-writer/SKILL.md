---
name: tech-reel-script-writer
description: Writes accurate 25-30 second vertical-video scripts (Instagram Reels, YouTube Shorts, TikTok) that explain one programming, DSA, system design, AI/ML, OS or tech-interview topic, fact-checks every claim, and validates length and on-screen limits with a bundled checker. Use when asked to script a reel/short/TikTok/explainer about a technical topic, plan a week of such scripts, or fix an existing draft that is too long, vague or inaccurate. Not for long-form YouTube videos, blog posts, or non-technical topics.
---

# Tech Reel Script Writer

Turns one technical topic into a tight 25-30 second vertical-video script that a developer audience
will trust: a hook, one idea per beat, a worked example with real numbers, a payoff and a call to
action. Every factual claim is listed and checked, and length and on-screen limits are validated by
`scripts/check.py`, because one wrong command or invented statistic in the comments costs more reach
than a weak hook.

## 1. Inputs

Ask only for what you can't infer; use the defaults otherwise.

| Input | Options | Default |
|---|---|---|
| Mode | `write` a new script, or `fix` a draft the user gives you | `write` |
| Topic | anything technical | **required** (in fix mode: taken from the draft) |
| Platform | `instagram`, `youtube`, `tiktok` | `instagram` |
| Format | `animated` (diagram / motion graphics), `screen` (screen recording), `talking` (talking head + overlays) | `animated` |
| Audience | `beginner`, `intermediate`, `senior` | `beginner` |
| Voice | own voice / TTS / non-English narration (sets the word cap, see section 3) | own voice |
| Handle | for the CTA | ask once |
| Batch | one script, or N scripts (e.g. "a week") | one |

## 2. Workflow

Follow these steps in order. Never skip 5 and 6.

1. **Pick the category** (section 5). A topic that fits two takes the one whose example tells the story.
2. **Find the one mechanism.** A 30-second video explains *one* thing: how it works, or why it beats
   the naive way. Write it as one sentence first. If it needs "and" twice, narrow the topic
   ("Load balancing" -> "Why round-robin breaks with sticky sessions").
3. **Work out a concrete example** with small real inputs (6 array values, 3 servers, one request).
   Compute it yourself, step by step: every number on screen must be what this example produces.
4. **Draft** in the output format (section 8), following the structure (section 3) and limits (section 4).
5. **Fact-check** (section 6): list every claim, verify each, fix or move it to "Unverified".
6. **Validate**: save the script as `reel-scripts/<YYYY-MM-DD>-<topic-slug>.md` in the user's project
   (create the folder; use another path if the user names one), then run
   `python3 <this skill's folder>/scripts/check.py <file>` (on Windows: `py` instead of `python3`).
   For a slower voice or non-English narration add `--max-words 60 --wps 2.3`. The checker counts words,
   beats and every on-screen limit, and checks the hooks, the snippet, the comparison table, the hashtags
   and the YouTube title. Fix every FAIL, read every WARN, and re-run until it passes. If you can't run code, do the same checks by hand,
   beat by beat, counting words one at a time.
7. **Hand over** the final script and the checker's result.

**Batch mode:** plan all topics first as a numbered list (title + one-line mechanism), make sure no two
share a mechanism, example or hook pattern, then write each script and validate them all in one file
(`reel-scripts/<YYYY-MM-DD>-batch.md`, one `## Title` per script).

**Fix mode** (the user gives you their own draft, in any shape):
1. Read it and write down its mechanism in one sentence and every claim it makes.
2. Rewrite it into the output format, keeping the user's wording and example wherever they work.
3. Apply steps 5-6 (fact-check, validate) exactly as for a new script.
4. Add a `### Changes` section: each change and why (too long, wrong command, absolute claim,
   two ideas in one beat...), so the user learns the rules instead of just getting a new script.

## 3. Structure: 5-8 beats, max 75 spoken words

A beat is one moment: one change on screen, 1-2 short spoken sentences, **max 16 words**.

| Beat | Job | Rule |
|---|---|---|
| 1. Hook | Stop the scroll | A curiosity question or a surprising true fact, **with the topic name within the first 6 words**. No greetings, no "in this video". |
| 2. The problem / naive way | Tension | Show what goes wrong without the idea, using the example's real numbers. |
| Middle beats | The mechanism | Exactly one step per beat. Two changes = two beats ("Found a bug?" then "Flip back."). |
| Last | Payoff + CTA | State the benefit as the mechanism (not a made-up number), then the one CTA. |

**Length:** total narration **max 75 words** (about 27 s at ~2.7 words per second, a normal speaking
rate; most TTS voices land within 25-30 s). Use **60** for slower voices and non-English narration.

**Hooks:** always give 3 options of 5-12 words, each with a different angle (a question, a
counter-intuitive true fact, a common mistake), and mark the strongest `(recommended)`. Beat 1 uses it.

**Audience:**
- `beginner`: define each term the first time it appears (in 6 words or fewer), at most one analogy, no
  jargon in on-screen captions.
- `intermediate`: don't define the basics (array, HTTP, commit, thread); spend the beats on how it works
  and when to use it.
- `senior`: internals, edge cases and failure modes (what breaks under load, version differences); a
  number only with a source.

## 4. On-screen limits and safe zones

| Element | Limit |
|---|---|
| Beat heading | max 20 characters, UPPERCASE |
| Caption line | max 40 characters (asterisks for *emphasis* don't count) |
| Code / terminal line | max 32 characters; real code or a real command (a line from a real program is fine; no made-up APIs, no `...` placeholders) |
| Diagram labels | max 12 characters (guidance: the checker can't see labels) |
| Cheat-sheet snippet | max 6 lines of 60 characters, real working code |

**Safe zones** (approximate; use the platform's own safe-zone template when you have one): on all three
apps roughly the bottom 20% (caption, audio, profile) and the right 15% (like/comment/share buttons) are
covered, and the top 10% holds the account name. Put headings, captions and code in the middle of the
frame, and say so in the shot list when it matters.

Spell symbols out in narration ("O of n") and use normal notation on screen (`O(n)`). In captions, `*`
marks emphasis, so write multiplication as `×` or `·` (`O(n·k)`).

**By format**, the "On screen" column of the shot list describes:
- `animated`: what the diagram does (a node lights up, a pointer moves, a counter changes).
- `screen`: what is on the screen recording (which file, command, line to highlight, zoom).
- `talking`: the overlay or B-roll shown over the speaker (a text card, a code snippet, a simple
  sketch). The speaker still changes "one thing" per beat: a new overlay, a cut, or a gesture to it.

## 5. Category notes

**DSA.** Show the data structure or the algorithm's state (cells, pointers, buckets, stack slots, tree
nodes). Each beat is one step of a real worked example; counters (steps, comparisons, Big-O) must be
exactly what the example produces. Define your formula: `mid = (lo + hi) // 2` finds 25 in
`[3, 8, 12, 17, 21, 25]` in **3** comparisons (12, 21, 25); the upper middle `(lo + hi + 1) // 2` takes 2
(17, 25). Show whichever one you narrate. The cheat sheet compares approaches by time and space.

**System Design.** Show the system (clients, load balancer, services, cache, queue, database) and the
**problem and the fix on the same picture**. Numbers are illustrative but plausible and consistent,
and a number changes only in the beat whose action causes it. Commands are real (`kubectl get pods`).

**AI / ML.** Show the data flow (input -> tokenizer / embedding / retrieval -> model -> output). Be exact
about units: tokens vs characters vs words, context window vs output length, training vs inference.
Never claim accuracy or benchmark numbers you can't cite.

**Dev & tools.** Show before and after (the bug, then the fix; the slow way, then the tool). Every
command and flag must exist in the current version of the tool; if unsure, verify it or leave it out.

**OS.** Processes, threads, memory, cores or the scheduler as boxes with states (running, waiting,
blocked). Keep the example tiny (2 processes, 1 lock) and be exact about what the OS does vs the program.

**Interview & careers.** Show a process, not a server (candidate -> rounds -> offer, or the shape of a
good answer). **Never invent pass rates, salaries or hiring statistics**; advice is practice, not data.
No terminal lines; the "snippet" is a reusable template, labelled as such.

## 6. Fact-check

A model reviewing its own draft tends to approve it, so make the check explicit:

1. **List every claim** in the draft (narration, captions, code, cheat sheet, caption, hooks):
   commands, flags, APIs, complexities, units, numbers, "X does Y" statements.
2. **Verify each one** with the strongest method available, and write the method down:
   - run it (a command's `--help`, a quick execution of the snippet, re-computing the example);
   - official documentation or a web search, when tools allow;
   - your own knowledge only for stable facts. For releases, versions, pricing or anything that
     changes, treat your knowledge as possibly outdated and verify or mark it **unverified**.
3. **Fix or remove** anything wrong; move anything you couldn't verify to the "Unverified" section
   instead of keeping it as fact. If your environment can start a fresh session or sub-agent, have it
   review the draft without seeing your reasoning.

Common catches:
- A command that doesn't do what's claimed (`cat doc.pdf | wc -w` doesn't count words: PDFs are
  binary; use `pdftotext doc.pdf - | wc -w`).
- Units: tokens vs characters (text splitters often measure characters by default), ms vs s, average
  vs worst case.
- Complexity that depends on the language: reversing in place is O(1) extra space for a char array, but a
  Python `str` is immutable, so reversing it needs an O(n) copy.
- The picture contradicts the words (narration says "straight to the model", diagram routes via a cache).
- Absolutes that aren't literally true: always, never, every, zero, instant, 100%, infinite.
- Invented numbers: benchmarks, percentages, salaries, user counts.
- Comparisons that don't compare like with like (a row that is a subset of another row).

## 7. Platform notes

Platform rules change; these are current guidance, not guarantees. Check the app when in doubt.

- **Instagram Reels:** caption 60-150 words: a hook line (different from the video's), the value, a
  closing question. **5 hashtags**, specific to the topic (Instagram was widely reported to cap posts at
  5 from December 2025; if a post with 5 fails or the Help Center says otherwise, follow the app). Skip
  generic tags such as `#fyp`, `#viral`, `#reels`: they say nothing about a niche topic.
- **YouTube Shorts:** a **title** (max 100 characters; the topic first) instead of a long caption, plus a
  2-3 line description. Up to **3 hashtags**, which can include `#Shorts`.
- **TikTok:** a short caption (1-2 lines, a hook plus a question) and **3-5 hashtags**.

## 8. Output format

Hand over exactly this (the checker reads these headings):

~~~markdown
## <Title>
Category: <category> · Platform: <platform> · Format: <format> · Audience: <audience>

### Voice-over
1. <beat 1 narration>
2. <beat 2 narration>
...

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | <heading> | <caption> | <what is shown> | <code or empty> |

### Hook options
1. <hook> (recommended)
2. <hook>
3. <hook>

### Cheat sheet
- Use when: <3 short bullets>
- Trade-offs: <3 short bullets>
- Snippet:
```<language>
<real code, max 6 lines of 60>
```
- Comparison: <2-4 rows x 4 columns (usually 3), the topic itself last>

### Caption
<Instagram/TikTok caption, or for YouTube: "Title: ..." then the description>

<hashtags>

### Claims checked
- <claim>: <how verified>

### Unverified
- <claim you couldn't verify, or "none">

### Validation
<the checker's output, or "checked by hand" with the counts>

### Changes
<fix mode only: each change and why>
~~~

The voice-over block is plain text in reading order, ready for a teleprompter or a TTS tool.
Inside table cells, write a pipe as `\|` (`ps aux \| grep node`), or the table breaks when rendered.
See `examples.md` for two complete scripts.

## 9. Tips that make the difference

- **The example carries the video.** "Find 25 in six sorted numbers: 3 comparisons instead of 6"
  beats any abstract explanation.
- **Show the failure first.** A beat where the naive way visibly breaks makes the fix land.
- **Verbs as cues.** Put the verb that causes the change ("flip", "crash", "drop") in that beat's
  narration; editors and animation tools can cut on it.
- **Payoff states the mechanism.** "Halve each step. O(log n) time." beats "1000x faster!".
- **One CTA, at the end.** "Follow <handle> for more <topic area> explainers."
