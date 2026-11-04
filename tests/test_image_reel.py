"""Image reel: a post's second item can be the cheat-sheet slide as a short video with music (posted as a
Reel) instead of the carousel. Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import approve_bot, image_reel, publish  # noqa: E402
from src import queue_store as q  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = shutil.which("ffmpeg") is not None


def brand(monkeypatch, **cfg):
    monkeypatch.setattr(image_reel, "load_brand", lambda: cfg)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value,expected", [("image_reel", "image_reel"), ("IMAGE_REEL", "image_reel"),
                                            ("carousel", "carousel"), (None, "carousel"), ("photo", "carousel")])
def test_default_format_reads_brand_post_format(monkeypatch, value, expected):
    brand(monkeypatch, post_format=value)
    assert image_reel.default_format() == expected


def test_brand_config_ships_with_the_carousel_default():
    import yaml
    cfg = yaml.safe_load((ROOT / "brand" / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["post_format"] == "carousel" and cfg["image_reel"]["duration_sec"] > 0
    assert all((ROOT / "brand" / "music" / f"{m}.mp3").exists() for m in cfg["image_reel"]["mood"].values())


# --------------------------------------------------------------------------- #
# Music
# --------------------------------------------------------------------------- #
def test_music_follows_the_category_mood(monkeypatch):
    brand(monkeypatch, image_reel={"music": "brand/music", "mood": {"DSA": "calm", "AI": "focus"}})
    assert image_reel.pick_music("DSA", "x").name == "calm.mp3"
    assert image_reel.pick_music("AI", "x").name == "focus.mp3"


def test_music_without_a_mood_is_stable_per_post(monkeypatch, tmp_path):
    for n in ("a", "b", "c"):
        (tmp_path / f"{n}.mp3").write_bytes(b"x")
    brand(monkeypatch, image_reel={"music": str(tmp_path), "mood": {"DSA": "missing"}})
    first = image_reel.pick_music("DSA", "binary-search")
    assert first == image_reel.pick_music("DSA", "binary-search")   # same post, same track on re-render
    assert {image_reel.pick_music("OS", k).name for k in map(str, range(30))} == {"a.mp3", "b.mp3", "c.mp3"}


def test_no_tracks_means_no_music(monkeypatch, tmp_path):
    brand(monkeypatch, image_reel={"music": str(tmp_path)})
    assert image_reel.pick_music("DSA", "x") is None


def test_cheat_slide_is_the_last_slide(tmp_path):
    for i in (1, 2, 10):
        (tmp_path / f"slide_{i:02d}.png").write_bytes(b"x")
    assert image_reel.cheat_slide(tmp_path).name == "slide_10.png"
    with pytest.raises(FileNotFoundError):
        image_reel.cheat_slide(tmp_path / "none")


# --------------------------------------------------------------------------- #
# Rendering (needs ffmpeg)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
@pytest.mark.parametrize("music", [True, False])
def test_render_makes_a_vertical_reel_with_audio(tmp_path, music):
    slide = tmp_path / "slide.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x101827:s=1080x1350",
                    "-frames:v", "1", str(slide)], check=True)
    track = ROOT / "brand" / "music" / "calm.mp3" if music else None
    out = image_reel.render(slide, tmp_path, track, seconds=3)
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration",
         "-of", "json", str(out)], capture_output=True, text=True, check=True).stdout)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a = next(s for s in probe["streams"] if s["codec_type"] == "audio")   # silent track without music
    assert (v["codec_name"], v["width"], v["height"], a["codec_name"]) == ("h264", 1080, 1920, "aac")
    assert abs(float(probe["format"]["duration"]) - 3) < 0.2
    assert (tmp_path / image_reel.COVER).exists()


def test_dry_run_renders_nothing(tmp_path):
    assert image_reel.render(tmp_path / "slide.png", tmp_path, None, 3, dry_run=True) is None
    assert not (tmp_path / image_reel.VIDEO).exists()


# --------------------------------------------------------------------------- #
# Queue items, preview and publishing
# --------------------------------------------------------------------------- #
def test_item_video_is_the_kinds_video():
    base = dict(date="2026-11-03", topic="t", category="DSA", post_dir="output/2026-11-03/t", caption="c")
    assert q.Item(id="r", kind="reel", media={"reel": "R"}, **base).video == "R"
    assert q.Item(id="i", kind="image", media={"image_reel": "I"}, **base).video == "I"
    assert q.Item(id="c", kind="carousel", media={"carousel": ["C"]}, **base).video is None


def test_image_reel_targets_instagram_only():
    item = q.Item(id="i", kind="image", date="2026-11-03", topic="t", category="DSA",
                  post_dir="output/2026-11-03/t", caption="c", targets=["ig", "yt"])
    assert item.effective_targets == ["ig"]


def test_control_text_names_the_image_reel():
    item = q.Item(id="20261103-i-abc123", kind="image", date="2026-11-03", topic="Topological Sort",
                  category="DSA", post_dir="output/2026-11-03/t", caption="Caption #dsa",
                  publish_at="2026-11-03T19:00:00+05:30")
    text = approve_bot._control_text(item)
    assert "IMAGE REEL" in text and len(text) <= 1024      # sent as a video caption


def test_instagram_publishes_an_image_reel_as_a_reel(monkeypatch):
    calls = []
    monkeypatch.setattr(publish, "publish_reel", lambda url, cap: calls.append(("reel", url)) or "m1")
    monkeypatch.setattr(publish, "publish_carousel", lambda urls, cap: calls.append(("carousel", urls)) or "m2")
    monkeypatch.setattr(publish, "_call", lambda *a, **k: {"permalink": "https://instagram.com/reel/x"})
    item = q.Item(id="i", kind="image", date="2026-11-03", topic="t", category="DSA",
                  post_dir="output/2026-11-03/t", caption="c", media={"image_reel": "https://res.cloudinary.com/v.mp4"})
    rec = publish._publish_ig(item)
    assert calls == [("reel", "https://res.cloudinary.com/v.mp4")] and rec["status"] == "published"


def test_items_from_post_makes_an_image_item_and_no_carousel(tmp_path, monkeypatch):
    from types import SimpleNamespace
    content = SimpleNamespace(topic="Topological Sort", category="DSA", caption="Caption", hashtags=["#dsa"],
                              language="en")
    monkeypatch.setattr(approve_bot.Content, "model_validate_json", classmethod(lambda cls, s: content))
    post = tmp_path / "output" / "2026-11-03" / "topo"
    post.mkdir(parents=True)
    (post / "content.json").write_text("{}", encoding="utf-8")
    (post / "media.json").write_text(json.dumps({"reel": "R", "cover": "C", "image_reel": "I", "image_cover": "IC"}),
                                     encoding="utf-8")
    monkeypatch.setattr(approve_bot, "ROOT", tmp_path)
    items = approve_bot.items_from_post(post)
    assert sorted(i.kind for i in items) == ["image", "reel"]            # the image reel replaces the carousel
    image = next(i for i in items if i.kind == "image")
    assert image.media == {"image_reel": "I", "image_cover": "IC"} and image.id.split("-")[1] == "i"
    assert image.voice == "" and image.effective_targets == ["ig"]


def test_yaml_post_format_wins_over_the_db_brand_copy(monkeypatch):
    """4 Nov: the DB brand copy (saved before image reels) has no post_format, and load_brand() returned it
    whole, so brand/config.yaml's post_format was ignored and every run made a carousel."""
    import yaml
    from src import config, db
    stale = {"handle": "@t", "voices": ["en-US-Old"]}
    monkeypatch.setattr(db, "enabled", lambda: True)
    monkeypatch.setattr(db, "get_setting", lambda key: dict(stale))
    yml = yaml.safe_load(config.BRAND_FILE.read_text(encoding="utf-8"))
    monkeypatch.setattr(config.yaml, "safe_load", lambda f: {**yml, "post_format": "image_reel"})
    config.load_brand.cache_clear()
    monkeypatch.setattr(image_reel, "load_brand", config.load_brand)
    try:
        b = config.load_brand()
        assert b["post_format"] == "image_reel" and b["image_reel"] == yml["image_reel"]
        assert image_reel.default_format() == "image_reel"
    finally:
        config.load_brand.cache_clear()
