"""Glue between the v2 scene engine and the classic pipeline.

The classic flow (main.py) calls gen_content.generate -> render_post.render_carousel ->
render_reel.render_reel. For categories listed in brand `reel.v2_categories`, generate() writes
a SceneSpec instead, wraps it in a classic `Content` (caption/hashtags/topic for approval and
publishing) and attaches the spec; the two renderers then hand off to src.reel_v2.render.
main.py needs no changes, and any v2 failure falls back to the classic generator.
"""
from __future__ import annotations

from pathlib import Path

from src.config import load_brand
from src.gen_content import Content, Reel, ReelPoint, Slide
from src.logger import get_logger
from src.reel_v2.spec import SceneSpec

log = get_logger("reel_v2.pipeline")
SCENE_FILE = "scene.json"
# Used when the brand has no reel.v2_categories (in production the brand lives in the DB
# `settings` table, so a new key there is not guaranteed). An empty list turns v2 off.
DEFAULT_CATEGORIES = ("SystemDesign", "AI", "OS", "Dev")


def uses_v2(category: str) -> bool:
    cats = load_brand().get("reel", {}).get("v2_categories")
    return category in (DEFAULT_CATEGORIES if cats is None else cats)


def _plain(text: str) -> str:
    return text.replace("*", "")


def to_content(spec: SceneSpec, title: str, category: str) -> Content:
    """A classic Content mirror of the spec (what approval, upload and publish read)."""
    b = spec.beats
    title_text = "".join(p.text for p in spec.title)
    slides = [Slide(type="title", kicker=category, heading=f"*{title_text}*", body=_plain(spec.cover_lead))]
    slides += [Slide(type="content", kicker=x.heading, heading=_plain(x.slide_title), body=_plain(x.slide_text))
               for x in b if x.on_carousel]
    slides.append(Slide(type="cta", heading="Save this for *later*", body=f"Follow {load_brand()['handle']}"))
    content = Content(
        topic=title, category=category, demo=None, carousel=slides,
        reel=Reel(hook_on_screen=b[0].heading, hook_narration=b[0].narration,
                  points=[ReelPoint(on_screen=x.heading, narration=x.narration) for x in b[1:-1]],
                  cta_on_screen=b[-1].heading, cta_narration=b[-1].narration),
        caption=spec.caption,
        hashtags=[h if h.startswith("#") else f"#{h}" for h in spec.hashtags][:15])
    content._scene = spec
    return content


def scene_of(content: Content, near: Path) -> SceneSpec | None:
    """The attached spec, else a scene.json saved next to the post (re-renders from disk)."""
    spec = getattr(content, "_scene", None)
    if spec is not None:
        return spec
    f = near / SCENE_FILE
    return SceneSpec.model_validate_json(f.read_text(encoding="utf-8")) if f.exists() else None


def save_scene(spec: SceneSpec, post_dir: Path) -> None:
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / SCENE_FILE).write_text(spec.model_dump_json(indent=1), encoding="utf-8")
