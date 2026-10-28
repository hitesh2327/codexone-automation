"""Generate a post (reel + carousel, caption, hashtags) for a ranked topic.

The animated-diagram engine (src/reel_v2/spec.py) writes, repairs, reviews and rewrites the scene;
this module wraps it in the `Content` that approval, upload and publishing read.

Output: output/<date>/<slug>/content.json

Usage:
    python -m src.gen_content [--date YYYY-MM-DD] [--feedback "..."] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from src.config import DATA_DIR, OUTPUT_DIR, Language
from src.logger import get_logger
from src.rank_topics import RankedTopic

log = get_logger("gen_content")


class ReelPoint(BaseModel):
    on_screen: str = Field(description="Big on-screen text, max 6 words. Use normal notation like O(1). Wrap the 1-2 key words in *asterisks*")
    narration: str = Field(description="Voiceover for this point, 1-3 short sentences")


class Reel(BaseModel):
    hook_on_screen: str = Field(description="On-screen hook, max 7 words. Wrap the 1-2 key words in *asterisks*")
    hook_narration: str = Field(description="Spoken hook, 1 sentence, creates curiosity honestly")
    hook_alternatives: list[str] = Field(
        default_factory=list,
        description="3 other spoken hooks for the same reel, each 5-12 words and true to the content, each a different "
                    "formula: a specific number or result, what's at stake for the viewer, a direct 'you' statement. "
                    "No greetings ('hey guys'), no 'in this video'")
    points: list[ReelPoint] = Field(description="Exactly 3 points")
    cta_on_screen: str = Field(description="On-screen CTA, max 6 words. Wrap the 1-2 key words in *asterisks*")
    cta_narration: str = Field(description="Spoken CTA, 1 sentence")


class Pointer(BaseModel):
    name: str = Field(description="Variable name shown on screen, max 6 chars, e.g. i, j, lo, hi, slow, fast, top")
    index: int = Field(description="0-based index of the element it points at")


class DemoStep(BaseModel):
    narration: str = Field(description="One short spoken sentence (max 14 words) describing this step")
    caption: str = Field(description="Compact on-screen state, max 28 chars, e.g. 'slow=2  fast=4' or 'sum=9 > 7'")
    pointers: list[Pointer] = Field(default_factory=list)
    highlight: list[int] = Field(default_factory=list, description="Indices being compared/active right now")
    done: list[int] = Field(default_factory=list, description="Indices already finalized/visited")
    values: list[str] = Field(default_factory=list,
                              description="Only if the data changed in this step (swap, write, push, pop): the FULL new list. Else empty")


class Demo(BaseModel):
    title: str = Field(description="Short title of the example, max 6 words, e.g. 'Two pointers on [1,3,5,8]'")
    kind: Literal["array", "string", "linked_list", "stack"]
    values: list[str] = Field(description="Initial elements as strings. array/string max 10, linked_list max 7, stack max 6. string = one char each")
    cycle_to: int = Field(default=-1, description="linked_list only: index the tail links back to (cycle), else -1")
    steps: list[DemoStep] = Field(description="4-7 steps; each shows the state AFTER the narrated action")


class Slide(BaseModel):
    type: Literal["title", "content", "visual", "cta"]
    kicker: str = Field(default="", description="Tiny label above heading, e.g. 'DSA' or 'Step 2'")
    heading: str = Field(description="Slide heading, max 8 words. On title/cta slides wrap the 1-3 key words in *asterisks*")
    body: str = Field(default="", description="Short text. Use '\\n' separated bullet lines for lists. Max 45 words")
    code: str = Field(default="", description="Optional code snippet, max 12 lines, max 50 chars per line (break long calls across lines)")
    code_language: str = Field(default="", description="e.g. python, java, cpp, sql, bash")
    steps: list[int] = Field(default_factory=list, description="type=visual only: exactly 2 demo step indices to show")


class Content(BaseModel):
    topic: str
    category: str
    reel: Reel
    demo: Demo | None = Field(default=None, description="Animated step-by-step example, or null if the topic has no data to animate")
    carousel: list[Slide] = Field(description="5-7 slides: first type=title, last type=cta, rest type=content or visual")
    caption: str = Field(description="Instagram caption without hashtags, 60-150 words, ends with a question")
    hashtags: list[str] = Field(description="10-15 hashtags, each starting with #")
    # Reel narration language, set by generate() (not chosen by the model): en | hi (Hinglish)
    language: Language = "en"
    # v2 scene spec (src/reel_v2) when this post uses the animated-diagram engine; not part of
    # the Gemini schema or content.json (it is saved separately as scene.json).
    _scene: object | None = PrivateAttr(default=None)


def slugify(text: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rsplit("-", 1)[0]  # cut at a word boundary
    return s or "post"


def _extract_formula_from_hook(hook: str) -> str | None:
    """Parse the [#N Name] annotation Gemini adds when using the formula block."""
    import re as _re
    m = _re.search(r"\[#\d+\s+([^\]]+)\]", hook)
    if m:
        return m.group(1).strip()
    return None


def _clean_formula_annotation(hook: str) -> str:
    """Remove the [#N Name] annotation from the final spoken hook."""
    import re as _re
    return _re.sub(r"\s*\[#\d+[^\]]*\]\s*", " ", hook).strip()


def generate(topic: RankedTopic, feedback: str = "", language: Language = "en") -> Content:
    """Write the post with the animated-diagram engine (src/reel_v2). There is no other format: if no valid
    scene comes out (after the engine's own repairs and rewrites), this raises and the run fails visibly."""
    from src.reel_v2 import pipeline as v2
    from src.reel_v2.spec import generate as generate_scene
    try:
        spec = generate_scene(topic.title, topic.category, topic.angle, feedback, language)
    except Exception as e:
        v2.notify_failure("Script", topic.title, e)
        raise
    log.info("v2 scene: %d beats, %d words", len(spec.beats), sum(len(b.narration.split()) for b in spec.beats))
    content = _post_process(v2.to_content(spec, topic.title, topic.category))
    content.language = language
    return content


def _post_process(content: Content) -> Content:
    """Phase 2+3: caption lint + humanise + Phase 5: score the hook. Called after every generation path."""
    # --- Phase 1: strip formula annotation from final hook, record it ---
    hook_formula = _extract_formula_from_hook(content.reel.hook_narration)
    if hook_formula:
        content.reel.hook_narration = _clean_formula_annotation(content.reel.hook_narration)
        log.info("hook formula used: %s", hook_formula)

    # --- Phase 3: humanise captions and narrations ---
    try:
        from src.humanize import clean as humanize_text
        before = content.caption
        content.caption = humanize_text(content.caption)
        content.reel.hook_narration = humanize_text(content.reel.hook_narration)
        for pt in content.reel.points:
            pt.narration = humanize_text(pt.narration)
        content.reel.cta_narration = humanize_text(content.reel.cta_narration)
        if content.caption != before:
            log.info("humanize: caption cleaned (slop/em-dash/invisible chars removed)")
    except Exception:  # noqa: BLE001
        log.exception("humanize pass failed; continuing with original text")

    # --- Phase 2: enforce caption lint rules (hashtag cap, dead tags, IG limit) ---
    try:
        from src.caption_lint import enforce, lint
        issues = lint(content.caption, content.hashtags)
        for issue in issues:
            (log.warning if issue.startswith("FAIL") else log.info)("caption_lint: %s", issue)
        content.caption, content.hashtags = enforce(content.caption, content.hashtags)
    except Exception:  # noqa: BLE001
        log.exception("caption_lint pass failed; continuing with original hashtags")

    # Ensure hashtag format after linting
    content.hashtags = [h if h.startswith("#") else f"#{h}" for h in content.hashtags]

    # --- Phase 5: score hook and log for ig-audit ---
    try:
        from src.hookscore import run as score_hook
        _, hook_score, hook_verdict, _ = score_hook(content.reel.hook_narration)
        log.info("hook score: %.0f (%s)", hook_score, hook_verdict)
    except Exception:  # noqa: BLE001
        hook_score, hook_verdict = None, None

    try:
        from src.post_log import record as log_post
        log_post(
            post_id=f"{content.category}-{slugify(content.topic)}",
            kind="reel+carousel",
            topic=content.topic,
            category=content.category,
            hook=content.reel.hook_narration,
            hook_formula=hook_formula,
            hook_score=hook_score,
            humanness_verdict=hook_verdict,
            caption_len=len(content.caption),
            hashtag_count=len(content.hashtags),
        )
    except Exception:  # noqa: BLE001
        log.exception("post_log.record failed silently")

    return content


def post_dir(day: str, title: str) -> Path:
    return OUTPUT_DIR / day / slugify(title)


def save(content: Content, day: str) -> Path:
    d = post_dir(day, content.topic)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "content.json"
    path.write_text(content.model_dump_json(indent=2), encoding="utf-8")
    if content._scene is not None:
        from src.reel_v2.pipeline import save_scene
        save_scene(content._scene, d)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate post content with Gemini")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--feedback", default="", help="extra instructions (used by Regenerate)")
    ap.add_argument("--dry-run", action="store_true", help="print only; write nothing")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ranked = DATA_DIR / f"ranked_{args.date}.json"
    if not ranked.exists():
        log.error("%s not found -- run `python -m src.rank_topics` first", ranked)
        return 1
    topic = RankedTopic.model_validate_json(ranked.read_text(encoding="utf-8"))
    content = generate(topic, args.feedback)
    print(json.dumps(content.model_dump(), indent=2, ensure_ascii=False))
    if not args.dry_run:
        log.info("saved → %s", save(content, args.date))
    return 0


if __name__ == "__main__":
    sys.exit(main())
