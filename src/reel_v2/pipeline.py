"""Glue between the v2 scene engine and the classic pipeline.

The classic flow (main.py) calls gen_content.generate -> render_post.render_carousel ->
render_reel.render_reel. For every category not listed in brand `reel.classic_categories`, generate() writes
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


def uses_v2(category: str) -> bool:
    """v2 is opt-out: a category keeps the classic format only when listed in reel.classic_categories.

    The old opt-in key `reel.v2_categories` is ignored on purpose: the production brand is a
    one-time DB copy of brand/config.yaml, so a stale list there silently kept DSA and
    Interview on the classic format.
    """
    return category not in (load_brand().get("reel", {}).get("classic_categories") or [])


def warn_fallback(what: str, topic: str, err: BaseException | None = None) -> None:
    """Say on Telegram that a post fell back to the classic design (it was only in the logs)."""
    detail = f": {type(err).__name__}: {str(err)[:200]}" if err else ""
    try:
        from src.approve_bot import notify
        notify(f"⚠️ {what} for “{topic}” fell back to the classic design{detail}")
    except Exception:  # noqa: BLE001 -- the warning must never cost the post
        log.exception("could not send the fallback warning")


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
