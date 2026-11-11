"""Unit tests for T-13 viral Reels + YouTube Shorts growth upgrades."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import gen_content  # noqa: E402
from src import publish_youtube as yt  # noqa: E402
from src import rank_topics  # noqa: E402
from src import render_reel  # noqa: E402
from src.gen_content import Content, Reel, ReelPoint, Slide  # noqa: E402
from src.reel_v2.spec import SceneSpec, validate  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "src" / "reel_v2" / "examples" / "blue_green.json"


@pytest.fixture(autouse=True)
def file_mode(monkeypatch):
    from src import db
    monkeypatch.setattr(db, "enabled", lambda: False)


def _sample_content(**reel_kw) -> Content:
    reel = Reel(
        hook_on_screen="STOP *DOING THIS*",
        hook_narration="Hey guys, in this video we look at Blue-Green deploys.",
        hook_alternatives=[
            "Stop taking production down on deploys. Do this 1-switch swap.",
            "Here is Blue-Green deployment.",
        ],
        points=[ReelPoint(on_screen="*POINT 1*", narration="Point one.")],
        cta_on_screen="SAVE *THIS*",
        cta_narration="Which keeps zero downtime when you...",
        **reel_kw,
    )
    return Content(
        topic="Blue-Green Deployment",
        category="SystemDesign",
        reel=reel,
        carousel=[Slide(type="title", heading="*Blue-Green*"), Slide(type="cta", heading="*Save*")],
        caption="🔥 Blue-green deployment stops downtime during releases.\n\nHave you used this in production?",
        hashtags=["#systemdesign", "#devops", "#fyp", "#viral", "#kubernetes", "#backend", "#extra"],
    )


# --------------------------------------------------------------------------- #
# YouTube Shorts metadata + privacy warning
# --------------------------------------------------------------------------- #
def test_youtube_title_stays_under_60_chars_and_skips_ig_cta():
    long_caption = "Comment 'SCALE' to get the full cheat sheet in your DMs.\n\nBlue-green deployment eliminates release downtime."
    title = yt.make_title(long_caption, topic="Blue-Green Deployment")
    assert len(title) <= yt.SHORTS_TITLE_TARGET
    assert title.endswith("#Shorts")
    assert "comment" not in title.lower() and "dms" not in title.lower()


def test_youtube_category_id_splits_education_and_science_tech():
    assert yt.category_id_for("DSA") == yt.CATEGORY_EDUCATION
    assert yt.category_id_for("Interview") == yt.CATEGORY_EDUCATION
    assert yt.category_id_for("OS") == yt.CATEGORY_EDUCATION
    assert yt.category_id_for("SystemDesign") == yt.CATEGORY_SCIENCE_TECH
    assert yt.category_id_for("AI") == yt.CATEGORY_SCIENCE_TECH


def test_youtube_description_strips_ig_dm_bait_and_adds_shorts_seo(monkeypatch):
    monkeypatch.setattr(yt, "load_brand", lambda: {"cta": "Comment 'SCALE' in your DMs"})
    caption = (
        "Blue-green deployment keeps zero downtime.\n\n"
        "Comment 'SCALE' and I will DM you the cheat sheet.\n\n"
        "#systemdesign #fyp #devops"
    )
    meta = yt.build_metadata(caption, category="SystemDesign", topic="Blue-Green Deployment")
    desc = meta["snippet"]["description"]
    assert "in your dms" not in desc.lower() and "dm you" not in desc.lower()
    assert "#Shorts" in desc and "Subscribe" in desc
    assert "#fyp" not in desc.lower()
    tags = meta["snippet"]["tags"]
    assert "Shorts" in tags and "YouTube Shorts" in tags and "system design" in tags
    assert "fyp" not in [t.lower() for t in tags]


def test_youtube_warns_explicitly_when_privacy_is_private(monkeypatch, caplog):
    monkeypatch.delenv("YT_PRIVACY", raising=False)
    monkeypatch.setattr(yt, "credentials", lambda: None)
    monkeypatch.setattr(yt, "load_brand", lambda: {"cta": ""})
    with caplog.at_level(logging.WARNING, logger="codexone.publish_youtube"):
        yt.publish_reel("local.mp4", "Caching explained\n\n#systemdesign", dry_run=True)
    assert any("YT_PRIVACY=private" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# gen_content viral hook & IG SEO caption enforcement
# --------------------------------------------------------------------------- #
def test_post_process_strips_preamble_promotes_strong_hook_and_syncs_scene(monkeypatch, tmp_path):
    from src import post_log
    monkeypatch.setattr(post_log, "LOG_FILE", tmp_path / "post_log.jsonl")
    spec = SceneSpec.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    c = _sample_content()
    c._scene = spec
    out = gen_content._post_process(c)
    assert out.reel.hook_narration.startswith("Stop taking production down")
    assert out._scene.beats[0].narration == out.reel.hook_narration
    assert validate(out._scene) == []


def test_post_process_enforces_clean_ig_caption_and_hashtag_cap(monkeypatch, tmp_path):
    from src import post_log
    monkeypatch.setattr(post_log, "LOG_FILE", tmp_path / "post_log.jsonl")
    c = _sample_content()
    out = gen_content._post_process(c)
    assert not out.caption.startswith("🔥")
    assert "Save this Blue-Green Deployment" in out.caption
    assert "Have you used this" not in out.caption
    assert len(out.hashtags) <= 5
    assert "#fyp" not in out.hashtags and "#viral" not in out.hashtags


def test_gen_content_youtube_metadata_helper(monkeypatch):
    monkeypatch.delenv("YT_PRIVACY", raising=False)
    c = _sample_content()
    meta = gen_content.youtube_metadata(c)
    assert len(meta["snippet"]["title"]) <= yt.SHORTS_TITLE_TARGET
    assert meta["snippet"]["categoryId"] == yt.CATEGORY_SCIENCE_TECH


# --------------------------------------------------------------------------- #
# render_reel & rank_topics growth alignment
# --------------------------------------------------------------------------- #
def test_render_reel_cta_and_loop_pacing():
    scene = render_reel.Scene("cta", "SAVE *THIS*", [render_reel.Part("Done.")])
    html = render_reel.scene_html(scene, "@codexonebyhitesh")
    assert "FOLLOW FOR MORE" not in html and "SAVE &amp; SHARE" in html
    assert render_reel.TAIL <= 0.3 and render_reel.GAP <= 0.25


def test_rank_topics_prompt_prioritizes_curiosity_and_saves(monkeypatch, tmp_path):
    monkeypatch.setattr(rank_topics, "DATA_DIR", tmp_path)
    (tmp_path / "topics_2026-11-11.json").write_text(
        '[{"category":"SystemDesign","title":"Why Redis Eviction Breaks","source":"hn","norm_score":0.9,"url":"https://x.test","summary":"OOM"}]',
        encoding="utf-8",
    )
    from types import SimpleNamespace
    from src import user_taste
    monkeypatch.setattr(user_taste, "get_user_taste", lambda: SimpleNamespace(
        niche="tech", target_audience="devs", categories=["SystemDesign"]
    ))
    monkeypatch.setattr(rank_topics, "load_brand", lambda: {"handle": "@t", "language": "English", "topics_weight": {"SystemDesign": 1}})


    monkeypatch.setattr(rank_topics, "recent_titles", lambda: [])
    seen = {}

    def fake_gen(prompt, schema, **k):
        seen["prompt"] = prompt
        return rank_topics.RankedTopic(
            category="SystemDesign", title="Why Redis Eviction Breaks",
            angle="Wrong eviction policy silently drops session keys.", source_url="https://x.test",
            evergreen=False, why="High-stakes prod bug",
        )
    monkeypatch.setattr(rank_topics, "generate_json", fake_gen)
    res = rank_topics.rank("2026-11-11", category="SystemDesign")
    assert res.title == "Why Redis Eviction Breaks"
    assert "curiosity gap" in seen["prompt"] and "saves" in seen["prompt"]
