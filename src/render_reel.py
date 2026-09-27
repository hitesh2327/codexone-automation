"""Render a 1080x1920 reel: edge-tts voiceover + animated scenes + word-highlight subtitles.

Scenes: hook → point 1 → [demo walkthrough] → point 2 → point 3 → CTA.

Every narration part is synthesized separately, so visuals change exactly when the
voice moves on. The demo scene animates a data structure: one voiced part per step,
state changes crossfade, and pointer labels (i, j, slow, fast, …) glide between cells.
Subtitles come from edge-tts word boundaries (current word highlighted). Background
music is optional.

Output: output/<date>/<slug>/reel.mp4 (+ reel_cover.jpg)

Usage:
    python -m src.render_reel output/<date>/<slug>/content.json [--music path.mp3] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import html
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import edge_tts
import numpy as np
from moviepy import AudioFileClip, CompositeAudioClip, VideoClip, afx
from PIL import Image

from src.config import load_brand
from src.gen_content import Content
from src.html_render import brand_context, browser_page, emphasize, env
from src.logger import get_logger

log = get_logger("render_reel")

W, H, FPS = 1080, 1920, 30
GAP = 0.35          # silence between scenes (s)
PART_GAP = 0.25     # silence between demo steps (s)
TAIL = 0.8          # hold after last word (s)
MOVE = 0.45         # pointer glide duration (s)
HOP = 0.3           # per-node hop when a linked-list pointer follows its next links (s)
XFADE = 0.25        # crossfade between demo steps (s)
TTS_RATE = "+6%"
MUSIC_VOLUME = 0.12


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Part:
    narration: str
    audio: Path | None = None
    words: list[Word] = field(default_factory=list)
    duration: float = 0.0
    offset: float = 0.0       # start within its scene


@dataclass
class Scene:
    kind: str                 # hook | point | demo | cta
    on_screen: str
    parts: list[Part]
    index: int = 0
    start: float = 0.0

    @property
    def duration(self) -> float:
        last = self.parts[-1]
        return last.offset + last.duration


# --------------------------------------------------------------------------- #
# TTS
# --------------------------------------------------------------------------- #
async def _tts(text: str, voice: str, out: Path) -> list[Word]:
    comm = edge_tts.Communicate(text, voice, rate=TTS_RATE, boundary="WordBoundary")
    words: list[Word] = []
    with out.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append(Word(chunk["text"], start, start + chunk["duration"] / 1e7))
    return words


def synthesize(part: Part, voice: str, out: Path, label: str, retries: int = 3) -> None:
    for attempt in range(1, retries + 1):
        try:
            part.words = asyncio.run(_tts(part.narration, voice, out))
            part.audio = out
            with AudioFileClip(str(out)) as a:
                part.duration = a.duration
            if not part.words:
                raise RuntimeError("no word boundaries returned")
            return
        except Exception as e:  # edge-tts raises various network errors
            log.warning("TTS failed for %s (attempt %d/%d): %s", label, attempt, retries, e)
            time.sleep(2 * attempt)
    raise RuntimeError(f"edge-tts failed for '{label}' after {retries} attempts")


# --------------------------------------------------------------------------- #
# Subtitles
# --------------------------------------------------------------------------- #
def chunk_words(words: list[Word], max_words: int = 3, max_chars: int = 18) -> list[list[Word]]:
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        text_len = sum(len(x.text) + 1 for x in cur)
        if len(cur) >= max_words or text_len >= max_chars or re.search(r"[.,!?;:]$", w.text):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def caption_html(chunk: list[Word], active: int) -> str:
    return '<div class="cap">' + " ".join(
        f'<span class="{"on" if i == active else ""}">{html.escape(w.text)}</span>'
        for i, w in enumerate(chunk)) + "</div>"


# --------------------------------------------------------------------------- #
# Scene text
# --------------------------------------------------------------------------- #
def scene_html(scene: Scene, handle: str) -> str:
    big = emphasize(scene.on_screen)
    if scene.kind == "point":
        top = f'<div class="num">{scene.index:02d}</div>'
    elif scene.kind == "cta":
        top = '<div class="kicker">FOLLOW FOR MORE</div>'
    else:
        top = ""
    extra = (f'<div class="kicker" style="margin:56px 0 0;background:var(--primary)">{html.escape(handle)}</div>'
             if scene.kind == "cta" else "")
    return f'<div class="scene" style="display:flex;flex-direction:column;align-items:center">{top}<div class="big">{big}</div>{extra}</div>'


def _snap(page, selector: str, out: Path, pad: int = 40) -> tuple[Path, tuple[int, int], dict]:
    """Screenshot just `selector`'s box (transparent bg). Returns path, image position, element box."""
    box = page.locator(selector).first.bounding_box()
    clip = {"x": max(0, box["x"] - pad), "y": max(0, box["y"] - pad),
            "width": min(W, box["width"] + 2 * pad), "height": min(H, box["height"] + 2 * pad)}
    page.screenshot(path=str(out), clip=clip, omit_background=True)
    return out, (int(clip["x"]), int(clip["y"])), box


def _show(page, mode: str, inner: str) -> None:
    page.evaluate("([m, h]) => window.__show(m, h)", [mode, inner])


# --------------------------------------------------------------------------- #
# Compositing
# --------------------------------------------------------------------------- #
def _ease_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _ease_in_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


@dataclass
class _Layer:
    """A transparent PNG visible in [start, end), optionally animated.

    animate: slide up + fade in (scene entrances)
    fade_in / fade_out: opacity ramps (crossfades)
    keys: [(time, x, y, duration), ...] -- glide to each (x, y) starting at its time
    """
    rgb: np.ndarray
    alpha: np.ndarray
    x: int
    y: int
    start: float
    end: float
    animate: bool = False
    fade_in: float = 0.0
    fade_out: float = 0.0
    keys: list[tuple[float, int, int, float]] | None = None

    @classmethod
    def load(cls, path: Path, x: int, y: int, start: float, end: float, **kw) -> "_Layer":
        img = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32)
        return cls(img[..., :3], img[..., 3:] / 255.0, x, y, start, end, **kw)

    def _pos(self, t: float) -> tuple[float, float]:
        if not self.keys:
            return self.x, self.y
        i = max((k for k, key in enumerate(self.keys) if key[0] <= t), default=0)
        t_i, x_i, y_i, dur = self.keys[i]
        _, x_p, y_p, _ = self.keys[i - 1] if i > 0 else self.keys[0]
        a = _ease_in_out((t - t_i) / dur)
        return x_p + (x_i - x_p) * a, y_p + (y_i - y_p) * a

    def blend(self, frame: np.ndarray, t: float) -> None:
        local, opacity, dy = t - self.start, 1.0, 0
        if self.animate:
            opacity, dy = min(local / 0.35, 1.0), int(70 * (1 - _ease_out(local / 0.45)))
        elif self.fade_in:
            opacity = min(local / self.fade_in, 1.0)
        if self.fade_out and self.end - t < self.fade_out:
            opacity *= max(0.0, (self.end - t) / self.fade_out)
        if opacity <= 0:
            return
        h, w = self.alpha.shape[:2]
        x, y = self._pos(t)
        x = int(min(max(x, 0), W - w))
        y = int(min(max(y + dy, 0), H - h))
        region = frame[y:y + h, x:x + w]
        a = self.alpha * opacity if opacity < 1 else self.alpha
        region += (self.rgb - region) * a


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build_scenes(content: Content) -> list[Scene]:
    r = content.reel
    scenes = [Scene("hook", r.hook_on_screen, [Part(r.hook_narration)])]
    points = [Scene("point", p.on_screen, [Part(p.narration)], i) for i, p in enumerate(r.points, 1)]
    scenes.append(points[0])
    if content.demo:
        scenes.append(Scene("demo", content.demo.title, [Part(s.narration) for s in content.demo.steps]))
    scenes += points[1:]
    scenes.append(Scene("cta", r.cta_on_screen, [Part(r.cta_narration)]))
    return scenes


def _list_path(demo: dict, n: int, src: int, dst: int) -> list[int]:
    """Nodes a linked-list pointer passes through going src → dst via next links (incl. dst)."""
    path, cur = [], src
    for _ in range(n + 1):
        if cur == dst and path:
            return path
        nxt = cur + 1 if cur + 1 < n else demo["cycle_to"]
        if nxt < 0:
            break
        path.append(nxt)
        cur = nxt
        if cur == dst:
            return path
    return [dst]


def _demo_layers(page, content: Content, scene: Scene, work: Path, is_last: bool) -> list[_Layer]:
    """Step snapshots (crossfading) + one gliding sprite per pointer name."""
    demo = content.demo.model_dump()
    steps = demo["steps"]
    scene_end = scene.start + scene.duration + (TAIL if is_last else GAP)
    starts = [scene.start + p.offset for p in scene.parts]
    layers: list[_Layer] = []
    step_geo = []

    for k in range(len(steps)):
        geo = page.evaluate("([v, k]) => window.__viz(v, k)", [demo, k])
        step_geo.append(geo)
        path, pos, _ = _snap(page, "#viz .viz-wrap", work / f"demo_{k}.png")
        end = starts[k + 1] + XFADE if k + 1 < len(steps) else scene_end
        layers.append(_Layer.load(path, *pos, starts[k], end, animate=k == 0,
                                  fade_in=0 if k == 0 else XFADE,
                                  fade_out=0.2 if k == len(steps) - 1 and not is_last else 0))

    # Pointer sprites
    names: list[str] = []
    for st in steps:
        for p in st["pointers"]:
            if p["name"] not in names:
                names.append(p["name"])
    for name in names:
        dir_ = step_geo[0]["dir"]
        page.evaluate("([n, d]) => window.__ptr(n, d)", [name, dir_])
        path, (ix, iy), box = _snap(page, "#ptr .viz-ptr", work / f"ptr_{re.sub(r'[^a-z0-9]', '_', name.lower())}.png", pad=6)
        off_x, off_y = box["x"] - ix, box["y"] - iy          # element offset inside the image
        bw, bh = box["width"], box["height"]

        def place(geo: dict, index: int, rank: int) -> tuple[int, int]:
            cell = geo["positions"][index]
            if dir_ == "up":
                ex, ey = cell["cx"] - bw / 2, cell["bottom"] + rank * (bh + 6)
            else:
                ex, ey = cell["right"] + rank * (bw + 6), cell["cy"] - bh / 2
            return int(ex - off_x), int(ey - off_y)

        segment: list[tuple[float, int, int, float]] = []
        seg_start, prev_index = None, None
        for k, st in enumerate(steps + [None]):              # sentinel closes the last segment
            here = [p for p in (st or {}).get("pointers", [])]
            match = next((p for p in here if p["name"] == name), None)
            cell = step_geo[k]["positions"][match["index"]] if (st and match and
                                                               match["index"] < len(step_geo[k]["positions"])) else None
            if cell:
                rank = [p["index"] for p in here[:here.index(match)]].count(match["index"])
                if seg_start is None:
                    seg_start = starts[k]
                n = len(step_geo[k]["positions"])
                if (demo["kind"] == "linked_list" and prev_index is not None
                        and prev_index != match["index"]):
                    # Follow the next links node by node (shows e.g. fast wrapping around a cycle).
                    hops = _list_path(demo, n, prev_index, match["index"])
                    for h, node in enumerate(hops):
                        x, y = place(step_geo[k], node, rank if node == match["index"] else 0)
                        segment.append((starts[k] + h * HOP, x, y, HOP))
                else:
                    segment.append((starts[k], *place(step_geo[k], match["index"], rank), MOVE))
                prev_index = match["index"]
            elif seg_start is not None:
                seg_end = starts[k] + XFADE if st else scene_end
                layers.append(_Layer.load(path, segment[0][1], segment[0][2], seg_start, seg_end,
                                          fade_in=XFADE if seg_start > scene.start else 0.35,
                                          fade_out=0.2, keys=segment))
                segment, seg_start, prev_index = [], None, None
    return layers


def render_reel(content: Content, out_dir: Path, music: Path | None = None,
                dry_run: bool = False) -> Path | None:
    brand = load_brand()
    scenes = build_scenes(content)
    if dry_run:
        for s in scenes:
            for p in s.parts:
                log.info("[dry-run] %-5s %-36s | %s", s.kind, s.on_screen[:36], p.narration)
        log.info("[dry-run] ~%d narration words",
                 sum(len(p.narration.split()) for s in scenes for p in s.parts))
        return None

    work = out_dir / "reel_parts"
    work.mkdir(parents=True, exist_ok=True)

    # 1) voiceover per part → exact timeline
    t = 0.0
    for i, s in enumerate(scenes):
        off = 0.0
        for j, p in enumerate(s.parts):
            synthesize(p, brand["voice"], work / f"voice_{i}_{j}.mp3", f"{s.kind} part {j}")
            p.offset = off
            off += p.duration + PART_GAP
        s.start = t
        t += s.duration + GAP
    total = scenes[-1].start + scenes[-1].duration + TAIL
    log.info("voiceover %.1fs across %d scenes", total, len(scenes))
    lo, hi = (int(x) for x in str(brand["reel"]["duration_sec"]).split("-"))
    if not lo <= total <= hi + 10:
        log.warning("reel is %.1fs, outside target %s s", total, brand["reel"]["duration_sec"])

    # 2) render visual layers
    ctx = {**brand_context(), "category": content.category}
    scene_layers: list[_Layer] = []
    sub_layers: list[_Layer] = []
    with browser_page(W, H) as page:
        page.set_content(env.get_template("reel.html").render(**ctx), wait_until="networkidle")
        _show(page, "bg", "")
        bg_path = work / "bg.png"
        page.screenshot(path=str(bg_path))

        for i, s in enumerate(scenes):
            last = s is scenes[-1]
            if s.kind == "demo":
                scene_layers += _demo_layers(page, content, s, work, last)
            else:
                _show(page, "text", scene_html(s, brand["handle"]))
                path, pos, _ = _snap(page, "#text .scene", work / f"scene_{i}.png")
                scene_layers.append(_Layer.load(
                    path, *pos, s.start, s.start + s.duration + (TAIL if last else GAP),
                    animate=s is not scenes[0],   # hook shows instantly → good thumbnail frame
                    fade_out=0.0 if last else 0.2))
                if s is scenes[0]:
                    cover = Image.open(bg_path).convert("RGBA")
                    cover.alpha_composite(Image.open(path).convert("RGBA"), pos)
                    cover.convert("RGB").save(out_dir / "reel_cover.jpg", quality=92)

            for j, p in enumerate(s.parts):
                chunks = chunk_words(p.words)
                base = s.start + p.offset
                for ci, chunk in enumerate(chunks):
                    next_start = chunks[ci + 1][0].start if ci + 1 < len(chunks) else p.duration
                    for wi, w in enumerate(chunk):
                        w_end = chunk[wi + 1].start if wi + 1 < len(chunk) else next_start
                        _show(page, "sub", caption_html(chunk, wi))
                        path, pos, _ = _snap(page, "#sub .cap", work / f"sub_{i}_{j}_{ci}_{wi}.png")
                        sub_layers.append(_Layer.load(path, *pos, base + w.start,
                                                      base + w.start + max(0.05, w_end - w.start)))

    # 3) compose: numpy frame function that blends only the small active regions
    bg = np.asarray(Image.open(bg_path).convert("RGB"), dtype=np.float32)
    bar_rgb = np.array([int(brand["colors"]["primary"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)],
                       dtype=np.float32)
    timeline = scene_layers + sub_layers   # later = on top

    def frame(tt: float) -> np.ndarray:
        f = bg.copy()
        for layer in timeline:
            if layer.start <= tt < layer.end:
                layer.blend(f, tt)
        f[0:10, : int(W * min(tt / total, 1.0))] = bar_rgb  # progress bar
        return f.astype(np.uint8)

    video = VideoClip(frame, duration=total)
    audio_clips = [AudioFileClip(str(p.audio)).with_start(s.start + p.offset)
                   for s in scenes for p in s.parts]
    if music:
        bgm = (AudioFileClip(str(music))
               .with_effects([afx.AudioLoop(duration=total), afx.MultiplyVolume(MUSIC_VOLUME),
                              afx.AudioFadeIn(0.5), afx.AudioFadeOut(1.5)]))
        audio_clips.insert(0, bgm)
    video = video.with_audio(CompositeAudioClip(audio_clips).with_duration(total))

    out = out_dir / "reel.mp4"
    video.write_videofile(
        str(out), fps=FPS, codec="libx264", audio_codec="aac", audio_fps=44100,
        audio_bitrate="128k", preset="medium", threads=4, logger=None,
        ffmpeg_params=["-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart",
                       "-profile:v", "high", "-level", "4.1"],
    )
    video.close()
    log.info("reel %.1fs → %s (%.1f MB)", total, out, out.stat().st_size / 1e6)
    return out


def _default_music() -> Path | None:
    """brand/config.yaml `reel.music` (a file or folder of mp3s), if set."""
    m = load_brand().get("reel", {}).get("music")
    if not m:
        return None
    p = Path(m) if Path(m).is_absolute() else Path(__file__).resolve().parent.parent / m
    if p.is_dir():
        files = sorted(p.glob("*.mp3"))
        return files[int(time.time() // 86400) % len(files)] if files else None
    return p if p.exists() else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render reel MP4 from content.json")
    ap.add_argument("content_json", type=Path)
    ap.add_argument("--music", type=Path, help="optional background music file")
    ap.add_argument("--dry-run", action="store_true", help="print scenes; render nothing")
    args = ap.parse_args(argv)
    content = Content.model_validate_json(args.content_json.read_text(encoding="utf-8"))
    render_reel(content, args.content_json.parent, args.music or _default_music(), args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
