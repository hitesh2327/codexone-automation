#!/usr/bin/env python3
"""Validate a script written with the tech-reel-script-writer skill.

Counts words and characters exactly (language models can't), so the limits in SKILL.md are guaranteed
instead of hoped for. Reads every "## <Title>" script in the file (one or many, e.g. a batch).

    python scripts/check.py script.md                     # platform read from the script header
    python scripts/check.py script.md --platform youtube  # override
    python scripts/check.py script.md --max-words 60      # slower or non-English TTS
    cat script.md | python scripts/check.py -

Exit code 0 when every script passes, 1 when any check FAILs. WARN lines are for a human to look at.
Standard library only (Python 3.8+).
"""
from __future__ import annotations

import argparse
import re
import sys

MAX_BEAT_WORDS = 16
BEATS = (5, 8)
HEADING_MAX, CAPTION_MAX, CODE_MAX = 20, 40, 32
SNIPPET_LINES, SNIPPET_WIDTH = 6, 60
HOOKS, HOOK_WORDS = 3, (5, 12)
HASHTAGS = {"instagram": (5, 5), "tiktok": (3, 5), "youtube": (0, 3)}   # (min, max), current guidance
YT_TITLE_MAX = 100
ABSOLUTES = re.compile(r"\b(always|never|every|everyone|zero|instant(?:ly)?|infinite|guaranteed?)\b|\b100\s?%",
                       re.IGNORECASE)
CTA = re.compile(r"\b(follow|subscribe|save|share|comment)\b", re.IGNORECASE)
STOP = {"the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "how", "why", "what", "your", "you",
        "with", "is", "are", "vs", "about"}


def words(text: str) -> list[str]:
    """Spoken words: whitespace-separated tokens that contain a letter or digit (dashes alone don't count)."""
    return [w for w in text.split() if re.search(r"[A-Za-z0-9ऀ-ॿ]", w)]


def sections(block: str) -> dict[str, str]:
    """### headings of one script -> their text."""
    out: dict[str, str] = {}
    parts = re.split(r"^### +(.+?)\s*$", block, flags=re.MULTILINE)
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].split("(")[0].strip().lower()] = parts[i + 1]
    return out


def numbered(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^\s*\d+\.\s+(.+)$", text, flags=re.MULTILINE)]


def table_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or re.match(r"^\|[\s:|-]+\|$", line):
            continue
        rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows[1:] if rows else []                         # drop the header row


def check_script(title: str, block: str, platform: str | None, max_words: int) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []
    sec = sections(block)
    header = re.search(r"Platform:\s*(\w+)", block)
    platform = (platform or (header.group(1) if header else "instagram")).lower()
    if platform not in HASHTAGS:
        fails.append(f"unknown platform {platform!r} (instagram, youtube, tiktok)")
        platform = "instagram"

    for name in ("voice-over", "shot list", "hook options", "cheat sheet", "caption", "claims checked", "unverified"):
        if name not in sec:
            fails.append(f"missing section '### {name.title()}'")

    # Voice-over: beats and words
    beats = numbered(sec.get("voice-over", ""))
    total = sum(len(words(b)) for b in beats)
    if not BEATS[0] <= len(beats) <= BEATS[1]:
        fails.append(f"{len(beats)} beats (need {BEATS[0]}-{BEATS[1]})")
    for i, b in enumerate(beats, 1):
        if len(words(b)) > MAX_BEAT_WORDS:
            fails.append(f"beat {i}: {len(words(b))} words (max {MAX_BEAT_WORDS})")
    if total > max_words:
        fails.append(f"narration is {total} words (max {max_words}, about 27 s)")
    if beats:
        first6 = [w.lower().strip(".,:;!?\"'()") for w in beats[0].split()[:6]]
        topic = [w.lower() for w in re.findall(r"[A-Za-z0-9+#]+", title) if w.lower() not in STOP and len(w) > 2]
        if topic and not any(t in first6 for t in topic):
            warns.append("beat 1: the topic name isn't in the first 6 words")
        if not CTA.search(beats[-1]):
            warns.append("last beat has no CTA (follow / subscribe / save)")
        for i, b in enumerate(beats[:-1], 1):
            if re.search(r"\bfollow\b|\bsubscribe\b", b, re.IGNORECASE):
                warns.append(f"beat {i}: CTA before the last beat")

    # Shot list: on-screen limits
    rows = table_rows(sec.get("shot list", ""))
    if beats and len(rows) != len(beats):
        fails.append(f"shot list has {len(rows)} rows for {len(beats)} beats")
    for r in rows:
        if len(r) < 5:
            fails.append(f"shot list row {r[0] if r else '?'}: needs 5 columns (#, Heading, Caption, On screen, Code)")
            continue
        n, heading, caption, _, code = r[:5]
        code = code.strip().strip("`").strip()
        if len(heading) > HEADING_MAX:
            fails.append(f"beat {n} heading is {len(heading)} chars (max {HEADING_MAX}): {heading!r}")
        if heading != heading.upper():
            warns.append(f"beat {n} heading isn't UPPERCASE")
        plain = caption.replace("*", "")
        if len(plain) > CAPTION_MAX:
            fails.append(f"beat {n} caption is {len(plain)} chars (max {CAPTION_MAX}): {plain!r}")
        if caption.count("*") % 2:
            fails.append(f"beat {n} caption has an unpaired *")
        if len(code) > CODE_MAX:
            fails.append(f"beat {n} code is {len(code)} chars (max {CODE_MAX}): {code!r}")
        if "..." in code or "…" in code:
            fails.append(f"beat {n} code has a '...' placeholder; on-screen code must be real")

    # Hooks
    hooks = [re.sub(r"\(recommended\)", "", h, flags=re.IGNORECASE).strip() for h in numbered(sec.get("hook options", ""))]
    if len(hooks) != HOOKS:
        fails.append(f"{len(hooks)} hook options (need {HOOKS})")
    for i, h in enumerate(hooks, 1):
        if not HOOK_WORDS[0] <= len(words(h)) <= HOOK_WORDS[1]:
            fails.append(f"hook {i}: {len(words(h))} words (need {HOOK_WORDS[0]}-{HOOK_WORDS[1]})")

    # Cheat-sheet snippet
    snippet = re.search(r"```[^\n]*\n(.*?)```", sec.get("cheat sheet", ""), flags=re.DOTALL)
    if not snippet:
        fails.append("cheat sheet has no ``` snippet block")
    else:
        lines = snippet.group(1).rstrip("\n").splitlines()
        if len(lines) > SNIPPET_LINES:
            fails.append(f"snippet has {len(lines)} lines (max {SNIPPET_LINES})")
        for j, line in enumerate(lines, 1):
            if len(line) > SNIPPET_WIDTH:
                fails.append(f"snippet line {j} is {len(line)} chars (max {SNIPPET_WIDTH})")

    # Caption and hashtags, per platform
    cap = sec.get("caption", "")
    tags = re.findall(r"(?<![\w&])#[A-Za-z0-9_]+", cap)
    lo, hi = HASHTAGS[platform]
    if not lo <= len(tags) <= hi:
        need = f"exactly {lo}" if lo == hi else f"{lo}-{hi}"
        fails.append(f"{len(tags)} hashtags for {platform} (need {need})")
    if platform == "youtube":
        title_line = re.search(r"^Title:\s*(.+)$", cap, flags=re.MULTILINE)
        if not title_line:
            fails.append("youtube: the caption needs a 'Title: ...' line")
        elif len(title_line.group(1).strip()) > YT_TITLE_MAX:
            fails.append(f"youtube title is {len(title_line.group(1).strip())} chars (max {YT_TITLE_MAX})")
    elif platform == "instagram":
        body = re.sub(r"(?<![\w&])#[A-Za-z0-9_]+", "", cap)
        n = len(words(body))
        if not 60 <= n <= 150:
            warns.append(f"instagram caption is {n} words (aim for 60-150)")

    # Claims and absolutes
    if "claims checked" in sec and not numbered(sec["claims checked"]) and not re.search(r"^\s*-\s+\S", sec["claims checked"], re.MULTILINE):
        warns.append("'Claims checked' is empty: list each claim and how it was verified")
    spoken = " ".join(beats + [r[2] for r in rows if len(r) > 2] + hooks)
    for m in sorted({m.group(0).lower() for m in ABSOLUTES.finditer(spoken)}):
        warns.append(f"absolute word {m!r}: make sure it is literally true")
    return fails, warns


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", help="the script file (markdown), or - for stdin")
    ap.add_argument("--platform", choices=sorted(HASHTAGS), help="default: the script header's Platform")
    ap.add_argument("--max-words", type=int, default=75, help="spoken words allowed (default 75; 60 for slower TTS)")
    args = ap.parse_args(argv)
    text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
    scripts = re.split(r"^## +(.+?)\s*$", text, flags=re.MULTILINE)
    if len(scripts) < 3:
        print("FAIL: no '## <Title>' script found")
        return 1
    failed = False
    for i in range(1, len(scripts) - 1, 2):
        title, block = scripts[i], scripts[i + 1]
        fails, warns = check_script(title, block, args.platform, args.max_words)
        beats = numbered(sections(block).get("voice-over", ""))
        n = sum(len(words(b)) for b in beats)
        print(f"{'FAIL' if fails else 'PASS'}: {title} ({len(beats)} beats, {n} words, ~{n / 2.7:.0f} s)")
        for f in fails:
            print(f"  FAIL  {f}")
        for w in warns:
            print(f"  WARN  {w}")
        failed |= bool(fails)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
