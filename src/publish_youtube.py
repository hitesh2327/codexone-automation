"""Upload an approved reel to YouTube Shorts (YouTube Data API v3).

Uses the SAME reel MP4 that goes to Instagram (downloaded from its Cloudinary URL, so
it works in CI where local renders don't exist). Resumable upload with retries.

Credentials come from YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (see
get_yt_token.py). Privacy comes from YT_PRIVACY (private | unlisted | public; default private).

Usage:
    python -m src.publish_youtube check                           # refresh token only (read-only)
    python -m src.publish_youtube metadata <item_id>              # show title/description/tags
    python -m src.publish_youtube upload <mp4-or-url> --caption-file c.txt [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
import tempfile
import time
from pathlib import Path

import httplib2
import requests
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from src.config import get_env, load_brand
from src.logger import get_logger

log = get_logger("publish_youtube")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
CATEGORY_SCIENCE_TECH = "28"
RETRIABLE_STATUS = {500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, ConnectionError, TimeoutError, OSError)
MAX_RETRIES = 6
TITLE_MAX = 100
TAGS_MAX_CHARS = 450  # YouTube allows 500 incl. separators; stay under


class YTError(RuntimeError):
    pass


def configured() -> bool:
    return all(get_env(k, required=False) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def privacy() -> str:
    p = (get_env("YT_PRIVACY", required=False, default="private") or "private").lower()
    if p not in ("private", "unlisted", "public"):
        raise YTError(f"YT_PRIVACY must be private, unlisted or public (got {p!r})")
    return p


def credentials() -> Credentials:
    creds = Credentials(token=None, refresh_token=get_env("YT_REFRESH_TOKEN"), token_uri=TOKEN_URI,
                        client_id=get_env("YT_CLIENT_ID"), client_secret=get_env("YT_CLIENT_SECRET"),
                        scopes=SCOPES)
    try:
        creds.refresh(Request())
    except RefreshError as e:
        raise YTError(
            f"YouTube refresh token rejected ({e}). Re-run get_yt_token.py and update YT_REFRESH_TOKEN. "
            "If the OAuth consent screen is in 'Testing' mode, Google expires refresh tokens after 7 days; "
            "switch it to 'In production' to stop that.") from e
    return creds


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
_HASHTAG = re.compile(r"#\w+")


def _clean(text: str) -> str:
    """YouTube rejects '<' and '>' in titles/descriptions; drop *emphasis* markers."""
    return text.replace("<", "").replace(">", "").replace("*", "").strip()


def split_caption(caption: str) -> tuple[str, list[str]]:
    """Queue captions are '<body>\\n\\n#tag #tag …'. Returns (body, hashtags)."""
    hashtags = list(dict.fromkeys(_HASHTAG.findall(caption)))
    body, _, tail = caption.strip().rpartition("\n\n")
    if body and tail and all(w.startswith("#") for w in tail.split()):
        return body.strip(), hashtags
    return caption.strip(), hashtags


def make_title(body: str) -> str:
    """Hook = first sentence of the caption, fitted with ' #Shorts' into 100 chars."""
    hook = re.split(r"(?<=[.!?])\s+", _clean(body), maxsplit=1)[0]
    suffix = " #Shorts"
    room = TITLE_MAX - len(suffix)
    if len(hook) > room:
        hook = hook[: room - 1].rsplit(" ", 1)[0].rstrip(",;:-") + "…"
    return hook + suffix


def fit_title(title: str) -> str:
    """A custom title, cleaned and cut to YouTube's 100 chars (adds #Shorts if there's room)."""
    t = _clean(title)
    if "#shorts" not in t.lower() and len(t) + 8 <= TITLE_MAX:
        t += " #Shorts"
    return t[:TITLE_MAX]


def build_metadata(caption: str, title: str | None = None, description: str | None = None) -> dict:
    """title/description: dashboard overrides; otherwise built from the caption."""
    body, hashtags = split_caption(caption)
    cta = load_brand().get("cta", "")
    tags_line = " ".join(hashtags + (["#Shorts"] if "#Shorts" not in hashtags else []))
    built_description = "\n\n".join(p for p in (_clean(body), cta, tags_line) if p)[:4900]
    tags, used = [], 0
    for t in [h.lstrip("#") for h in hashtags] + ["Shorts"]:
        if t.lower() in (x.lower() for x in tags):
            continue
        cost = len(t) + (2 if " " in t else 0) + 1
        if used + cost > TAGS_MAX_CHARS:
            break
        tags.append(t)
        used += cost
    return {
        "snippet": {"title": fit_title(title) if title else make_title(body),
                    "description": _clean(description)[:4900] if description else built_description, "tags": tags,
                    "categoryId": CATEGORY_SCIENCE_TECH, "defaultLanguage": "en",
                    "defaultAudioLanguage": "en"},
        "status": {"privacyStatus": privacy(), "selfDeclaredMadeForKids": False, "embeddable": True},
    }


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
def _download(url: str) -> Path:
    fd, name = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)  # an open handle would block deleting the file on Windows
    tmp = Path(name)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    log.info("downloaded reel %.1f MB", tmp.stat().st_size / 1e6)
    return tmp


def _reason(e: HttpError) -> str:
    try:
        return e.error_details[0].get("reason", "") if e.error_details else ""
    except Exception:  # noqa: BLE001
        return ""


def upload_file(path: Path, body: dict) -> str:
    youtube = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    # Our own file handle (closed by `with`), so nothing keeps the MP4 locked afterwards.
    with path.open("rb") as fh:
        media = MediaIoBaseUpload(fh, mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        return _run_upload(request)


def _run_upload(request) -> str:
    response, retries = None, 0
    while response is None:
        err = None
        try:
            status, response = request.next_chunk()
            if status:
                log.info("upload %d%%", int(status.progress() * 100))
        except HttpError as e:
            if e.resp.status not in RETRIABLE_STATUS:
                reason = _reason(e)
                hint = {"quotaExceeded": " (daily API quota used up; resets at midnight Pacific time)",
                        "uploadLimitExceeded": " (channel's daily upload limit reached)"}.get(reason, "")
                raise YTError(f"YouTube upload rejected: HTTP {e.resp.status} {reason}{hint}") from e
            err = f"HTTP {e.resp.status}"
        except RETRIABLE_EXCEPTIONS as e:
            err = f"{type(e).__name__}: {e}"
        if err:
            retries += 1
            if retries > MAX_RETRIES:
                raise YTError(f"YouTube upload failed after {MAX_RETRIES} retries: {err}")
            wait = min(2 ** retries + random.random(), 60)
            log.warning("upload error (%s); resuming in %.0fs (%d/%d)", err, wait, retries, MAX_RETRIES)
            time.sleep(wait)
    if "id" not in response:
        raise YTError(f"unexpected upload response: {response}")
    return response["id"]


def shorts_url(video_id: str) -> str:
    return f"https://youtube.com/shorts/{video_id}"


def publish_reel(video: str, caption: str, dry_run: bool = False, title: str | None = None,
                 description: str | None = None) -> tuple[str, str]:
    """Upload a reel (local path or URL). Returns (video_id, shorts_url)."""
    body = build_metadata(caption, title, description)
    if dry_run:
        credentials()
        if video.startswith("http"):
            r = requests.head(video, timeout=20)
            if not r.ok:
                raise YTError(f"reel URL not reachable: HTTP {r.status_code}")
        log.info("[dry-run] YouTube token OK; would upload as %s:\n  title: %s\n  tags: %s\n  description:\n%s",
                 body["status"]["privacyStatus"], body["snippet"]["title"],
                 ", ".join(body["snippet"]["tags"]), body["snippet"]["description"])
        return "", ""
    path, tmp = (Path(video), None) if not video.startswith("http") else (None, _download(video))
    try:
        vid = upload_file(tmp or path, body)
    finally:
        if tmp:
            try:
                tmp.unlink(missing_ok=True)
            except OSError as e:  # cleanup must never mask a finished upload
                log.warning("could not delete temp file %s: %s", tmp, e)
    log.info("uploaded to YouTube (%s): %s", body["status"]["privacyStatus"], shorts_url(vid))
    return vid, shorts_url(vid)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="YouTube Shorts uploader")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="verify the refresh token (no upload)")
    m = sub.add_parser("metadata", help="show the metadata a queue item would get")
    m.add_argument("item_id")
    u = sub.add_parser("upload", help="upload a file/URL directly (bypasses the approval queue)")
    u.add_argument("video")
    u.add_argument("--caption-file", type=Path, required=True)
    u.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        credentials()
        log.info("YouTube token OK (scope: youtube.upload); uploads will be %s", privacy())
    elif args.cmd == "metadata":
        from src import queue_store as q
        item = q.get(args.item_id)
        if not item:
            log.error("no queue item %s", args.item_id)
            return 1
        import json
        print(json.dumps(build_metadata(item.caption), indent=2, ensure_ascii=False))
    else:
        publish_reel(args.video, args.caption_file.read_text(encoding="utf-8"), args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
