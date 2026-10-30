# Tech Reel Script Writer

**Version 1.1.0** · A SKILL.md agent skill for Claude Code, Cursor, Copilot and other agents that
support the SKILL.md format.

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
  headings, captions, on-screen code, snippet size, hooks, hashtags per platform, YouTube title).
  Python 3.8+, no dependencies.
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
- "This script runs 40 seconds. Fix it."

To check a script yourself:

```bash
python scripts/check.py my-script.md
python scripts/check.py my-script.md --platform youtube --max-words 60
```

## Changelog

- **1.1.0**: bundled `scripts/check.py`; claims list and "Unverified" section; voice-over block + shot
  list; platform input (Instagram, YouTube Shorts, TikTok) and format input (animated, screen,
  talking head); safe zones; audience level; batch mode; fixed the binary-search example to match
  the standard midpoint formula.
- **1.0.0**: first release.

## Licence

For use by the purchaser in their own content and projects. Please don't resell or redistribute the
skill itself.

---

Want this fully automated (trending topic -> script -> animated diagram reel + carousel -> approval on
Telegram -> posted to Instagram and YouTube)? That's what **Mintly** by Anjanex Labs does:
<your Mintly link>
