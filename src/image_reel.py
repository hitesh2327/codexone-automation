"""Image reel: the carousel's last slide (the cheat sheet, the whole post on one page) as a short vertical
video with background music, published as an Instagram Reel instead of the carousel.

Instagram's API can't put music on a photo post, and its music library needs Facebook Login (this app uses
Instagram Login), so the music is a bundled track (brand/music/) mixed into the video.

brand/config.yaml:
    post_format: carousel | image_reel        # default; the Generate page can choose per post
    image_reel: { duration_sec: 12, music: brand/music, mood: {DSA: calm, ...} }

    python -m src.image_reel output/<date>/<slug> [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import subprocess
import sys
from pathlib import Path

from src.config import load_brand


def _ffmpeg() -> str:
    """The ffmpeg bundled with imageio-ffmpeg (as the reel renderer uses; CI installs no system ffmpeg)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 -- fall back to one on PATH
        return "ffmpeg"

log = logging.getLogger("codexone.image_reel")
ROOT = Path(__file__).resolve().parent.parent
W, H, FPS = 1080, 1920, 30
ZOOM = 0.05                       # the slide grows 5% over the video: motion without moving the text much
SLIDE_W, LIFT = 1000, 90          # slide width and how far above centre: clear of the caption/buttons (bottom 20%)
VIDEO, COVER = "image_reel.mp4", "image_reel_cover.jpg"
SRC = "image_reel_src"            # where the slides are rendered (not "carousel": no carousel is posted)
FORMATS = ("carousel", "image_reel")


def settings() -> dict:
    return load_brand().get("image_reel") or {}


def default_format() -> str:
    """brand/config.yaml `post_format`: what a post's second item is when a run doesn't choose."""
    f = str(load_brand().get("post_format") or "carousel").strip().lower()
    return f if f in FORMATS else "carousel"


def duration() -> float:
    return float(settings().get("duration_sec") or 12)


def pick_music(category: str = "", key: str = "") -> Path | None:
    """The track for this post: the category's mood (image_reel.mood) if that file exists, else one of the
    tracks in the folder, chosen by `key` so a post keeps its track when re-rendered."""
    folder = Path(settings().get("music") or "brand/music")
    folder = folder if folder.is_absolute() else ROOT / folder
    tracks = sorted(folder.glob("*.mp3")) if folder.is_dir() else []
    if not tracks:
        return None
    mood = (settings().get("mood") or {}).get(category)
    if mood and (folder / f"{mood}.mp3").exists():
        return folder / f"{mood}.mp3"
    return tracks[int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(tracks)]


def cheat_slide(slides_dir: Path) -> Path:
    slides = sorted(slides_dir.glob("slide_*.png"))
    if not slides:
        raise FileNotFoundError(f"no slides in {slides_dir}")
    return slides[-1]                                   # the cheat sheet is always the last slide


def render(slide: Path, out_dir: Path, music: Path | None, seconds: float | None = None,
           dry_run: bool = False) -> Path | None:
    """Write out_dir/image_reel.mp4 (1080x1920, H.264/AAC) and image_reel_cover.jpg from one slide."""
    seconds = seconds or duration()
    out, cover = out_dir / VIDEO, out_dir / COVER
    if dry_run:
        log.info("[dry-run] image reel %.0fs from %s with %s", seconds, slide.name, music.name if music else "silence")
        return None
    frames = int(seconds * FPS)
    # Background: the slide blown up, blurred and darkened to fill 9:16. Foreground: the slide, slowly
    # zooming, a little above centre so the app's caption and buttons don't cover it. Fades in and out.
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:6,"
          f"eq=brightness=-0.22:saturation=0.8[bg];"
          f"[0:v]scale=w='trunc({SLIDE_W}*(1+{ZOOM}*n/{frames})/2)*2':h=-2:eval=frame[fg];"
          f"[bg][fg]overlay=x='(W-w)/2':y='(H-h)/2-{LIFT}':eval=frame,fps={FPS},"
          f"fade=t=in:st=0:d=0.4,fade=t=out:st={seconds - 0.6:.2f}:d=0.6,format=yuv420p[v]")
    audio_in = (["-stream_loop", "-1", "-i", str(music)] if music
                else ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"])
    af = f"[1:a]afade=t=in:d=0.8,afade=t=out:st={seconds - 1.5:.2f}:d=1.5,volume=0.9[a]"
    ff = _ffmpeg()
    cmd = [ff, "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-t", f"{seconds}",
           "-i", str(slide), *audio_in, "-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
           "-t", f"{seconds}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
           "-level", "4.1", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(out)]
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)
    # Cover: a 9:16 frame of the video itself (after the fade-in), so posters and previews aren't cropped
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{min(1.5, seconds / 2):.2f}", "-i", str(out),
                    "-frames:v", "1", "-q:v", "3", str(cover)], check=True)
    log.info("image reel %.0fs → %s (%.1f MB, music: %s)", seconds, out, out.stat().st_size / 1e6,
             music.name if music else "none")
    return out


def render_post(post_dir: Path, category: str = "", dry_run: bool = False) -> Path | None:
    """The image reel of a post whose slides are already in post_dir/image_reel_src."""
    return render(cheat_slide(post_dir / SRC), post_dir, pick_music(category, post_dir.name), dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render a post's image reel (cheat sheet + music)")
    ap.add_argument("post_dir", type=Path)
    ap.add_argument("--category", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    render_post(args.post_dir, args.category, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
