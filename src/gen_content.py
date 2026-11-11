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

_PREAMBLE_RE = re.compile(
    r"^\s*(?:(?:hey|hi|hello)\s+(?:guys|everyone|devs|friends)[,!.\s]+|"
    r"(?:stop\s+scrolling|don'?t\s+scroll)[,!.\s]+|"
    r"in\s+(?:this|today'?s)\s+(?:video|reel|short)[,:\s]+|"
    r"today\s+we(?:'re|\s+are)\s+(?:going\s+to|gonna)\s+(?:learn|talk\s+about|look\s+at)\s+)",
    re.I,
)
_WEAK_IG_QUESTION_RE = re.compile(
    r"(?:have you|would you|do you|what do you think|let me know|thoughts\?)",
    re.I,
)
_ACTION_CTA_RE = re.compile(r"\b(?:save|bookmark|comment|share|send|dm)\b", re.I)
_LEADING_DECOR_RE = re.compile(r"^(?:[\U0001F300-\U0001FAFF\u2600-\u27BF]+|#\S+)\s*")


class ReelPoint(BaseModel):
    on_screen: str = Field(description="Big on-screen text, max 6 words. Use normal notation like O(1). Wrap the 1-2 key words in *asterisks*")
    narration: str = Field(description="Voiceover for this point, 1-3 short sentences")


class Reel(BaseModel):
    hook_on_screen: str = Field(description="On-screen hook, max 7 words. Wrap the 1-2 key words in *asterisks*")
    hook_narration: str = Field(description="Spoken hook under 2.5s (5-12 words), front-loaded stakes/number, no greeting or preamble")
    hook_alternatives: list[str] = Field(
        default_factory=list,
        description="3 other spoken hooks for the same reel, each 5-12 words and true to the content, each a different "
                    "formula: a specific number or result, what's at stake for the viewer, a direct 'you' statement. "
                    "No greetings ('hey guys'), no 'in this video'")
    points: list[ReelPoint] = Field(description="Exactly 3 points")
    cta_on_screen: str = Field(description="On-screen CTA, max 6 words. Wrap the 1-2 key words in *asterisks*")
    cta_narration: str = Field(description="Payoff + seamless loop-back line connecting back into the opening hook (no 'follow for more')")


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
    caption: str = Field(description="Instagram SEO caption without hashtags, 60-120 words: line 1 <= 125 chars hook, natural search keywords, single save/share/keyword CTA")
    hashtags: list[str] = Field(description="Up to 5 specific niche hashtags (Instagram Dec 2025 cap), each starting with #, no #viral/#fyp")
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
    m = re.search(r"\[#\d+\s+([^\]]+)\]", hook)
    return m.group(1).strip() if m else None


def _clean_formula_annotation(hook: str) -> str:
    """Remove the [#N Name] annotation from the final spoken hook."""
    return re.sub(r"\s*\[#\d+[^\]]*\]\s*", " ", hook).strip()


def _strip_hook_preamble(hook: str) -> str:
    """Strip dealbreaker greetings/preambles and capitalize the real hook start."""
    cleaned = _PREAMBLE_RE.sub("", hook).strip()
    if not cleaned:
        return hook.strip()
    return cleaned[0].upper() + cleaned[1:]


def _sync_scene_hook(content: Content, new_hook: str) -> None:
    """Keep attached v2 SceneSpec beat 1 narration and trigger word valid after hook cleanup/swap."""
    beats = getattr(content._scene, "beats", None)
    if not beats:
        return
    b0 = beats[0]
    b0.narration = new_hook
    spoken = [w.strip(".,?!'\"।") for w in new_hook.split() if w.strip(".,?!'\"।")]
    if spoken and b0.trigger.lower().strip(".,?!'\"।") not in [w.lower() for w in spoken]:
        b0.trigger = max(spoken, key=len)


def _enforce_hook(content: Content) -> tuple[str | None, float | None, str | None]:
    """Score the spoken hook, strip English preambles, promote stronger alternatives, and sync v2 beat 1."""
    hook_formula = _extract_formula_from_hook(content.reel.hook_narration)
    hook = _clean_formula_annotation(content.reel.hook_narration)
    if hook_formula:
        log.info("hook formula used: %s", hook_formula)

    if content.language == "en":
        stripped = _strip_hook_preamble(hook)
        if stripped != hook:
            log.info("stripped weak preamble from hook: %r -> %r", hook, stripped)
            hook = stripped

    content.reel.hook_narration = hook
    if content._scene is not None and content.language == "en":
        _sync_scene_hook(content, hook)

    try:
        from src.hookscore import run as score_hook
        _, best_score, best_verdict, best_flags = score_hook(hook)
        if content.language == "en" and content.reel.hook_alternatives:
            for alt in content.reel.hook_alternatives:
                cand = _strip_hook_preamble(_clean_formula_annotation(alt))
                if not cand:
                    continue
                _, alt_score, alt_verdict, alt_flags = score_hook(cand)
                better_clean = len(alt_flags) < len(best_flags) and alt_score >= best_score - 5
                better_score = len(alt_flags) <= len(best_flags) and (
                    alt_score >= best_score + 5 or (alt_verdict == "STRONG" and best_verdict != "STRONG")
                )
                if better_clean or better_score:
                    log.info("promoted hook alternative (%.0f %s -> %.0f %s): %s",
                             best_score, best_verdict, alt_score, alt_verdict, cand)
                    hook, best_score, best_verdict, best_flags = cand, alt_score, alt_verdict, alt_flags
                    content.reel.hook_narration = hook
                    _sync_scene_hook(content, hook)
        log.info("hook score: %.0f (%s)", best_score, best_verdict)
        if content.language == "en" and (best_verdict == "WEAK" or best_flags):
            log.warning("weak hook (%s, %.0f): %s%s", best_verdict, best_score, hook,
                        f" | flags: {'; '.join(best_flags)}" if best_flags else "")
        return hook_formula, best_score, best_verdict
    except Exception:  # noqa: BLE001
        return hook_formula, None, None


def _enforce_ig_caption(caption: str, topic: str) -> str:
    """Keep IG caption line 1 clean before the 125-char fold and ensure a single save/share/keyword ask."""
    text = caption.strip()
    if not text:
        return text
    lines = text.splitlines()
    lines[0] = _LEADING_DECOR_RE.sub("", lines[0]).strip()
    if len(lines[0]) > 125:
        log.info("caption line 1 is %d chars (> 125-char IG '... more' fold)", len(lines[0]))
    text = "\n".join(lines).strip()
    if not _ACTION_CTA_RE.search(text):
        last = lines[-1].strip()
        cta = f"Save this {topic} breakdown for your next review."
        if _WEAK_IG_QUESTION_RE.search(last):
            lines[-1] = cta
            text = "\n".join(lines).strip()
        else:
            text = f"{text}\n\n{cta}"
    return text


def youtube_metadata(content: Content) -> dict:
    """Build YouTube Shorts SEO metadata (title < 60 chars, description, categoryId, tags) for Content."""
    from src.publish_youtube import build_metadata
    full = f"{content.caption.strip()}\n\n{' '.join(content.hashtags)}".strip()
    return build_metadata(full, audio_language=content.language, category=content.category, topic=content.topic)


def generate(topic: RankedTopic, feedback: str = "", language: Language = "en") -> Content:
    """Write the post with the animated-diagram engine (src/reel_v2). There is no other format: if no valid
    scene comes out (after the engine's own repairs and rewrites), this raises and the run fails visibly."""
    from src.reel_v2 import pipeline as v2
    from src.reel_v2.spec import generate as generate_scene
    prompt_style = getattr(topic, "prompt_style", "") or ""
    try:
        spec = generate_scene(topic.title, topic.category, topic.angle, feedback, language, prompt_style=prompt_style)
    except Exception as e:
        v2.notify_failure("Script", topic.title, e)
        raise
    log.info("v2 scene: %d beats, %d words", len(spec.beats), sum(len(b.narration.split()) for b in spec.beats))
    content = v2.to_content(spec, topic.title, topic.category)
    content.language = language
    return _post_process(content)


def _post_process(content: Content) -> Content:
    """Enforce viral hook quality, humanise text, enforce IG SEO caption + hashtag cap, and log for ig-audit."""
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

    hook_formula, hook_score, hook_verdict = _enforce_hook(content)
    content.caption = _enforce_ig_caption(content.caption, content.topic)

    try:
        from src.caption_lint import enforce, lint
        issues = lint(content.caption, content.hashtags)
        for issue in issues:
            (log.warning if issue.startswith("FAIL") else log.info)("caption_lint: %s", issue)
        content.caption, content.hashtags = enforce(content.caption, content.hashtags)
    except Exception:  # noqa: BLE001
        log.exception("caption_lint pass failed; continuing with original hashtags")

    content.hashtags = [h if h.startswith("#") else f"#{h}" for h in content.hashtags]

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
