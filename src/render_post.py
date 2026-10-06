"""Render carousel slides (title / content+code / CTA) to PNG.

Output: output/<date>/<slug>/carousel/slide_01.png ...

Usage:
    python -m src.render_post output/2026-09-27/<slug>/content.json [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.gen_content import Content, Slide
from src.html_render import (body_html, brand_context, browser_page, code_html,
                             highlight_heading, inline, render_to_png)
from src.config import load_brand
from src.logger import get_logger

log = get_logger("render_post")

TEMPLATES = {"title": "title.html", "content": "content.html", "visual": "visual.html", "cta": "cta.html"}


def _size() -> tuple[int, int]:
    w, h = load_brand()["carousel"]["size"].lower().split("x")
    return int(w), int(h)


def slide_context(slide: Slide, index: int, total: int, demo: dict | None = None) -> dict:
    w, h = _size()
    return {
        **brand_context(),
        "width": w, "height": h, "index": index, "total": total, "demo": demo,
        "slide": {
            **slide.model_dump(),
            "heading_html": highlight_heading(slide.heading) if slide.type in ("title", "cta") else inline(slide.heading),
            "body_inline": inline(slide.body.replace("\n", " ")),
            "body_html": body_html(slide.body),
            "code_html": code_html(slide.code, slide.code_language) if slide.code else "",
        },
    }


def render_carousel(content: Content, out_dir: Path, dry_run: bool = False) -> list[Path]:
    from src.reel_v2 import pipeline as v2
    if (spec := v2.scene_of(content, out_dir.parent)) is not None:
        if dry_run:
            log.info("[dry-run] v2 carousel: cover + %d beats + cheat sheet",
                     sum(b.on_carousel for b in spec.beats))
            return []
        from src.reel_v2.render import render_carousel as render_v2
        v2.save_scene(spec, out_dir.parent)
        try:
            return render_v2(spec, out_dir, content.category)
        except Exception:  # the classic slides mirror the same story
            log.exception("v2 carousel render failed; rendering the classic slides instead")
    slides = content.carousel
    if dry_run:
        for i, s in enumerate(slides, 1):
            log.info("[dry-run] slide %d/%d %-7s %s", i, len(slides), s.type, s.heading)
        return []
    w, h = _size()
    paths = []
    with browser_page(w, h) as page:
        for i, s in enumerate(slides, 1):
            out = out_dir / f"slide_{i:02d}.png"
            demo = content.demo.model_dump() if content.demo else None
            render_to_png(page, TEMPLATES[s.type], slide_context(s, i, len(slides), demo), out)
            log.info("rendered %s", out.name)
            paths.append(out)
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render carousel PNGs from content.json")
    ap.add_argument("content_json", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="list slides; render nothing")
    args = ap.parse_args(argv)
    content = Content.model_validate_json(args.content_json.read_text(encoding="utf-8"))
    paths = render_carousel(content, args.content_json.parent / "carousel", args.dry_run)
    if paths:
        log.info("carousel: %d slides → %s", len(paths), paths[0].parent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
