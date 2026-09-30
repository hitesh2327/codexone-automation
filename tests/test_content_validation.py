"""A cosmetic nit must never cost the day's post.

Two daily runs (28 and 30 Sep) failed outright because Gemini kept writing one code line a
few characters over the limit. Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gen_content import (CODE_LINE_HARD_MAX, CODE_LINE_MAX, Content, Reel, ReelPoint,  # noqa: E402
                             Slide, cosmetic_problems, validate_shape)

BRAND = {"carousel": {"slides": "5-7"}}


def content(code: str = "") -> Content:
    slides = [Slide(type="title", heading="T", body="b")]
    slides += [Slide(type="content", heading=f"H{i}", body="b", code=code if i == 1 else "")
               for i in range(1, 5)]
    slides.append(Slide(type="cta", heading="C", body="b"))
    return Content(
        topic="T", category="DSA", caption="c", hashtags=["#x"],
        reel=Reel(hook_on_screen="h", hook_narration="h",
                  points=[ReelPoint(on_screen=f"p{i}", narration="n") for i in range(3)],
                  cta_on_screen="c", cta_narration="c"),
        carousel=slides,
    )


def test_clean_code_has_no_problems():
    c = content("def f():\n    return 1")
    assert validate_shape(c, BRAND) == [] and cosmetic_problems(c) == []


def test_slightly_long_line_is_cosmetic_not_blocking():
    """The exact 30 Sep failure: a 59-char line (limit 56)."""
    line = "    if not self.min_stack or val <= self.min_stack[-1]:"  # 59 chars, as in the real run
    line += " " * (CODE_LINE_MAX + 3 - len(line))
    assert len(line) == CODE_LINE_MAX + 3 <= CODE_LINE_HARD_MAX
    c = content(line)
    assert validate_shape(c, BRAND) == []          # does not block the post
    assert len(cosmetic_problems(c)) == 1          # still asks for a rewrite


def test_unreadably_long_line_still_blocks():
    c = content("x = " + "a" * CODE_LINE_HARD_MAX)
    problems = validate_shape(c, BRAND)
    assert len(problems) == 1 and "code lines must be at most" in problems[0]
    assert cosmetic_problems(c) == []              # counted once, as blocking


@pytest.mark.parametrize("length,blocking", [
    (CODE_LINE_MAX, False), (CODE_LINE_MAX + 1, False),
    (CODE_LINE_HARD_MAX, False), (CODE_LINE_HARD_MAX + 1, True),
])
def test_threshold_boundaries(length, blocking):
    c = content("a" * length)
    assert bool(validate_shape(c, BRAND)) is blocking


def test_real_errors_still_block():
    c = content()
    c.carousel = c.carousel[:2]                    # too few slides
    assert any("5-7 slides" in p for p in validate_shape(c, BRAND))
