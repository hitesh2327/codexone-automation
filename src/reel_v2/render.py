"""Render a v2 scene spec to a reel (MP4) and a carousel (PNGs).

Each beat is voiced separately (edge-tts); the diagram changes exactly when the beat's trigger
word is spoken. Reels are capped at MAX_SECONDS: if the voice runs long it is re-synthesized
faster, and the render fails rather than ship an over-length reel.

Output: <out>/reel.mp4, <out>/reel_cover.jpg, <out>/carousel/slide_01.png ...

Usage:
    python -m src.reel_v2.render spec.json --out output/<date>/<slug> [--category SystemDesign]
        [--voice en-US-AndrewMultilingualNeural] [--carousel-only | --reel-only] [--preview 12.5]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
import sys
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from moviepy import AudioFileClip, CompositeAudioClip
from playwright.sync_api import sync_playwright

from src.config import TEMPLATES_DIR, load_brand
from src.logger import get_logger
from src.render_reel import Word, pick_voice, speakable
from src.reel_v2.spec import SceneSpec

log = get_logger("reel_v2.render")

TPL = TEMPLATES_DIR / "reel_v2"
W, H, FPS = 1080, 1920, 30
GAP, TAIL = 0.3, 1.4
MAX_SECONDS = 30.0
BASE_RATE, MAX_RATE = 6, 30   # edge-tts speed-up in percent


def launch(p):
    """Playwright's Chromium, or the system Edge if Playwright's browsers are missing."""
    try:
        return p.chromium.launch()
    except Exception as e:  # noqa: BLE001
        log.warning("bundled Chromium unavailable (%s); using Microsoft Edge", str(e).splitlines()[0])
        return p.chromium.launch(channel="msedge")


async def _tts(text: str, voice: str, rate: int, out: Path) -> list[Word]:
    comm = edge_tts.Communicate(text, voice, rate=f"+{rate}%", boundary="WordBoundary")
    words: list[Word] = []
    with out.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append(Word(chunk["text"], s, s + chunk["duration"] / 1e7))
    return words


def _voice_beats(spec: SceneSpec, voice: str, rate: int, work: Path) -> tuple[list[Path], list[list[Word]], list[float]]:
    files, words, durs = [], [], []
    for i, b in enumerate(spec.beats):
        mp3 = work / f"beat_{i}.mp3"
        for attempt in range(1, 6):
            try:
                ws = asyncio.run(_tts(speakable(b.narration), voice, rate, mp3))
                with AudioFileClip(str(mp3)) as a:
                    d = a.duration
                if not ws:
                    raise RuntimeError("no word boundaries")
                break
            except Exception as e:  # noqa: BLE001 - edge-tts network errors
                log.warning("tts beat %d attempt %d: %s", i, attempt, e)
                if attempt == 5:
                    raise
        files.append(mp3); words.append(ws); durs.append(d)
    return files, words, durs


def timeline(spec: SceneSpec, voice: str, work: Path) -> tuple[dict, Path]:
    """Voice every beat, fit the reel under MAX_SECONDS, and pin triggers to spoken words."""
    rate = BASE_RATE
    while True:
        files, words, durs = _voice_beats(spec, voice, rate, work)
        total = sum(durs) + GAP * (len(durs) - 1) + TAIL
        if total <= MAX_SECONDS:
            break
        if rate >= MAX_RATE:
            raise ValueError(f"reel is {total:.1f}s even at +{rate}% speed; shorten the narration")
        need = (sum(durs) / (MAX_SECONDS - GAP * (len(durs) - 1) - TAIL - .3)) * (100 + rate) - 100
        rate = min(MAX_RATE, max(rate + 3, math.ceil(need)))
        log.info("voice is %.1fs (> %.0fs); re-synthesizing at +%d%%", total, MAX_SECONDS, rate)

    starts, t = [], 0.0
    for d in durs:
        starts.append(t)
        t += d + GAP
    triggers = []
    for i, (b, ws) in enumerate(zip(spec.beats, words)):
        target = b.trigger.lower().strip(".,?!'\"")
        hit = next((w.start for w in ws if w.text.lower().strip(".,?!'\"") == target), None)
        if hit is None:
            hit = next((w.start for w in ws if w.text.lower().strip(".,?!'\"").startswith(target[:4])), 0.0)
            log.warning("beat %d: trigger %r not matched exactly; using %.2fs", i, b.trigger, hit)
        triggers.append(starts[i] + hit)

    audio = work / "voice.m4a"
    clips = [AudioFileClip(str(f)).with_start(s) for f, s in zip(files, starts)]
    CompositeAudioClip(clips).with_duration(total).write_audiofile(str(audio), fps=44100, codec="aac", logger=None)
    for c in clips:
        c.close()
    log.info("voice %s at +%d%%: %.1fs over %d beats", voice, rate, total, len(spec.beats))
    return {"spec": spec.model_dump(), "handle": load_brand()["handle"], "starts": starts,
            "triggers": triggers, "total": round(total, 3)}, audio


def render_reel(spec: SceneSpec, out_dir: Path, voice: str | None = None, preview: float | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "reel_work"
    work.mkdir(exist_ok=True)
    tl_file = work / "timeline.json"
    if preview is not None and tl_file.exists():
        tl, audio = json.loads(tl_file.read_text(encoding="utf-8")), work / "voice.m4a"
    else:
        tl, audio = timeline(spec, voice or pick_voice(), work)
        tl_file.write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
    out = out_dir / "reel.mp4"
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto((TPL / "reel.html").as_uri())
        page.evaluate("document.fonts.ready")
        page.evaluate("tl => setTimeline(tl)", tl)
        if preview is not None:
            page.evaluate("t => renderAt(t)", preview)
            shot = out_dir / f"preview_{preview:.1f}.png"
            page.screenshot(path=str(shot))
            browser.close()
            return shot
        # cover: the moment the story is solved (start of the payoff beat)
        page.evaluate("t => renderAt(t)", max(0.0, tl["starts"][-1] - 0.05))
        page.screenshot(path=str(out_dir / "reel_cover.jpg"), type="jpeg", quality=90)
        n = int(tl["total"] * FPS)
        proc = subprocess.Popen(
            [ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
             "-i", str(audio), "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p", "-color_range", "tv",
             "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "160k",
             "-movflags", "+faststart", "-shortest", str(out)],
            stdin=subprocess.PIPE)
        assert proc.stdin
        for f in range(n):
            page.evaluate("t => renderAt(t)", f / FPS)
            proc.stdin.write(page.screenshot(type="jpeg", quality=92))
            if f % 150 == 0:
                log.info("frame %d/%d", f, n)
        proc.stdin.close()
        if proc.wait():
            raise RuntimeError("ffmpeg failed")
        browser.close()
    log.info("reel %.1fs → %s (%.1f MB)", tl["total"], out, out.stat().st_size / 1e6)
    return out


def render_carousel(spec: SceneSpec, folder: Path, category: str = "") -> list[Path]:
    """Write slide_01.png ... into `folder` (the classic <post>/carousel)."""
    w, h = (int(x) for x in load_brand()["carousel"]["size"].lower().split("x"))
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        page.goto((TPL / "carousel.html").as_uri())
        page.evaluate("document.fonts.ready")
        n = page.evaluate("([s, h, c]) => build(s, h, c)", [spec.model_dump(), load_brand()["handle"], category])
        page.wait_for_timeout(200)
        for i, el in enumerate(page.query_selector_all(".slide"), 1):
            path = folder / f"slide_{i:02d}.png"
            el.screenshot(path=str(path))
            paths.append(path)
        browser.close()
    log.info("carousel: %d slides → %s", n, folder)
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render a v2 scene spec")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--category", default="")
    ap.add_argument("--voice")
    ap.add_argument("--preview", type=float, help="reel: only screenshot this time (s)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--carousel-only", action="store_true")
    g.add_argument("--reel-only", action="store_true")
    args = ap.parse_args(argv)
    spec = SceneSpec.model_validate_json(args.spec.read_text(encoding="utf-8"))
    if not args.reel_only and args.preview is None:
        render_carousel(spec, args.out / "carousel", args.category)
    if not args.carousel_only:
        render_reel(spec, args.out, args.voice, args.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
