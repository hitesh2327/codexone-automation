"""Upload rendered media to Cloudinary and return public HTTPS URLs.

Carousel slides are converted to JPEG on upload (Instagram's API only accepts JPEG
images). Results are saved next to the content as media.json.

Usage:
    python -m src.upload output/<date>/<slug> [--only carousel|reel] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import cloudinary
import cloudinary.uploader

from src.config import OUTPUT_DIR, get_env
from src.logger import get_logger

log = get_logger("upload")
FOLDER = "codexone"


def _configure() -> None:
    url = get_env("CLOUDINARY_URL")
    # Tolerate the whole "CLOUDINARY_URL=cloudinary://..." line pasted as the value.
    url = url.split("=", 1)[1] if url.upper().startswith("CLOUDINARY_URL=") else url
    if not url.startswith("cloudinary://"):
        raise RuntimeError("CLOUDINARY_URL must look like cloudinary://<key>:<secret>@<cloud_name>")
    os.environ["CLOUDINARY_URL"] = url
    cloudinary.reset_config()
    cloudinary.config(secure=True)


def _upload(path: Path, public_id: str, resource_type: str, retries: int = 3, **opts) -> str:
    for attempt in range(1, retries + 1):
        try:
            res = cloudinary.uploader.upload(
                str(path), public_id=public_id, resource_type=resource_type,
                overwrite=True, invalidate=True, **opts)
            return res["secure_url"]
        except Exception as e:  # cloudinary raises its own Error + network errors
            log.warning("upload %s failed (attempt %d/%d): %s", path.name, attempt, retries, e)
            time.sleep(3 * attempt)
    raise RuntimeError(f"Cloudinary upload failed for {path}")


def upload_post(post_dir: Path, only: str | None = None, dry_run: bool = False) -> dict:
    """Upload carousel slides / reel / cover from post_dir. Returns and saves media.json."""
    rel = post_dir.resolve().relative_to(OUTPUT_DIR.resolve()).as_posix()  # <date>/<slug>
    base = f"{FOLDER}/{rel}"
    media_file = post_dir / "media.json"
    media = json.loads(media_file.read_text(encoding="utf-8")) if media_file.exists() else {}

    slides = sorted((post_dir / "carousel").glob("slide_*.png"))
    reel, cover = post_dir / "reel.mp4", post_dir / "reel_cover.jpg"
    plan = []
    if only in (None, "carousel"):
        plan += [("carousel", s) for s in slides]
    if only in (None, "reel"):
        plan += [("reel", p) for p in (reel, cover) if p.exists()]
    if not plan:
        raise FileNotFoundError(f"nothing to upload in {post_dir} (render first)")

    if dry_run:
        for kind, p in plan:
            log.info("[dry-run] would upload %s → %s/%s", p.name, base, p.stem)
        return media

    _configure()
    if only in (None, "carousel") and slides:
        media["carousel"] = [
            _upload(s, f"{base}/{s.stem}", "image", format="jpg", quality="95") for s in slides]
        log.info("uploaded %d slides", len(slides))
    if only in (None, "reel") and reel.exists():
        media["reel"] = _upload(reel, f"{base}/reel", "video")
        if cover.exists():
            media["cover"] = _upload(cover, f"{base}/reel_cover", "image")
        log.info("uploaded reel")
    media_file.write_text(json.dumps(media, indent=2), encoding="utf-8")
    return media


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Upload rendered media to Cloudinary")
    ap.add_argument("post_dir", type=Path)
    ap.add_argument("--only", choices=["carousel", "reel"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    media = upload_post(args.post_dir, args.only, args.dry_run)
    print(json.dumps(media, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
