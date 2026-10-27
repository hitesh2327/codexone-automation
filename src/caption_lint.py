# Vendored rules from .claude/skills/ig-caption/SKILL.md, MIT License.
# Instagram capped hashtags at 5 per post on 18 December 2025.
# Used by src/gen_content.py to enforce compliance before saving.
"""Caption linter: enforce Instagram platform rules on every generated post."""
from __future__ import annotations

import re

from src.logger import get_logger

log = get_logger("caption_lint")

MAX_HASHTAGS = 5
IG_CHAR_LIMIT = 2200

# Dead hashtags: Instagram has confirmed these do not increase reach.
DEAD_HASHTAGS: frozenset[str] = frozenset({
    "#viral", "#fyp", "#foryou", "#explorepage", "#foryoupage",
    "#reels", "#reelsinstagram", "#trending", "#explore",
    "#instagood", "#love", "#instadaily", "#follow", "#followforfollow",
})

_LINK_RE = re.compile(r"https?://\S+")


def lint(caption: str, hashtags: list[str]) -> list[str]:
    """Return a list of issue strings (prefixed FAIL or WARN). Empty = clean."""
    issues: list[str] = []

    if len(hashtags) > MAX_HASHTAGS:
        issues.append(
            f"FAIL: {len(hashtags)} hashtags — Instagram caps at {MAX_HASHTAGS} (since Dec 2025)"
        )

    dead = [h for h in hashtags if h.lower() in DEAD_HASHTAGS]
    if dead:
        issues.append(f"WARN: dead hashtags (zero reach value): {', '.join(dead)}")

    if _LINK_RE.search(caption):
        issues.append("FAIL: URL in caption body — captions are not clickable on Instagram")

    total_len = len(caption) + sum(len(h) + 1 for h in hashtags)
    if total_len > IG_CHAR_LIMIT:
        issues.append(
            f"FAIL: caption + hashtags = {total_len} chars, exceeds {IG_CHAR_LIMIT}-char limit"
        )

    return issues


def enforce(caption: str, hashtags: list[str]) -> tuple[str, list[str]]:
    """Auto-fix what can be fixed without rewriting.

    - Strips dead hashtags
    - Caps at MAX_HASHTAGS (keeps most relevant/specific ones)
    Returns (caption, clean_hashtags).
    """
    # Remove dead tags first, then cap the remainder.
    clean = [h for h in hashtags if h.lower() not in DEAD_HASHTAGS]
    if len(clean) < len(hashtags):
        removed = [h for h in hashtags if h.lower() in DEAD_HASHTAGS]
        log.info("caption_lint: removed dead hashtags: %s", ", ".join(removed))

    if len(clean) > MAX_HASHTAGS:
        log.info(
            "caption_lint: trimmed hashtags from %d to %d (IG cap)",
            len(clean), MAX_HASHTAGS,
        )
        clean = clean[:MAX_HASHTAGS]

    return caption, clean
