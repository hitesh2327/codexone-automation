# Tech Reel Script Writer

**Version 1.2.0** · An agent skill in the SKILL.md format (a `name` and `description` header, plus
bundled files). Built for Claude Code; other agents that load SKILL.md skills should work too, but
haven't been tested yet (see "Tested" below).

Turns one technical topic (DSA, system design, AI/ML, dev tools, OS, tech interviews) into an
accurate 25-30 second script for Instagram Reels, YouTube Shorts or TikTok, then fact-checks it and
validates it with a bundled checker.

## What you get

- **A script that fits:** 5-8 beats, max 75 spoken words (about 27 s), one idea per beat, a worked example
  with real numbers, 3 hook options, a payoff and one CTA.
- **A voice-over block** ready for a teleprompter or a TTS tool, plus a **shot list** (heading, caption,
  what's on screen, code) for animated, screen-recording or talking-head videos.
- **Fact-checking you can see:** every claim listed with how it was verified, and anything unverified
  flagged instead of guessed.
- **`scripts/check.py`:** counts words and characters exactly and enforces every limit (beats, words,
  headings, captions, on-screen code, snippet size, comparison table, hooks, hashtags per platform,
  YouTube title). Python 3.7+, no dependencies.
- **Fix mode:** paste your own draft in any shape; you get it back in the format, checked, with a list
  of what changed and why.
- **Audience levels** (beginner, intermediate, senior) and **non-English narration** (a lower word cap
  for slower TTS voices, on-screen text measured the way it shows on screen).
- **Platform notes** for Instagram, YouTube Shorts and TikTok, and safe zones so text isn't hidden
  behind the app's buttons.
- **Batch mode:** plan and write a week of scripts without repeated topics or hooks.
- **Two complete examples** in `examples.md`.

## Install

Copy the `tech-reel-script-writer` folder into your agent's skills folder. For Claude Code that is
`~/.claude/skills/` (all projects) or `.claude/skills/` inside a project. For other agents, see their
documentation for where SKILL.md skills go.

## Use

Ask your agent, for example:

- "Write a reel script about consistent hashing."
- "Script a YouTube Short on Python generators, screen-recording format, intermediate audience."
- "Plan 7 DSA reels for next week."
- "This script runs 40 seconds. Fix it." (paste the script)

Scripts are saved to `reel-scripts/` in your project. To check one yourself (on Windows, use `py`
instead of `python3`):

```bash
python3 scripts/check.py reel-scripts/my-script.md
python3 scripts/check.py my-script.md --platform youtube
python3 scripts/check.py my-script.md --max-words 60 --wps 2.3   # slower or non-English TTS
```

FAIL lines must be fixed; WARN lines are for you to read (for example, an "always" that may not be
literally true). Exit code 0 means every script passed.

## Tested

What was run for 1.2.0, and what wasn't:

- **The checker:** 56 automated tests, all passing. They cover every limit, plus the inputs that broke
  1.1.0: shell pipes in table cells, Markdown variants (`~~~` fences, `1)` numbering, headings inside
  code, lines that wrap, unclosed code blocks), Windows consoles (cp1252), CRLF, UTF-8 with a BOM and
  UTF-16 files, and Hindi text.
- **Ten fresh agent sessions, each given only this skill folder and a one-line request** (Claude Code
  sub-agents that saw nothing else). Together they wrote 12 scripts:
  - all six categories, three platforms, three formats and three audience levels;
  - a Hinglish narration;
  - a fix-mode rewrite of a deliberately wrong draft (all five false Big-O claims in it were caught and
    corrected);
  - a batch of three.
  - **Results:** all 12 first drafts passed the checker, and so did all 12 final scripts. Every agent
    verified its facts by running code: real `pip` installs, C programs that count page faults, the
    source code of LLM libraries, and Java's `HashMap`.
  - **What the agents found unclear** was fixed in this version: the comparison-table shape, what goes
    in the Validation section before the first run, which hook needs the topic name, how `#Shorts`
    counts, and how to write numbers and the handle for a TTS voice. Their remaining checker warnings
    were false alarms on Hindi narration and on rates such as "one every 6 s"; both are fixed.
- **Ten more scripts written by the skill's author** across the same range: 7 of 10 first drafts
  passed. The three failures were over the word cap and one `*` used as multiplication in a caption,
  exactly what the checker is for. All 10 pass after one round of fixes. Their facts were checked by
  running them too (`git bisect` on all 64 positions in a 64-commit repository, real Docker builds).
- **Not tested yet:**
  - No agent other than Claude Code has been tried.
  - Windows behaviour is simulated in the tests, not run on a Windows machine.
  - A real TTS voice reading the scripts: lengths are estimates from the word count.

## Changelog

- **1.2.0**:
  - **Checker, correctness:**
    - commands with pipes are measured correctly (write `\|` inside table cells);
    - narration that wraps onto a second line is counted;
    - Hindi and other Indic captions are measured by what shows on screen.
  - **Checker, robustness:**
    - no crash on Windows consoles or on UTF-16, BOM and CRLF files;
    - accepts `~~~` fences, `1)` numbering, heading variants and indented code blocks;
    - `#1` isn't counted as a hashtag;
    - fewer false warnings: "zero-downtime" is no longer flagged, real `...` syntax (spread, git
      ranges) is allowed, and each warning says where it is.
  - **Checker, new checks and options:**
    - the comparison table is checked;
    - the recommended hook must be marked and used in beat 1;
    - `--wps` sets the speaking rate for the time estimate;
    - batch files get a summary, and non-script sections are skipped;
    - exit code 2 for an unreadable file or bad arguments.
  - **From the fresh-agent test:** no topic or CTA warning on Hindi narration; rates ("one every 6 s")
    and indexes ("pop zero") are not flagged as absolutes.
  - **SKILL.md:**
    - clearer rules found by the fresh-agent test: comparison table shape, the Validation section,
      which hook needs the topic name, `#Shorts`, numbers and the handle for TTS, the batch plan;
    - fix mode for existing drafts;
    - rules per audience level;
    - where to save scripts, and `python3`/`py`;
    - hedged platform rules (Instagram's 5-hashtag cap, approximate safe zones);
    - pipes in tables, `×` or `·` for multiplication in captions, and complexity that depends on the
      language.
- **1.1.0**:
  - bundled `scripts/check.py`;
  - a claims list and an "Unverified" section;
  - a voice-over block and a shot list;
  - platform input (Instagram, YouTube Shorts, TikTok) and format input (animated, screen, talking
    head);
  - safe zones, audience level and batch mode;
  - fixed the binary-search example to match the standard midpoint formula.
- **1.0.0**: first release.

## Licence

For use by the purchaser in their own content and projects. Please don't resell or redistribute the
skill itself. If you bought it on a marketplace, the marketplace's licence terms apply and take
precedence. See `LICENSE.txt`.

---

Want this fully automated (trending topic -> script -> animated diagram reel + carousel -> approval on
Telegram -> posted to Instagram and YouTube)? That's what **Mintly** by Anjanex Labs does:
<your Mintly link>
