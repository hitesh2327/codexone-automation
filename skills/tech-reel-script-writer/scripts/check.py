#!/usr/bin/env python3
"""Validate a script written with the tech-reel-script-writer skill.

Counts words and characters exactly (language models can't), so the limits in SKILL.md are guaranteed
instead of hoped for. Reads every "## <Title>" script in the file (one, or a whole batch).

    python3 scripts/check.py script.md                      # platform read from the script header
    python3 scripts/check.py script.md --platform youtube   # override it
    python3 scripts/check.py script.md --max-words 60 --wps 2.3   # slower or non-English TTS
    python3 scripts/check.py - < script.md                  # read from stdin

On Windows, use `py` instead of `python3`, and pass the file name instead of piping the file in.
Exit code: 0 every script passes, 1 a check FAILed, 2 bad arguments or the file couldn't be read.
WARN lines are for a human to look at. Standard library only (Python 3.7+).
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata

MAX_BEAT_WORDS = 16
BEATS = (5, 8)
HEADING_MAX, CAPTION_MAX, CODE_MAX = 20, 40, 32
SNIPPET_LINES, SNIPPET_WIDTH = 6, 60
COMPARISON_COLUMNS, COMPARISON_ROWS = 4, (2, 4)
HOOKS, HOOK_WORDS = 3, (5, 12)
HASHTAGS = {"instagram": (5, 5), "tiktok": (3, 5), "youtube": (0, 3)}   # (min, max): current guidance
YT_TITLE_MAX = 100
IG_CAPTION_WORDS = (60, 150)

# A word counts if it has a letter or digit in any script (so dashes and bullets don't).
WORD = re.compile(r"[^\W_]", re.UNICODE)
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([\w+-]*)")
NUMBERED = re.compile(r"^\s*\d+\s*[.):]\s+(.+?)\s*$")
BULLET = re.compile(r"^\s*[-*•]\s+(\S.*?)\s*$")
STRUCTURE = re.compile(r"^\s*([|#>]|`{3}|~{3})")   # lines that never continue a list item
# "(recommended)" or "<- recommended" after a hook, or "(recommended)" / "Recommended:" before it.
RECOMMENDED = re.compile(r"^[\s*_]*(?:\(\s*recommended\s*\)|recommended\s*:)[\s*_]*"
                         r"|[\s*_]*(?:\(\s*recommended\s*\)|(?:<-|←|—|–)\s*recommended)[\s*_]*$", re.IGNORECASE)
# A hashtag needs a letter (#100DaysOfCode yes, "#1 tip" no) and isn't part of C#, &#123; or a URL.
HASHTAG = re.compile(r"(?<![\w&#/])#(?=[0-9_]*[^\W\d_])\w+")
# "..." is a placeholder unless it is glued to a name: JS spread (...args) and git ranges (main...dev) are real.
PLACEHOLDER = re.compile(r"…|(?<![\w.])\.{3}(?![\w.])")
# Not absolutes: a rate ("one every 12 seconds") or an index ("pop zero", "index zero").
TIME = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|few|other)?\s*" \
       r"(?:s|ms|milliseconds?|seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b"
ABSOLUTES = re.compile(r"(?<![\w-])(always|never|every(?!\s+" + TIME + r")|everyone|everything"
                       r"|(?<!index )(?<!pop )(?<!insert )(?<!position )(?<!at )zero"
                       r"|instant(?:ly)?|infinite(?:ly)?|guaranteed?)(?![\w-])|(?<![\d.])100\s?%", re.IGNORECASE)
# English, plus the Hindi spellings TTS scripts use (Devanagari has no \b word boundaries).
CTA = re.compile(r"\b(follow|subscribe|save|share|comment)\b|\u092b\u093c?\u0949\u0932\u094b|सब्सक्राइब|सेव|शेयर",
                 re.IGNORECASE)
STOP = {"the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "how", "why", "what", "your", "you",
        "with", "is", "are", "vs", "about", "into", "from", "by", "at", "it"}
PROSE = {"", "text", "txt", "plain", "plaintext", "md", "markdown"}   # snippet languages that aren't code
SECTIONS = {   # normalised heading -> canonical key
    "voiceover": "voiceover", "narration": "voiceover",
    "shotlist": "shotlist", "shots": "shotlist",
    "hookoptions": "hooks", "hooks": "hooks",
    "cheatsheet": "cheatsheet", "snippet": "cheatsheet", "comparison": "cheatsheet",
    "caption": "caption", "captionandhashtags": "caption",
    "claimschecked": "claims", "claims": "claims", "factcheck": "claims",
    "unverified": "unverified",
}
REQUIRED = {"voiceover": "Voice-over", "shotlist": "Shot list", "hooks": "Hook options",
            "cheatsheet": "Cheat sheet", "caption": "Caption", "claims": "Claims checked",
            "unverified": "Unverified"}


def words(text: str) -> list:
    return [w for w in text.split() if WORD.search(w)]


def tokens(text: str) -> list:
    """Lower-case words for matching; vowel signs stay attached (Hindi and other Indic scripts)."""
    out, cur = [], []
    for ch in text.lower() + " ":
        if unicodedata.category(ch)[0] in "LMN":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    return out


def visible_len(text: str) -> int:
    """Characters as they take space on screen: combining marks (Hindi vowel signs and the like) and
    invisible format characters don't count; *emphasis* asterisks don't either."""
    return sum(1 for ch in text.replace("*", "") if unicodedata.category(ch) not in ("Mn", "Me", "Cf"))


def section_key(heading: str) -> str:
    key = re.sub(r"[^a-z]", "", heading.split("(")[0].lower())
    if key in SECTIONS:
        return SECTIONS[key]
    for k in sorted(SECTIONS, key=len, reverse=True):   # "Voice-over script" -> voiceover
        if key.startswith(k):
            return SECTIONS[k]
    return key


def closes(line: str, fence: str) -> bool:
    s = line.strip()
    return len(s) >= len(fence) and set(s) == {fence[0]}


def parse(text: str) -> list:
    """The '## ' blocks in a file: [{title, head, sections: {key: [lines]}}]. Headings inside ``` or ~~~
    code blocks are content, not structure."""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    blocks, cur, sec, fence = [], None, None, None
    for line in text.split("\n"):
        if fence:
            if closes(line, fence):
                fence = None
        elif FENCE.match(line):
            fence = FENCE.match(line).group(2)
        elif re.match(r"^##[ \t]+\S", line):
            cur = {"title": line[2:].strip(), "head": [], "sections": {}}
            blocks.append(cur)
            sec = None
            continue
        elif re.match(r"^###[ \t]+\S", line) and cur is not None:
            sec = section_key(line[3:].strip())
            cur["sections"].setdefault(sec, [])
            continue
        if cur is not None:
            (cur["sections"][sec] if sec else cur["head"]).append(line)
    if fence and cur is not None:
        cur["unclosed"] = True
    return blocks


def numbered(lines: list) -> list:
    """Numbered items. A line that wraps onto the next line still belongs to its item."""
    out, can_continue, gap = [], False, False
    for line in lines:
        m = NUMBERED.match(line)
        if m:
            out.append(m.group(1))
            can_continue, gap = True, False
        elif not line.strip():
            gap = True
        elif can_continue and (not gap or line[:1].isspace()) and not BULLET.match(line) \
                and not STRUCTURE.match(line):
            out[-1] += " " + line.strip()
            gap = False
        else:
            can_continue = False
    return out


def items(lines: list) -> list:
    return [m.group(1) for line in lines for m in [NUMBERED.match(line) or BULLET.match(line)] if m]


def split_cells(line: str) -> tuple:
    """Markdown table cells. A pipe splits cells unless it is escaped (\\|) or inside `backticks`.
    Returns (cells, unescaped pipes found inside backticks)."""
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    cells, buf, tick, raw_pipes, i = [], [], False, 0, 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and s[i + 1:i + 2] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "`":
            tick = not tick
        if ch == "|" and not tick:
            cells.append("".join(buf).strip())
            buf = []
        else:
            raw_pipes += ch == "|"
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells, raw_pipes


def table(lines: list) -> tuple:
    """The first table outside code blocks: its rows (header dropped) and how many unescaped pipes
    were inside backticks."""
    rows, raw, fence = [], 0, None
    for line in lines:
        s = line.strip()
        if fence:
            fence = None if closes(line, fence) else fence
            continue
        if FENCE.match(line):
            fence = FENCE.match(line).group(2)
            continue
        if not s.startswith("|"):
            if rows:
                break
            continue
        if re.match(r"^\|[\s:|-]+\|?$", s) and "-" in s:
            continue
        cells, n = split_cells(s)
        rows.append(cells)
        raw += n
    return rows[1:], raw


def snippet(lines: list) -> tuple:
    """(lines of the first fenced code block, its language); (None, "") if there is none. The opening
    fence's indentation is removed from each line, as Markdown does."""
    out, fence, indent, lang = None, None, 0, ""
    for line in lines:
        if fence is None:
            m = FENCE.match(line)
            if m:
                indent, fence, lang, out = len(m.group(1)), m.group(2), m.group(3).lower(), []
        elif closes(line, fence):
            break
        else:
            out.append(line[min(indent, len(line) - len(line.lstrip())):])
    return out, lang


def check_script(script: dict, platform, max_words: int) -> tuple:
    fails, warns = [], []
    sec = script["sections"]
    header = re.search(r"Platform:\s*(\w+)", "\n".join(script["head"]))
    platform = (platform or (header.group(1) if header else "instagram")).lower()
    if platform not in HASHTAGS:
        fails.append(f"unknown platform {platform!r} (instagram, youtube, tiktok)")
        platform = "instagram"
    if script.get("unclosed"):
        fails.append("a ``` or ~~~ code block is never closed, so everything after it is read as code")
    for key, name in REQUIRED.items():
        if key not in sec:
            fails.append(f"missing section '### {name}'")

    # Voice-over
    beats = numbered(sec.get("voiceover", []))
    total = sum(len(words(b)) for b in beats)
    if "voiceover" in sec and not beats:
        fails.append("no beats under '### Voice-over': write one numbered line per beat (1. ..., 2. ...)")
    elif beats and not BEATS[0] <= len(beats) <= BEATS[1]:
        fails.append(f"{len(beats)} beats (need {BEATS[0]}-{BEATS[1]})")
    for i, b in enumerate(beats, 1):
        if len(words(b)) > MAX_BEAT_WORDS:
            fails.append(f"beat {i}: {len(words(b))} words (max {MAX_BEAT_WORDS})")
    if total > max_words:
        fails.append(f"narration is {total} words (max {max_words})")
    if beats:
        topic = [t for t in tokens(script["title"]) if t not in STOP and len(t) > 2]
        opening = " ".join(beats[0].split()[:6])
        letters = [ch for ch in opening if ch.isalpha()]   # a mostly Devanagari opening can't match an English title
        latin = sum(ch.isascii() for ch in letters) * 2 > len(letters)
        if topic and latin and not set(topic) & set(tokens(opening)):
            warns.append("beat 1: the topic name isn't in the first 6 words")
        if not CTA.search(beats[-1]):
            warns.append("last beat has no CTA (follow / subscribe / save)")
        for i, b in enumerate(beats[:-1], 1):
            if re.search(r"\b(follow|subscribe)\b", b, re.IGNORECASE):
                warns.append(f"beat {i}: CTA before the last beat")

    # Shot list: on-screen limits
    rows, raw_pipes = table(sec.get("shotlist", []))
    if beats and len(rows) != len(beats):
        fails.append(f"shot list has {len(rows)} rows for {len(beats)} beats")
    for r in rows:
        if len(r) != 5:
            fails.append(f"shot list row {r[0] if r else '?'} has {len(r)} columns (need 5: #, Heading, Caption, "
                         "On screen, Code); write a | inside a cell as \\|")
            continue
        n, heading, caption, _, code = r
        code = code.strip().strip("`").strip()
        if visible_len(heading) > HEADING_MAX:
            fails.append(f"beat {n} heading is {visible_len(heading)} chars (max {HEADING_MAX}): {heading!r}")
        if heading != heading.upper():
            warns.append(f"beat {n} heading isn't UPPERCASE")
        if visible_len(caption) > CAPTION_MAX:
            fails.append(f"beat {n} caption is {visible_len(caption)} chars (max {CAPTION_MAX}): {caption!r}")
        if caption.count("*") % 2:
            fails.append(f"beat {n} caption has an unpaired * (* marks emphasis; write multiplication as × or ·)")
        if len(code) > CODE_MAX:
            fails.append(f"beat {n} code is {len(code)} chars (max {CODE_MAX}): {code!r}")
        if PLACEHOLDER.search(code):
            fails.append(f"beat {n} code has a '...' placeholder; on-screen code must be real "
                         "(spread ...args and git a...b are fine)")

    # Hooks: exactly 3, the recommended one marked and used in beat 1
    hooks, best = [], None
    for i, h in enumerate(numbered(sec.get("hooks", []))):
        h, marked = RECOMMENDED.subn("", h)
        hooks.append(h.strip())
        best = i if marked and best is None else best
    if "hooks" in sec and len(hooks) != HOOKS:
        fails.append(f"{len(hooks)} hook options (need {HOOKS})")
    for i, h in enumerate(hooks, 1):
        if not HOOK_WORDS[0] <= len(words(h)) <= HOOK_WORDS[1]:
            fails.append(f"hook {i}: {len(words(h))} words (need {HOOK_WORDS[0]}-{HOOK_WORDS[1]})")
    if hooks and best is None:
        warns.append("no hook is marked (recommended): mark the strongest one, and use it in beat 1")
    elif hooks and beats:
        want = {t for t in tokens(hooks[best]) if t not in STOP and len(t) > 2}
        if want and 2 * len(want & set(tokens(beats[0]))) < len(want):
            warns.append(f"beat 1 doesn't use the recommended hook (hook {best + 1})")

    # Cheat sheet: snippet and comparison table
    if "cheatsheet" in sec:
        code, lang = snippet(sec["cheatsheet"])
        if code is None:
            fails.append("cheat sheet has no code block (``` or ~~~)")
        else:
            while code and not code[-1].strip():
                code.pop()
            if len(code) > SNIPPET_LINES:
                fails.append(f"snippet has {len(code)} lines (max {SNIPPET_LINES})")
            for j, line in enumerate(code, 1):
                if len(line) > SNIPPET_WIDTH:
                    fails.append(f"snippet line {j} is {len(line)} chars (max {SNIPPET_WIDTH})")
            if lang not in PROSE and any(PLACEHOLDER.search(line) for line in code):
                warns.append("snippet has a '...' placeholder: the snippet must be real, working code")
        comparison, raw = table(sec["cheatsheet"])
        raw_pipes += raw
        lo, hi = COMPARISON_ROWS
        if not comparison:
            fails.append("cheat sheet has no comparison table")
        elif not lo <= len(comparison) <= hi:
            fails.append(f"comparison table has {len(comparison)} rows (need {lo}-{hi})")
        for r in comparison:
            if len(r) != COMPARISON_COLUMNS:
                fails.append(f"comparison row {r[0]!r} has {len(r)} columns (need {COMPARISON_COLUMNS}); "
                             "write a | inside a cell as \\|")
    if raw_pipes:
        warns.append("a | inside `code` in a table isn't escaped; write \\| or the table breaks when rendered")

    # Caption and hashtags, per platform
    cap = "\n".join(sec.get("caption", []))
    tags = HASHTAG.findall(cap)
    lo, hi = HASHTAGS[platform]
    if "caption" in sec and not lo <= len(tags) <= hi:
        need = f"exactly {lo}" if lo == hi else f"{lo}-{hi}"
        fails.append(f"{len(tags)} hashtags for {platform} (need {need})")
    if platform == "youtube" and "caption" in sec:
        title = re.search(r"^\s*Title:\s*(.+?)\s*$", cap, flags=re.MULTILINE)
        if not title:
            fails.append("youtube: the caption needs a 'Title: ...' line")
        elif len(title.group(1)) > YT_TITLE_MAX:
            fails.append(f"youtube title is {len(title.group(1))} chars (max {YT_TITLE_MAX})")
    elif platform == "instagram" and "caption" in sec:
        n = len(words(HASHTAG.sub("", cap)))
        if not IG_CAPTION_WORDS[0] <= n <= IG_CAPTION_WORDS[1]:
            warns.append(f"instagram caption is {n} words (aim for {IG_CAPTION_WORDS[0]}-{IG_CAPTION_WORDS[1]})")

    # Claims and absolutes
    if "claims" in sec:
        listed = [c for c in items(sec["claims"]) if c.strip().lower() not in ("none", "n/a", "-")]
        if not listed:
            warns.append("'Claims checked' is empty: list each claim and how it was verified")
    places = [(f"beat {i}", b) for i, b in enumerate(beats, 1)]
    places += [(f"beat {r[0]} caption", r[2]) for r in rows if len(r) == 5]
    places += [(f"hook {i}", h) for i, h in enumerate(hooks, 1)] + [("post caption", cap)]
    found = {}
    for where, text in places:
        for m in ABSOLUTES.finditer(text):
            found.setdefault(m.group(0).lower(), {})[where] = None
    for word in sorted(found):
        warns.append(f"absolute word {word!r} ({', '.join(found[word])}): make sure it is literally true")
    return fails, warns, len(beats), total


def decode(data: bytes) -> tuple:
    """(text, warning or None). UTF-8 with or without a BOM, or UTF-16 with a BOM (what Windows
    PowerShell 5.1 writes with > or Out-File)."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return data.decode("utf-16"), None
        except UnicodeDecodeError:
            return data.decode("utf-16", errors="replace"), "the UTF-16 file has broken characters"
    try:
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return (data.decode("utf-8", errors="replace"),
                "the file isn't valid UTF-8 (save it as UTF-8); unreadable characters were replaced")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):   # never crash on a non-UTF-8 console (Windows cp1252)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", help="the script file (Markdown), or - for stdin")
    ap.add_argument("--platform", choices=sorted(HASHTAGS), help="default: the script header's Platform")
    ap.add_argument("--max-words", type=int, default=75, help="spoken words allowed (default 75; 60 for slower TTS)")
    ap.add_argument("--wps", type=float, default=2.7,
                    help="speaking rate for the time estimate, words per second (default 2.7; ~2.3 for Hindi TTS)")
    args = ap.parse_args(argv)
    if args.max_words < 1 or args.wps <= 0:
        ap.error("--max-words and --wps must be positive")
    try:
        if args.file == "-":
            data = sys.stdin.buffer.read()
        else:
            with open(args.file, "rb") as f:
                data = f.read()
    except OSError as e:
        print(f"FAIL: can't read {args.file}: {e.strerror or e}")
        return 2
    text, problem = decode(data)
    if problem:
        print(f"WARN: {problem}")
    blocks = parse(text)
    for b in blocks:
        b["script"] = bool(set(b["sections"]) & set(REQUIRED))
    scripts = [b for b in blocks if b["script"]]
    if not scripts:
        where = f"'## {blocks[0]['title']}' has none of the script sections" if blocks else \
            "no '## <Title>' script found"
        print(f"FAIL: {where}. Put each script under a '## Title' heading with the sections from SKILL.md "
              "(### Voice-over, ### Shot list, ...)")
        return 1
    passed = 0
    for b in blocks:
        if not b["script"]:
            print(f"SKIP: {b['title']} (not a script: no ### Voice-over, ### Shot list, ... under it)")
            continue
        fails, warns, n_beats, n_words = check_script(b, args.platform, args.max_words)
        print(f"{'FAIL' if fails else 'PASS'}: {b['title']} ({n_beats} beats, {n_words} words, "
              f"~{n_words / args.wps:.0f} s)")
        for f in fails:
            print(f"  FAIL  {f}")
        for w in warns:
            print(f"  WARN  {w}")
        passed += not fails
    if len(scripts) > 1:
        print(f"{len(scripts)} scripts: {passed} passed, {len(scripts) - passed} failed")
    return 0 if passed == len(scripts) else 1


if __name__ == "__main__":
    sys.exit(main())
