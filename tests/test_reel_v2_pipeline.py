"""Which posts get the v2 animated-diagram design, and that falling back is never silent.
Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rank_topics import TECH_CATEGORY_DESCRIPTIONS  # noqa: E402
from src.reel_v2 import pipeline as v2  # noqa: E402
from src.reel_v2.spec import _prompt  # noqa: E402

BRAND = {"handle": "@test", "hashtags": ["#dsa"]}


@pytest.mark.parametrize("category", sorted(TECH_CATEGORY_DESCRIPTIONS))
def test_every_builtin_category_uses_v2_by_default(monkeypatch, category):
    monkeypatch.setattr(v2, "load_brand", lambda: {"reel": {}})
    assert v2.uses_v2(category)


def test_stale_opt_in_list_no_longer_keeps_dsa_and_interview_classic(monkeypatch):
    # the shape of a brand copied into the DB before this change
    monkeypatch.setattr(v2, "load_brand", lambda: {"reel": {"v2_categories": ["SystemDesign", "AI", "OS", "Dev"]}})
    assert v2.uses_v2("DSA") and v2.uses_v2("Interview")


def test_classic_categories_opts_out(monkeypatch):
    monkeypatch.setattr(v2, "load_brand", lambda: {"reel": {"classic_categories": ["Interview"]}})
    assert not v2.uses_v2("Interview")
    assert v2.uses_v2("DSA")


@pytest.mark.parametrize("category", ["DSA", "Interview"])
def test_prompt_carries_category_notes(category):
    assert f"CATEGORY NOTES ({category})" in _prompt("t", category, "", BRAND)


def test_prompt_for_system_design_has_no_category_notes():
    assert "CATEGORY NOTES" not in _prompt("t", "SystemDesign", "", BRAND)


def test_fallback_warning_goes_to_telegram(monkeypatch):
    from src import approve_bot
    sent = []
    monkeypatch.setattr(approve_bot, "notify", lambda text, *a, **k: sent.append(text))
    v2.warn_fallback("Reel", "Binary Search", ValueError("scene spec still invalid"))
    assert len(sent) == 1 and "Binary Search" in sent[0] and "classic design" in sent[0]


def test_fallback_warning_never_raises(monkeypatch):
    from src import approve_bot

    def boom(*a, **k):
        raise RuntimeError("telegram down")
    monkeypatch.setattr(approve_bot, "notify", boom)
    v2.warn_fallback("Carousel", "Binary Search")  # must not raise
