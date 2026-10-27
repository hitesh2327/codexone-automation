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
    G = gen_content
    draft = G.Content(
        topic="T", category="SystemDesign", caption="c", hashtags=["#x"],
        reel=G.Reel(hook_on_screen="h", hook_narration="सोचो cache क्या है?",
                    points=[G.ReelPoint(on_screen=f"p{i}", narration="cache तेज़ है।") for i in range(3)],
                    cta_on_screen="c", cta_narration="follow करो।"),
        carousel=[G.Slide(type="title", heading="T", body="b"),
                  *[G.Slide(type="content", heading=f"H{i}", body="b") for i in range(4)],
                  G.Slide(type="cta", heading="C", body="b")])
    prompts = []

    def fake(prompt, schema, **k):
        prompts.append(prompt)
        return draft if schema is gen_content.Content else gen_content.Review(ok=True, issues=[])
    monkeypatch.setattr(gen_content, "generate_json", fake)
    monkeypatch.setattr(gen_content, "pick_hook", lambda *a: pytest.fail("hook scorer ran on Hinglish"))
    c = gen_content.generate(TOPIC, language="hi")
    assert c.language == "hi" and "NARRATION LANGUAGE: HINGLISH" in prompts[0]


# --------------------------------------------------------------------------- #
# Voices, subtitles and trigger timing
# --------------------------------------------------------------------------- #
from types import SimpleNamespace  # noqa: E402

from src import render_reel  # noqa: E402
from src.reel_v2 import render as v2render  # noqa: E402


def _queue(monkeypatch, items):
    from src import queue_store as q
    monkeypatch.setattr(q, "load", lambda *a, **k: items)


def test_hindi_voices_rotate_on_their_own(monkeypatch):
    monkeypatch.setattr(render_reel, "load_brand", lambda: {"voices": ["en-US-A", "en-US-B"],
                                                           "voices_hi": ["hi-IN-X", "hi-IN-Y"]})
    reel = lambda lang: SimpleNamespace(kind="reel", voice="v", language=lang)  # noqa: E731
    _queue(monkeypatch, [reel("en"), reel("en"), reel("en"), reel("hi")])
    assert render_reel.pick_voice("hi") == "hi-IN-Y"      # 1 Hinglish reel so far
    assert render_reel.pick_voice("en") == "en-US-B"      # 3 English reels so far
    assert render_reel.pick_voice() == "en-US-B"


def test_hindi_voices_default_when_the_brand_has_none(monkeypatch):
    monkeypatch.setattr(render_reel, "load_brand", lambda: {"voices": ["en-US-A"]})   # an older DB brand
    _queue(monkeypatch, [])
    assert render_reel.pick_voice("hi") == render_reel.DEFAULT_VOICES_HI[0]


def test_feedback_voice_stays_in_the_posts_language(monkeypatch):
    monkeypatch.setattr(render_reel, "load_brand", lambda: {"voices": ["en-US-AndrewMultilingualNeural"]})
    assert render_reel.voice_from_feedback("use Swara please", "hi") == "hi-IN-SwaraNeural"
    assert render_reel.voice_from_feedback("use Swara please", "en") is None
    assert render_reel.voice_from_feedback("try Andrew", "en") == "en-US-AndrewMultilingualNeural"


def _fake_tts(with_words: bool):
    import subprocess

    import imageio_ffmpeg

    async def tts(text, voice, rate, out):
        words = text.split()
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "anullsrc=r=24000:cl=mono", "-t", f"{0.4 * len(words):.2f}", "-q:a", "9", str(out)], check=True)
        return [render_reel.Word(w, 0.4 * i, 0.4 * i + 0.35) for i, w in enumerate(words)] if with_words else []
    return tts


@pytest.mark.parametrize("with_words", [True, False])
def test_hinglish_timeline_has_no_subtitles_and_ordered_triggers(monkeypatch, tmp_path, with_words):
    monkeypatch.setattr(v2render, "_tts", _fake_tts(with_words))
    monkeypatch.setattr(v2render, "load_brand", lambda: {"handle": "@t", "pronunciations": {}})
    monkeypatch.setattr(render_reel, "load_brand", lambda: {"pronunciations": {}})
    tl, _ = v2render.timeline(hinglish(), "hi-IN-MadhurNeural", tmp_path, "hi")
    assert tl["subs"] == [[] for _ in hinglish().beats]
    # each narration is "अब <trigger> करो।": the trigger is word 2 of 3, ~0.4 s into its beat either way
    for start, trig in zip(tl["starts"], tl["triggers"]):
        assert start < trig < start + 1.2


def test_english_timeline_still_needs_word_boundaries(monkeypatch, tmp_path):
    monkeypatch.setattr(v2render, "_tts", _fake_tts(False))
    monkeypatch.setattr(render_reel, "load_brand", lambda: {"pronunciations": {}})
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="no word boundaries"):
        v2render.timeline(english(), "en-US-AndrewMultilingualNeural", tmp_path, "en")


def test_english_timeline_keeps_subtitles(monkeypatch, tmp_path):
    monkeypatch.setattr(v2render, "_tts", _fake_tts(True))
    monkeypatch.setattr(v2render, "load_brand", lambda: {"handle": "@t", "pronunciations": {}})
    monkeypatch.setattr(render_reel, "load_brand", lambda: {"pronunciations": {}})
    tl, _ = v2render.timeline(english(), "en-US-AndrewMultilingualNeural", tmp_path, "en")
    assert all(tl["subs"])


def test_youtube_audio_language(monkeypatch):
    from src import publish_youtube as yt
    monkeypatch.setattr(yt, "load_brand", lambda: {"cta": ""})
    hi = yt.build_metadata("Caching explained\n\n#ai", audio_language="hi")["snippet"]
    en = yt.build_metadata("Caching explained\n\n#ai")["snippet"]
    assert (hi["defaultAudioLanguage"], hi["defaultLanguage"]) == ("hi", "en")
    assert en["defaultAudioLanguage"] == "en"
