---
name: tech-reel-script-writer
description: Write accurate 25-30 second short-video scripts (Instagram Reels, YouTube Shorts, TikTok) that explain one programming, DSA, system design, AI or tech-interview topic, then fact-check them before you record. Use when asked to script a reel/short/explainer about a technical topic, or to fix one that is too long, vague or inaccurate.
---

# Tech Reel Script Writer

Turns one technical topic into a tight, beginner-friendly 25-30 second video script that a developer
audience will trust: a hook, one idea per beat, a worked example with real numbers, a payoff and a
call to action. Every script goes through an accuracy review and a length check before it is handed
over, because one wrong command or invented statistic in the comments costs more reach than a weak hook.

Works for a voice-over you record yourself or a text-to-speech voice, and for any editing style
(talking head, screen recording, animated diagram).

## When to use

- "Write a reel / short / 30-second explainer about <topic>"
- "Turn this blog post / concept into a short video script"
- "This script is too long / too vague / wrong - fix it"

Ask the user only for what you can't infer: the topic (required), the audience level (default:
students and junior developers), the account handle for the CTA, and the voice (their own voice
or a TTS voice). Don't ask about format or length: the rules below decide them.

## The workflow

Follow these steps in order. Don't skip the review (step 5) even when the draft looks right.

1. **Pick the category** and read its notes below: DSA, System Design, AI/ML, Dev & tools, OS,
   Interview & careers. A topic that fits two categories takes the one whose diagram tells the story.
2. **Find the one mechanism.** A 30-second video explains *one* thing: how it works, or why it beats
   the naive way. Write it as one sentence before writing anything else. If you need "and" twice,
   the topic is too big: narrow it (e.g. "Load balancing" -> "Why round-robin breaks with sticky sessions").
3. **Choose a concrete example** with small real inputs (an array of 6 numbers, 3 servers, one
   request). Work it out yourself first: every number you put on screen must be exactly what that
   example produces.
4. **Draft the beats** (structure and limits below).
5. **Review** with the accuracy checklist, then the length and on-screen checks. Fix and re-check
   until everything passes. Report what you fixed.
6. **Hand over** in the output format at the end.

## Structure: 5-8 beats, max 75 spoken words

A beat is one moment on screen: one change, one caption, 1-2 short spoken sentences (max 16 words).

| Beat | Job | Rule |
|---|---|---|
| 1. Hook | Stop the scroll | A curiosity question or a surprising true fact **plus the topic name**, said in the first 2 seconds. No greetings, no "in this video". Something must already be moving on screen. |
| 2. The problem / naive way | Create tension | Show what goes wrong without the idea, with the example's real numbers. |
| 3-6. The mechanism | One change per beat | Each beat shows exactly one step. Two changes = two beats (e.g. "Found a bug?" then "Flip back."). |
| Last. Payoff + CTA | Land it | State the benefit as the mechanism, not a made-up number, then the follow CTA. |

**Length:** total narration **max 75 words** (about 27 s at a normal speaking rate of ~2.7 words per
second; most TTS voices land within 25-30 s). For a slower voice or a non-English narration, use 60.
Count the words; don't estimate.

**Hook alternatives:** always write 3 alternative hooks (5-12 words each) with different angles:
a question, a counter-intuitive fact, a mistake the viewer is probably making. Mark the strongest.

## On-screen text limits

Phone screens are small and viewers read while listening. Keep on-screen text far shorter than the narration:

| Element | Limit |
|---|---|
| Beat heading | max 20 characters, UPPERCASE (e.g. `FLIP THE SWITCH`) |
| Caption line | max 40 characters; wrap 1-3 key words in `*asterisks*` for emphasis |
| Terminal / code line on screen | max 32 characters; must be real and runnable |
| Labels in a diagram | max 12 characters |
| Cheat-sheet snippet | max 6 lines of 60 characters, real working code |

Spell symbols out in narration ("O of n", "O of log n") and use normal notation on screen (`O(n)`).

## Category notes

### DSA
- Show the data structure or the algorithm's state: array cells, pointers, hash buckets, stack slots,
  tree or graph nodes.
- Each beat is one step of a **real worked example** with small inputs. Show counters such as steps,
  comparisons, time and space complexity, and make them exactly what the example produces.
- On-screen code is a real line or trace (`mid = (lo + hi) // 2`). The cheat sheet compares
  alternative approaches by time and space complexity.

### System Design
- Show the system: clients, load balancer, services, cache, queue, database. Show **the problem and the
  fix on the same picture** (a node fails, then traffic is rerouted; a cache starts answering; a
  queue absorbs a spike).
- Numbers (latency, load, hit rate) are illustrative but must be plausible and consistent with each
  other, and a number changes only in the beat whose action causes it (latency drops when cache hits
  *start*, not while the cache is being filled).
- Commands are real (`redis-cli GET user:42`, `kubectl get pods`).

### AI / ML
- Show the data flow: input -> tokenizer / embedding / retrieval -> model -> output.
- Be precise about units: tokens vs characters vs words, context window vs output length,
  training vs inference. Name the default behaviour of a library correctly.
- Never claim accuracy, recall or benchmark numbers you can't cite. Prefer "fewer irrelevant chunks"
  to "95% accuracy".

### Dev & tools
- Show the before and after of a workflow (the bug, then the fix; the slow way, then the tool).
- Every command and flag must exist in the current version of the tool. If you are not sure a flag
  exists, leave it out.

### OS
- Show processes, threads, memory, CPU cores or the scheduler as boxes with states (running,
  waiting, blocked).
- Keep the example tiny (2 processes, 1 lock) and be exact about what the OS does vs what the program does.

### Interview & careers
- Show a process, not a server: candidate -> recruiter -> rounds -> offer, or the structure of a good
  answer (question -> clarify -> approach -> trade-offs -> result).
- **Never invent pass rates, salaries or hiring statistics.** Advice is phrased as practice, not as data.
- No terminal lines. The "snippet" is a reusable template (an answer outline), labelled as such.

## Accuracy review (step 5)

Read the draft as a strict senior engineer would read it in the comments. Fix every hit:

- [ ] **Every command, flag and API exists and does what the script says.** (Example of a real
      catch: `cat doc.pdf | wc -w` "counts words in a PDF". It doesn't, because PDFs are binary.
      Use `pdftotext doc.pdf - | wc -w`, or drop the line.)
- [ ] **Units are right**: tokens vs characters (a text splitter's `chunk_size` is often characters by
      default), ms vs s, bits vs bytes, average vs worst case.
- [ ] **The picture matches the words**: if the narration says data goes straight to the model, the
      diagram doesn't route it through a cache.
- [ ] **No absolutes that aren't literally true**: "always", "never", "zero", "instant", "100%",
      "infinite". Long-context models *can* read big documents; chunking is about cost, latency and
      precision. Say that.
- [ ] **No invented numbers**: benchmarks, percentages, salaries, user counts. Illustrative numbers in a
      worked example are fine when they follow from the example.
- [ ] **Comparisons compare like with like**: a table row isn't a subset of another row (e.g.
      "Chunking" vs "Fixed-size": fixed-size *is* a chunking strategy; compare Full document vs
      Fixed-size vs Semantic chunking).
- [ ] **The code snippet runs** as written (imports, signatures, language version).

Then the mechanical checks:

- [ ] 5-8 beats; total narration <= 75 words (count them); each beat <= 16 words
- [ ] Beat 1 names the topic and starts with motion, not a greeting
- [ ] Each beat changes exactly one thing on screen
- [ ] Every on-screen element within the limits table
- [ ] The CTA is in the last beat only

## Caption and hashtags

- **Caption:** 60-150 words. First line is a hook (different from the video's), the middle gives the
  value in plain words, and it ends with a question that invites a comment. No hashtags in the caption body.
- **Hashtags: exactly 5** (Instagram's limit since December 2025), specific to the topic
  (`#binarysearch`, `#systemdesign`, `#redis`). No generic tags that add no reach: `#fyp`, `#viral`,
  `#reels`, `#explore`, `#trending`, `#instagood`, `#foryou`.

## Output format

Hand over exactly this, in Markdown:

~~~markdown
## <Title> - <one-line mechanism>
Category: <category> · Spoken words: <n> (~<seconds> s) · Beats: <n>

### Hook options
1. <hook>  <- recommended
2. <hook>
3. <hook>

### Script
| # | Heading (on screen) | Narration (spoken) | Caption (on screen) | Visual change | Code / terminal |
|---|---|---|---|---|---|
| 1 | ... | ... | ... | ... | ... |

### Cheat sheet (for a carousel or the pinned comment)
- Use when: 3 bullets, max 6 words each
- Trade-offs: 3 bullets, max 6 words each
- Snippet (<= 6 x 60): ```<real code>```
- Comparison: 3-4 rows x 4 columns, the topic itself last

### Caption
<caption>

<5 hashtags>

### Review
- Fixed: <each accuracy or length issue found and how it was fixed, or "none">
- Checks: words <n>/75 ✓, beats ✓, on-screen limits ✓, CTA ✓
~~~

See `examples.md` for two complete scripts (a DSA topic and an interview topic) in this format.

## Tips that make the difference

- **The example carries the video.** "Find 25 in [3, 8, 12, 17, 21, 25]: 2 compares instead of 6" beats
  any abstract explanation.
- **Show the failure first.** A beat where the naive approach visibly breaks makes the fix land.
- **Verbs as cues.** Put the verb that causes the change ("flip", "crash", "cache", "drop") in the
  narration of that beat; editors and animation tools can cut on it.
- **Payoff states the mechanism.** "Halve each step. O(log n) time." beats "1000x faster!".
- **One CTA, at the end.** "Follow <handle> for more <topic area> explainers."

---

Want this fully automated (trending topic -> script -> animated diagram reel + carousel -> approval
on Telegram -> posted to Instagram and YouTube)? That is what **Mintly** by Anjanex Labs does:
<your Mintly link>.
