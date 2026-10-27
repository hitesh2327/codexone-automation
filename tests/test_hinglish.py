"""Hinglish narration (docs/specs/hinglish-narration-plan.md): only the spoken text changes language.
Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import gen_content  # noqa: E402
from src.rank_topics import RankedTopic  # noqa: E402
from src.reel_v2 import spec as specmod  # noqa: E402
from src.reel_v2.spec import MAX_WORDS, MAX_WORDS_HI, SceneSpec, _prompt, _review_prompt, validate  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "src" / "reel_v2" / "examples" / "blue_green.json"
BRAND = {"handle": "@test", "hashtags": ["#dsa"]}


def english() -> SceneSpec:
    return SceneSpec.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))


def hinglish() -> SceneSpec:
    """The example with Hinglish narration (Devanagari + the English trigger word), on-screen text untouched."""
    s = english()
    for b in s.beats:
        b.narration = f"अब {b.trigger} करो।"
    return s


# --------------------------------------------------------------------------- #
# v2 prompt and checks
# --------------------------------------------------------------------------- #
def test_prompt_has_the_hinglish_block_only_for_hi():
    hi, en = _prompt("t", "SystemDesign", "", BRAND, language="hi"), _prompt("t", "SystemDesign", "", BRAND)
    assert "NARRATION LANGUAGE: HINGLISH" in hi and "follow करो @test" in hi
    assert "HINGLISH" not in en
    assert f"MAX {MAX_WORDS_HI} words" in hi and f"MAX {MAX_WORDS} words" in en


def test_review_prompt_mentions_hinglish_only_for_hi():
    assert "Hinglish" in _review_prompt(hinglish(), "hi") and "Hinglish" not in _review_prompt(english())


def test_hinglish_spec_is_valid():
    assert validate(hinglish(), "hi") == []


def test_hinglish_word_cap_is_lower():
    s = hinglish()
    s.beats[1].narration = "अब live " + "और " * 42      # 44 + 7 other beats x 3 = 65 words: over 60, under 75
    assert sum(len(b.narration.split()) for b in s.beats) == 65 > MAX_WORDS_HI
    assert any("30 seconds" in p for p in validate(s, "hi"))
    assert not any("30 seconds" in p for p in validate(s, "en"))      # under the English cap of 75


def test_trigger_with_danda_matches():
    s = hinglish()
    s.beats[2].trigger = "करो।"
    assert validate(s, "hi") == []


def test_hinglish_in_latin_script_is_rejected():
    s = hinglish()
    s.beats[3].narration = "ab Test karo"
    assert any("beat 4" in p and "Devanagari" in p for p in validate(s, "hi"))


def test_devanagari_on_screen_is_rejected():
    s = hinglish()
    s.beats[0].heading = "शिप करो"
    s.cheat.use_when[0] = "जब deploy हो"
    [p] = [p for p in validate(s, "hi") if "on-screen" in p]
    assert "शिप करो" in p


def test_english_spec_has_no_language_checks():
    assert validate(english()) == []          # English narration has no Devanagari, and that is fine


def test_generate_passes_the_language_through(monkeypatch):
    prompts = []

    def fake(prompt, schema, **k):
        prompts.append(prompt)
        return hinglish() if schema is SceneSpec else specmod.Review(ok=True, issues=[])
    monkeypatch.setattr(specmod, "generate_json", fake)
    monkeypatch.setattr(specmod, "load_brand", lambda: BRAND)
    specmod.generate("Blue-Green", "SystemDesign", language="hi")
    assert "HINGLISH" in prompts[0] and "Hinglish" in prompts[1]


# --------------------------------------------------------------------------- #
# gen_content: both engines set Content.language; the classic one skips the hook scorer
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def file_mode(monkeypatch):
    """Brand and taste from brand/config.yaml (another test module may point DATABASE_URL at a test DB)."""
    from src import db
    monkeypatch.setattr(db, "enabled", lambda: False)


TOPIC = RankedTopic(category="SystemDesign", title="Blue-Green", angle="", source_url="", evergreen=True, why="t")


def test_v2_path_sets_language(monkeypatch):
    monkeypatch.setattr(specmod, "generate", lambda *a, **k: hinglish())
    monkeypatch.setattr("src.reel_v2.pipeline.load_brand", lambda: {"handle": "@t", "reel": {}})
    c = gen_content.generate(TOPIC, language="hi")
    assert c.language == "hi" and c._scene is not None


def test_classic_path_sets_language_and_skips_hook_scorer(monkeypatch):
    from src.reel_v2 import pipeline
    monkeypatch.setattr(pipeline, "uses_v2", lambda category: False)
    from tests.test_content_validation import content
    draft = content()
    prompts = []

    def fake(prompt, schema, **k):
        prompts.append(prompt)
        return draft if schema is gen_content.Content else gen_content.Review(ok=True, issues=[])
    monkeypatch.setattr(gen_content, "generate_json", fake)
    monkeypatch.setattr(gen_content, "pick_hook", lambda *a: pytest.fail("hook scorer ran on Hinglish"))
    c = gen_content.generate(TOPIC, language="hi")
    assert c.language == "hi" and "NARRATION LANGUAGE: HINGLISH" in prompts[0]
