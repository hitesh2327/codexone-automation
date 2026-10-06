"""Prototype: Blue-Green Deployment reel in the "one persistent animated diagram" style.

Voiceover per beat (edge-tts) drives the timeline; visual events are pinned to spoken
words (e.g. the router flips on "flip"). bluegreen.html draws any instant via
renderAt(t); Playwright captures each frame and ffmpeg muxes it with the voice.

Usage (from repo root):
    .venv/Scripts/python -m prototypes.reel_v2.bluegreen [--voice en-US-AndrewMultilingualNeural] [--preview 12.5]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
from moviepy import AudioFileClip, CompositeAudioClip
from playwright.sync_api import sync_playwright

from prototypes.reel_v2._browser import launch
from src.render_reel import _tts, speakable

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
W, H, FPS = 1080, 1920, 30
GAP = 0.3     # silence between beats (s)
TAIL = 1.4    # hold on the payoff after the last word (s)

BLUE, GREEN, AMBER, RED, CYAN = "#7DB3FF", "#7CF0A6", "#FFB800", "#FF4D5E", "#00E5FF"

# heading/color/term/caption are on screen; narration is spoken.
BEATS = [
    dict(heading="ZERO-DOWNTIME DEPLOYS", color=CYAN, term="watch traffic --app shop",
         caption="Ship v2 <em>without</em> taking the app down",
         narration="How do big apps ship new code without ever going down? Blue-green deployment."),
    dict(heading="● LIVE ON BLUE", color=BLUE, term="router status   → blue (v1.0)",
         caption="Blue = <em>live</em>. Every request lands here",
         narration="Blue is your live environment, running version one. Every request lands here."),
    dict(heading="DEPLOY v2 → GREEN", color=AMBER, term="deploy v2.0 --env green",
         caption="Green = an <em>identical copy</em> running v2",
         narration="Next to it, you build Green, an identical copy running version two."),
    dict(heading="TEST GREEN", color=AMBER, term="smoke-test green   ✓ 42 passed",
         caption="Test Green. Users <em>never touch it</em>",
         narration="You test Green fully, while real users never touch it."),
    dict(heading="FLIP THE SWITCH", color=GREEN, term="router switch → green",
         caption="<em>One switch</em> → all traffic on Green",
         narration="Then you flip the router, and all traffic moves to Green in one switch."),
    dict(heading="BUG? ROLL BACK", color=RED, term="router switch → blue   # rollback",
         caption="Bug? Flip back. <em>Blue never stopped</em>",
         narration="Found a bug? Just flip it back. Blue is still running, so rollback takes seconds."),
    dict(heading="DOWNTIME: 0s", color=GREEN, term="uptime   100%",
         caption="Zero downtime · <em>instant</em> rollback",
         narration="Zero downtime, instant rollback. Follow codexonebyhitesh for more system design."),
]

# visual event -> (beat index, spoken word it fires on, delay after that word)
EVENTS = {
    "boot": (2, "build", 0.0),
    "test": (3, "test", 0.0),
    "switch": (4, "flip", 0.1),
    "bug": (5, "bug", 0.0),
    "rollback": (5, "back", 0.0),
    "payoff": (6, None, 0.0),
}


def synth(voice: str) -> tuple[dict, Path]:
    OUT.mkdir(exist_ok=True)
    t, clips, beats = 0.0, [], []
    words_by_beat = []
    for i, b in enumerate(BEATS):
        mp3 = OUT / f"beat_{i}.mp3"
        for attempt in range(5):
            try:
                words = asyncio.run(_tts(speakable(b["narration"]), voice, mp3))
                break
            except Exception as e:  # noqa: BLE001 - edge-tts network hiccups
                print(f"tts retry {attempt + 1}: {e}")
        else:
            raise RuntimeError(f"tts failed for beat {i}")
        clip = AudioFileClip(str(mp3))
        clips.append(clip.with_start(t))
        beats.append({k: b[k] for k in ("heading", "color", "term", "caption")} | {"start": t})
        words_by_beat.append([(w.text, t + w.start) for w in words])
        t += clip.duration + GAP
    total = t - GAP + TAIL

    ev = {}
    for name, (bi, word, delay) in EVENTS.items():
        if word is None:
            ev[name] = beats[bi]["start"]
            continue
        hit = next((s for w, s in words_by_beat[bi] if w.lower().strip(".,?!").startswith(word)), None)
        if hit is None:
            raise ValueError(f"event {name}: word {word!r} not spoken in beat {bi}")
        ev[name] = hit + delay

    audio = OUT / "voice.m4a"
    CompositeAudioClip(clips).with_duration(total).write_audiofile(
        str(audio), fps=44100, codec="aac", logger=None)
    return {"total": round(total, 3), "beats": beats, "ev": ev}, audio


def capture(tl: dict, audio: Path, out: Path, preview: float | None) -> None:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto((HERE / "bluegreen.html").as_uri())
        page.evaluate("document.fonts.ready")
        page.evaluate("tl => setTimeline(tl)", tl)
        if preview is not None:
            page.evaluate("t => renderAt(t)", preview)
            page.screenshot(path=str(OUT / f"preview_{preview:.1f}.png"))
            browser.close()
            return
        n = int(tl["total"] * FPS)
        proc = subprocess.Popen(
            [ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
             "-i", str(audio), "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p", "-color_range", "tv", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", str(out)],
            stdin=subprocess.PIPE)
        for f in range(n):
            page.evaluate("t => renderAt(t)", f / FPS)
            proc.stdin.write(page.screenshot(type="jpeg", quality=92))
            if f % 150 == 0:
                print(f"frame {f}/{n}")
        proc.stdin.close()
        proc.wait()
        browser.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="en-US-AndrewMultilingualNeural")
    ap.add_argument("--preview", type=float, help="only screenshot this time (s)")
    args = ap.parse_args()
    tl_file = OUT / "timeline.json"
    if args.preview is not None and tl_file.exists():
        tl, audio = json.loads(tl_file.read_text(encoding="utf-8")), OUT / "voice.m4a"
    else:
        tl, audio = synth(args.voice)
        tl_file.write_text(json.dumps(tl, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"total {tl['total']:.1f}s  events {tl['ev']}")
    capture(tl, audio, OUT / "blue_green_reel.mp4", args.preview)


if __name__ == "__main__":
    main()
