"""Every post uses the animated-diagram engine; when it can't make one, the run fails visibly (no old style).
Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import gen_content  # noqa: E402
from src.gen_content import Reel  # noqa: E402
from src.rank_topics import RankedTopic  # noqa: E402
from src.reel_v2 import pipeline as v2  # noqa: E402
from src.reel_v2 import spec as specmod  # noqa: E402
from src.reel_v2.spec import SceneSpec, _prompt  # noqa: E402

BRAND = {"handle": "@test", "hashtags": ["#dsa"]}
EXAMPLE = Path(__file__).resolve().parent.parent / "src" / "reel_v2" / "examples" / "blue_green.json"


def topic(category="SystemDesign"):
    return RankedTopic(category=category, title="Blue-Green", angle="", source_url="", evergreen=True, why="t")


@pytest.fixture()
def telegram(monkeypatch):
    from src import approve_bot, db
    monkeypatch.setattr(db, "enabled", lambda: False)
    sent: list[str] = []
    monkeypatch.setattr(approve_bot, "notify", lambda text, *a, **k: sent.append(text))
    return sent


@pytest.mark.parametrize("category", ["SystemDesign", "DSA", "Interview", "Cooking"])   # any category, any niche
def test_every_post_uses_the_scene_engine(monkeypatch, telegram, category):
    monkeypatch.setattr(specmod, "generate", lambda *a, **k: SceneSpec.model_validate_json(EXAMPLE.read_text(encoding="utf-8")))
    monkeypatch.setattr(v2, "load_brand", lambda: {"handle": "@t"})
    c = gen_content.generate(topic(category))
    assert c._scene is not None and c.category == category and not telegram


def test_old_writer_is_gone():
    for name in ("_write_prompt", "_review_prompt", "validate_shape", "pick_hook", "CLASSIC_HINGLISH"):
        assert not hasattr(gen_content, name), name
    assert not hasattr(v2, "uses_v2") and not hasattr(v2, "warn_fallback")


def test_a_failed_scene_fails_the_run_and_says_so(monkeypatch, telegram):
    def boom(*a, **k):
        raise ValueError("scene spec still invalid: beat 1: heading too long")
    monkeypatch.setattr(specmod, "generate", boom)
    with pytest.raises(ValueError):
        gen_content.generate(topic())
    assert len(telegram) == 1 and "Blue-Green" in telegram[0] and "failed" in telegram[0]


def test_a_failed_render_fails_instead_of_rendering_the_old_style(monkeypatch, telegram, tmp_path):
    from src import render_post
    from src.reel_v2 import render
    monkeypatch.setattr(specmod, "generate", lambda *a, **k: SceneSpec.model_validate_json(EXAMPLE.read_text(encoding="utf-8")))
    monkeypatch.setattr(v2, "load_brand", lambda: {"handle": "@t"})
    content = gen_content.generate(topic())

    def boom(*a, **k):
        raise RuntimeError("chromium crashed")
    monkeypatch.setattr(render, "render_carousel", boom)
    with pytest.raises(RuntimeError):
        render_post.render_carousel(content, tmp_path / "carousel")
    assert "Carousel" in telegram[0]


def test_failure_notice_never_raises(monkeypatch):
    from src import approve_bot

    def down(*a, **k):
        raise RuntimeError("telegram down")
    monkeypatch.setattr(approve_bot, "notify", down)
    v2.notify_failure("Script", "Binary Search", ValueError("x"))   # must not raise


@pytest.mark.parametrize("category", ["DSA", "Interview"])
def test_prompt_carries_category_notes(category):
    assert f"CATEGORY NOTES ({category})" in _prompt("t", category, "", BRAND)


def test_prompt_for_system_design_has_no_category_notes():
    assert "CATEGORY NOTES" not in _prompt("t", "SystemDesign", "", BRAND)


def test_hook_formulas_reach_the_scene_prompt(monkeypatch, tmp_path):
    f = tmp_path / "hooks.json"
    f.write_text('{"hooks": [{"id": 3, "name": "Nobody Tells You", "template": "Nobody tells you X"}]}')
    monkeypatch.setattr(specmod, "HOOKS_FILE", f)
    p = _prompt("t", "AI", "", {**BRAND, "reel": {"preferred_hook_formulas": ["Nobody Tells You"]}})
    assert "#03 Nobody Tells You" in p and "OVER-INDEXING" in p and "never say the formula" in p
    monkeypatch.setattr(specmod, "HOOKS_FILE", tmp_path / "missing.json")
    assert "HOOK FORMULA" not in _prompt("t", "AI", "", BRAND)


def test_older_content_without_alternatives_still_loads():
    assert Reel(hook_on_screen="h", hook_narration="h", points=[], cta_on_screen="c",
                cta_narration="c").hook_alternatives == []


def test_prompt_asks_for_instagrams_hashtag_limit():
    from src.caption_lint import MAX_HASHTAGS
    p = _prompt("t", "AI", "", BRAND)
    assert f"HASHTAGS: exactly {MAX_HASHTAGS}" in p and "#fyp" in p and "10-15" not in p
    assert str(MAX_HASHTAGS) in SceneSpec.model_fields["hashtags"].description


def test_post_never_carries_more_than_the_limit(monkeypatch):
    from src.caption_lint import MAX_HASHTAGS
    monkeypatch.setattr(v2, "load_brand", lambda: {"handle": "@t"})
    s = SceneSpec.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    s.hashtags = [f"#tag{i}" for i in range(11)]
    assert len(v2.to_content(s, "Blue-Green", "SystemDesign").hashtags) == MAX_HASHTAGS
