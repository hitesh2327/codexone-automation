"""Generate reel script, carousel slides, caption and hashtags for a ranked topic.

Two Gemini passes: (1) write the content, (2) a strict technical review. If the
reviewer finds errors, the content is rewritten once with the issues fed back.

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

from pydantic import BaseModel, Field

from src.config import DATA_DIR, OUTPUT_DIR, load_brand
from src.llm import generate_json
from src.logger import get_logger
from src.rank_topics import RankedTopic

log = get_logger("gen_content")


class ReelPoint(BaseModel):
    on_screen: str = Field(description="Big on-screen text, max 6 words. Use normal notation like O(1). Wrap the 1-2 key words in *asterisks*")
    narration: str = Field(description="Voiceover for this point, 1-3 short sentences")


class Reel(BaseModel):
    hook_on_screen: str = Field(description="On-screen hook, max 7 words. Wrap the 1-2 key words in *asterisks*")
    hook_narration: str = Field(description="Spoken hook, 1 sentence, creates curiosity honestly")
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


class Review(BaseModel):
    ok: bool = Field(description="True only if there are no factual/technical errors")
    issues: list[str] = Field(description="Each concrete error or misleading claim, with the fix")


SYSTEM = """You are the content writer for a tech education Instagram account.
You write clear, technically accurate, beginner-friendly content. You never invent
statistics, benchmarks, quotes or release details. If unsure of a fact, leave it out.
No clickbait, no exaggeration, no emojis in slide text."""


def slugify(text: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rsplit("-", 1)[0]  # cut at a word boundary
    return s or "post"


def _write_prompt(topic: RankedTopic, brand: dict, feedback: str = "") -> str:
    reel = brand["reel"]
    car = brand["carousel"]
    extra = f"\n\nFix these problems from the previous draft:\n{feedback}" if feedback else ""
    return f"""Create one Instagram reel and one carousel for {brand['handle']}.

Topic: {topic.title}
Category: {topic.category}
Angle: {topic.angle}
Source (for context only, may be empty): {topic.source_url}
Language: {brand['language']}

REEL ({reel['duration_sec']} seconds spoken, structure: {reel['structure']}):
- Total narration 90-140 words (110-160 including the demo). Short sentences, easy to speak aloud.
- Spell out symbols in NARRATION only (say "O of n" not "O(n)"); on-screen text uses normal notation like O(n).
- CTA narration should invite the viewer to follow {brand['handle']}.

DEMO (animated walkthrough of a concrete example):
- If the topic is an algorithm or data structure working on data (array, string, linked list,
  stack), include `demo`: a SMALL concrete input traced step by step. It is animated in the reel
  right after point 1 (pointers slide between cells, cells light up) and shown on carousel
  visual slides. Otherwise set demo to null.
- 4-7 steps. Each step is the state AFTER the action its narration describes. The first step is
  usually the starting state.
- pointers = variable names at indices; highlight = elements being compared/used now;
  done = elements finalized/visited; values = full new list only when data changes.
- The trace MUST be exactly what the algorithm (and the carousel code, if any) does. Simulate it
  carefully, one step at a time, before writing it.
- When there is a demo, keep each of the 3 reel points' narration to ONE sentence.

CAROUSEL ({car['slides']} slides, {car['size']} portrait):
- Slide 1 type=title: a curiosity-building but honest heading + short body subtitle.
- Middle slides type=content: one idea per slide. Use code where it genuinely helps
  (at least one code slide if the topic is technical). Code must be correct and runnable.
- If there is a demo: include 1-2 slides type=visual whose `steps` lists exactly 2 demo step indices
  showing the key moments (heading says what we are watching; body empty or one short line).
- Last slide type=cta: heading like "Save this for later" style, body mentions following {brand['handle']}.

CAPTION: 60-150 words, hook first line, value in the middle, question at the end. No hashtags.
HASHTAGS: 10-15 relevant tags; include a few of: {' '.join(brand['hashtags'])}.{extra}"""


def _review_prompt(content: Content) -> str:
    return f"""You are a strict senior engineer reviewing a social media post for technical accuracy.
Check every claim, complexity, definition and code snippet (does the code run and do what the
text says?). Ignore style. Flag only real errors or misleading statements.

If there is a `demo`, re-simulate the algorithm yourself on demo.values, step by step, and
compare EVERY step's pointers, highlight, done, values and caption against your simulation.
Flag any mismatch with the exact correct state for that step.

{content.model_dump_json(indent=2)}"""


def normalize(c: Content) -> Content:
    """Fix a frequent model slip: code returned as one line with literal backslash-n escapes."""
    for s in c.carousel:
        if s.code and "\n" not in s.code and "\\n" in s.code:
            s.code = s.code.replace("\\n", "\n").replace('\\"', '"').replace("\\t", "    ")
    return c


def validate_shape(c: Content, brand: dict) -> list[str]:
    """Cheap structural checks the model sometimes gets wrong."""
    problems = []
    lo, hi = (int(x) for x in str(brand["carousel"]["slides"]).split("-"))
    if not lo <= len(c.carousel) <= hi:
        problems.append(f"carousel must have {lo}-{hi} slides, got {len(c.carousel)}")
    if c.carousel and c.carousel[0].type != "title":
        problems.append("first slide must be type=title")
    if c.carousel and c.carousel[-1].type != "cta":
        problems.append("last slide must be type=cta")
    if len(c.reel.points) != 3:
        problems.append(f"reel must have exactly 3 points, got {len(c.reel.points)}")
    for i, s in enumerate(c.carousel, 1):
        long_lines = [(n, l) for n, l in enumerate(s.code.splitlines(), 1) if len(l) > CODE_LINE_MAX]
        if long_lines:
            detail = "; ".join(f"line {n} has {len(l)} chars: {l.strip()[:70]!r}" for n, l in long_lines[:4])
            problems.append(f"slide {i}: code lines must be at most {CODE_LINE_MAX} chars "
                            f"(split long calls/strings across lines) -- {detail}")
        if s.code and len(s.code.splitlines()) > 14:
            problems.append(f"slide {i}: code too long (max 12 lines)")
    problems += validate_demo(c)
    if len(c.caption) + sum(len(h) + 1 for h in c.hashtags) > 2100:
        problems.append("caption + hashtags exceed Instagram's 2200 char limit")
    return problems


CODE_LINE_MAX = 56  # the renderer shrinks code to fit this width at >= 23px

MAX_VALUES = {"array": 10, "string": 10, "linked_list": 7, "stack": 6}


def validate_demo(c: Content) -> list[str]:
    """Index/bounds checks on the demo trace (correctness is checked by the reviewer)."""
    problems, d = [], c.demo
    visual_slides = [s for s in c.carousel if s.type == "visual"]
    if not d:
        return ["visual slides need a demo"] if visual_slides else []
    if not d.values:
        return ["demo.values is empty"]
    if len(d.values) > MAX_VALUES[d.kind]:
        problems.append(f"demo: {d.kind} can show at most {MAX_VALUES[d.kind]} elements")
    if d.kind == "string" and any(len(v) != 1 for v in d.values):
        problems.append("demo: string values must be single characters")
    if d.kind != "linked_list" and d.cycle_to != -1:
        problems.append("demo: cycle_to only applies to linked_list")
    if not -1 <= d.cycle_to < len(d.values):
        problems.append("demo: cycle_to out of range")
    if not 3 <= len(d.steps) <= 8:
        problems.append(f"demo: needs 4-7 steps, got {len(d.steps)}")
    n = len(d.values)
    for k, st in enumerate(d.steps):
        n = len(st.values) if st.values else n
        if st.values and len(st.values) > MAX_VALUES[d.kind]:
            problems.append(f"demo step {k}: too many values")
        bad = [i for i in [p.index for p in st.pointers] + st.highlight + st.done if not 0 <= i < n]
        if bad:
            problems.append(f"demo step {k}: indices {bad} out of range for {n} elements")
        if len(st.caption) > 32:
            problems.append(f"demo step {k}: caption too long (max 28 chars)")
        if len(st.narration.split()) > 18:
            problems.append(f"demo step {k}: narration too long (max 14 words)")
        if any(len(p.name) > 8 for p in st.pointers):
            problems.append(f"demo step {k}: pointer names must be short")
    for s in visual_slides:
        if not s.steps or any(not 0 <= i < len(d.steps) for i in s.steps):
            problems.append(f"visual slide '{s.heading}': steps must be valid demo step indices")
        if len(s.steps) > 2:
            problems.append(f"visual slide '{s.heading}': max 2 steps")
    return problems


def generate(topic: RankedTopic, feedback: str = "") -> Content:
    brand = load_brand()
    content = generate_json(_write_prompt(topic, brand, feedback), Content, system=SYSTEM)
    attempts = 3
    for attempt in range(1, attempts + 1):
        content = normalize(content)
        problems = validate_shape(content, brand)
        if not problems:  # only spend a review call on structurally valid drafts
            review = generate_json(_review_prompt(content), Review, temperature=0.1)
            problems = [] if review.ok else review.issues
        if not problems:
            log.info("content passed review")
            break
        log.warning("review found %d issue(s): %s", len(problems), "; ".join(problems))
        if attempt == attempts:
            raise RuntimeError("content still failing review after rewrites: " + "; ".join(problems))
        # Revise the previous draft (keeps what was right) instead of starting over.
        fb = ("\n".join(f"- {p}" for p in problems) + (f"\n- {feedback}" if feedback else "")
              + "\n\nPrevious draft to revise:\n" + content.model_dump_json())
        content = generate_json(_write_prompt(topic, brand, fb), Content, system=SYSTEM)
    content.hashtags = [h if h.startswith("#") else f"#{h}" for h in content.hashtags][:15]
    content.topic, content.category = topic.title, topic.category
    return content


def post_dir(day: str, title: str) -> Path:
    return OUTPUT_DIR / day / slugify(title)


def save(content: Content, day: str) -> Path:
    d = post_dir(day, content.topic)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "content.json"
    path.write_text(content.model_dump_json(indent=2), encoding="utf-8")
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
