---
name: tech-reel-script-writer
description: Write accurate 25-30 second vertical-video scripts (Instagram Reels, YouTube Shorts, TikTok) that explain one programming, DSA, system design, AI/ML, OS or tech-interview topic, fact-check every claim, and validate length and on-screen limits with a bundled checker. Use when asked to script a reel/short/TikTok/explainer about a technical topic, plan a week of such scripts, or fix one that is too long, vague or inaccurate. Not for long-form YouTube videos, blog posts, or non-technical topics.
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
| Topic | anything technical | **required** |
| Platform | `instagram`, `youtube`, `tiktok` | `instagram` |
| Format | `animated` (diagram / motion graphics), `screen` (screen recording), `talking` (talking head + overlays) | `animated` |
| Audience | `beginner`, `intermediate`, `senior` | `beginner` |
| Voice | own voice / TTS / non-English narration | own voice |
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
6. **Validate**: save the script to a file and run `python <this skill's folder>/scripts/check.py <file>`
   (add `--max-words 60` for TTS in a non-English language). Fix every FAIL and re-run until it passes.
   If you can't run code, do the same checks by hand, beat by beat, counting words one at a time.
7. **Hand over** the final script and the checker's result.

**Batch mode:** plan all topics first as a numbered list (title + one-line mechanism), make sure no two
share a mechanism, example or hook pattern, then write and validate each script separately.

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
counter-intuitive true fact, a common mistake), and mark the strongest. Beat 1 uses it.

## 4. On-screen limits and safe zones

| Element | Limit |
|---|---|
| Beat heading | max 20 characters, UPPERCASE |
| Caption line | max 40 characters (asterisks for *emphasis* don't count) |
| Code / terminal line | max 32 characters, real and runnable (no `...` placeholders) |
| Diagram labels | max 12 characters |
| Cheat-sheet snippet | max 6 lines of 60 characters, real working code |

**Safe zones:** on all three apps the bottom ~20% (caption, audio, profile) and the right ~15%
(like/comment/share buttons) are covered, and the top ~10% holds the account name. Put headings,
captions and code in the middle 70% of the frame, and say so in the shot list when it matters.

Spell symbols out in narration ("O of n") and use normal notation on screen (`O(n)`).

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
- The picture contradicts the words (narration says "straight to the model", diagram routes via a cache).
- Absolutes that aren't literally true: always, never, every, zero, instant, 100%, infinite.
- Invented numbers: benchmarks, percentages, salaries, user counts.
- Comparisons that don't compare like with like (a row that is a subset of another row).

## 7. Platform notes

Platform rules change; these are current guidance, not guarantees. Check the app when in doubt.

- **Instagram Reels:** caption 60-150 words: a hook line (different from the video's), the value, a
  closing question. **5 hashtags** (the current cap), specific to the topic; skip generic ones such as
  `#fyp`, `#viral`, `#reels`, which do nothing for a niche account.
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
- Comparison: <3-4 rows x 4 columns, the topic itself last>

### Caption
<Instagram/TikTok caption, or for YouTube: "Title: ..." then the description>

<hashtags>

### Claims checked
- <claim>: <how verified>

### Unverified
- <claim you couldn't verify, or "none">

### Validation
<the checker's output, or "checked by hand" with the counts>
~~~

The voice-over block is plain text in reading order, ready for a teleprompter or a TTS tool.
See `examples.md` for two complete scripts.

## 9. Tips that make the difference

- **The example carries the video.** "Find 25 in six sorted numbers: 3 comparisons instead of 6"
  beats any abstract explanation.
- **Show the failure first.** A beat where the naive way visibly breaks makes the fix land.
- **Verbs as cues.** Put the verb that causes the change ("flip", "crash", "drop") in that beat's
  narration; editors and animation tools can cut on it.
- **Payoff states the mechanism.** "Halve each step. O(log n) time." beats "1000x faster!".
- **One CTA, at the end.** "Follow <handle> for more <topic area> explainers."
