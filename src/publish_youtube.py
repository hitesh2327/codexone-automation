"""Upload an approved reel to YouTube Shorts (YouTube Data API v3).

Uses the SAME reel MP4 that goes to Instagram (downloaded from its Cloudinary URL, so
it works in CI where local renders don't exist). Resumable upload with retries.

Credentials come from YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (see
get_yt_token.py). Privacy comes from YT_PRIVACY (private | unlisted | public; default public).

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
from src.credentials import get_for_user
from src.logger import get_logger

log = get_logger("publish_youtube")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
CATEGORY_EDUCATION = "27"
CATEGORY_SCIENCE_TECH = "28"
RETRIABLE_STATUS = {429, 500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, ConnectionError, TimeoutError, OSError)
MAX_RETRIES = 6
SHORTS_TITLE_TARGET = 60
TITLE_MAX = 100
TAGS_MAX_CHARS = 450  # YouTube allows 500 incl. separators; stay under

EDUCATION_CATEGORIES = frozenset({"dsa", "interview", "os", "algorithms", "data structures", "cs"})
DEAD_YT_TAGS = frozenset({"viral", "fyp", "foryou", "foryoupage", "explorepage", "explore", "trending", "instagood"})
CATEGORY_TAGS: dict[str, list[str]] = {
    "ai": ["artificial intelligence", "llm", "ai engineering", "machine learning"],
    "systemdesign": ["system design", "software architecture", "backend engineering", "distributed systems"],
    "dsa": ["data structures", "algorithms", "coding interview", "leetcode"],
    "interview": ["tech interview", "coding interview", "software engineer interview", "career"],
    "os": ["operating systems", "linux", "concurrency", "systems programming"],
    "dev": ["software engineering", "programming", "developer", "coding"],
}
YT_CTA = (
    "Which trade-off would you pick in production? Comment below.\n"
    "Subscribe for daily 20-second software engineering breakdowns."
)


class YTError(RuntimeError):
    pass


class YTQuotaExceeded(YTError):
    pass


def configured() -> bool:
    return all(get_for_user(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def privacy() -> str:
    p = (get_env("YT_PRIVACY", required=False, default="public") or "public").lower()
    if p not in ("private", "unlisted", "public"):
        raise YTError(f"YT_PRIVACY must be private, unlisted or public (got {p!r})")
    return p


def credentials() -> Credentials:
    creds = Credentials(token=None, refresh_token=get_for_user("YT_REFRESH_TOKEN"), token_uri=TOKEN_URI,
                        client_id=get_for_user("YT_CLIENT_ID"), client_secret=get_for_user("YT_CLIENT_SECRET"),
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
_IG_CTA_RE = re.compile(r"(?:in your dms?\b|\bdm me\b|link in bio\b|comment\s+['\"][A-Z0-9_-]+['\"])", re.I)


def category_id_for(category: str = "", text: str = "") -> str:
    """Use Education (27) for DSA/Interview/OS tutorials; Science & Tech (28) for AI/SystemDesign/Dev."""
    cat = category.strip().lower()
    if cat in EDUCATION_CATEGORIES:
        return CATEGORY_EDUCATION
    if not cat and any(k in text.lower() for k in ("leetcode", "big-o", "linked list", "binary search", "interview")):
        return CATEGORY_EDUCATION
    return CATEGORY_SCIENCE_TECH


def _warn_if_private(priv: str) -> None:
    if priv == "private":
        log.warning(
            "YT_PRIVACY=private: uploaded Shorts get 0 organic impressions or subscribers. "
            "Set YT_PRIVACY=public in GitHub Actions repository variables or .env to publish publicly."
        )


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


def _strip_ig_cta(text: str) -> str:
    """Remove Instagram-only DM/link-in-bio lines before publishing to YouTube."""
    return "\n".join(p for p in text.splitlines() if not _IG_CTA_RE.search(p)).strip()


def make_title(body: str, topic: str = "") -> str:
    """Search-intent Shorts title (< 60 chars incl. ' #Shorts' so mobile never truncates)."""
    suffix = " #Shorts"
    room = SHORTS_TITLE_TARGET - len(suffix)
    cleaned_body = _strip_ig_cta(_clean(body))
    first = re.split(r"(?<=[.!?])\s+", cleaned_body, maxsplit=1)[0].strip() if cleaned_body else ""
    clean_topic = _clean(topic)
    if clean_topic and (not first or (len(first) > room and len(clean_topic) <= room)):
        hook = clean_topic
    else:
        hook = first or clean_topic or "Software Engineering Breakdown"
    hook = hook.rstrip(".")
    if len(hook) > room:
        hook = hook[:room - 1].rsplit(" ", 1)[0].rstrip(",;:-—") + "…"
    return f"{hook}{suffix}"


def fit_title(title: str) -> str:
    """A custom title, cleaned and cut to YouTube's 100 chars (logs if > 60-char Shorts limit)."""
    t = _clean(title)
    if "#shorts" not in t.lower() and len(t) + 8 <= TITLE_MAX:
        t += " #Shorts"
    if len(t) > SHORTS_TITLE_TARGET:
        log.info("YouTube title is %d chars (> %d mobile Shorts truncation limit)", len(t), SHORTS_TITLE_TARGET)
    return t[:TITLE_MAX]


def youtube_description(body: str, hashtags: list[str], *, topic: str = "", category: str = "") -> str:
    """Keyword-rich YouTube Shorts SEO description (strips IG DM-bait, adds subscribe CTA + #Shorts)."""
    clean_body = _strip_ig_cta(_clean(body))
    lead = f"{_clean(topic)} — {category} breakdown." if topic and _clean(topic).lower() not in clean_body.lower() else ""
    clean_tags = [h for h in hashtags if h.lstrip("#").lower() not in DEAD_YT_TAGS][:4]
    if "#shorts" not in [t.lower() for t in clean_tags]:
        clean_tags = ["#Shorts"] + clean_tags
    tags_line = " ".join(clean_tags)
    return "\n\n".join(p for p in (lead, clean_body, YT_CTA, tags_line) if p)[:4900]


def youtube_tags(hashtags: list[str], *, category: str = "", topic: str = "") -> list[str]:
    """Deduplicated YouTube tags combining Shorts, topic keywords, category terms, and clean hashtags."""
    candidates = ["Shorts", "YouTube Shorts"]
    if topic and len(_clean(topic)) <= 45:
        candidates.append(_clean(topic))
    candidates.extend(CATEGORY_TAGS.get(category.strip().lower(), []))
    candidates.extend(h.lstrip("#") for h in hashtags if h.lstrip("#").lower() not in DEAD_YT_TAGS)
    tags: list[str] = []
    used = 0
    for t in candidates:
        t = t.strip()
        if not t or t.lower() in (x.lower() for x in tags):
            continue
        cost = len(t) + (2 if " " in t else 0) + 1
        if used + cost > TAGS_MAX_CHARS:
            break
        tags.append(t)
        used += cost
    return tags


def build_metadata(caption: str, title: str | None = None, description: str | None = None,
                   audio_language: str = "en", *, category: str = "", topic: str = "",
                   publish_at: str | None = None) -> dict:
    """title/description: dashboard overrides; otherwise built as Shorts-optimized SEO metadata.
    audio_language: "hi" for a Hinglish reel; the title and description stay English (defaultLanguage "en")."""
    body, hashtags = split_caption(caption)
    built_description = youtube_description(body, hashtags, topic=topic, category=category)
    tags = youtube_tags(hashtags, category=category, topic=topic)
    status: dict[str, str | bool] = {
        "selfDeclaredMadeForKids": False,
        "embeddable": True,
    }
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    else:
        status["privacyStatus"] = privacy()

    return {
        "snippet": {"title": fit_title(title) if title else make_title(body, topic=topic),
                    "description": _clean(description)[:4900] if description else built_description, "tags": tags,
                    "categoryId": category_id_for(category, f"{topic} {body}"), "defaultLanguage": "en",
                    "defaultAudioLanguage": audio_language},
        "status": status,
    }


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
def _download(url: str) -> Path:
    fd, name = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)  # an open handle would block deleting the file on Windows
    tmp = Path(name)
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
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
                msg = f"YouTube upload rejected: HTTP {e.resp.status} {reason}{hint}"
                if reason == "quotaExceeded" or "quotaExceeded" in str(e):
                    raise YTQuotaExceeded(msg) from e
                raise YTError(msg) from e
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
                 description: str | None = None, audio_language: str = "en",
                 *, category: str = "", topic: str = "", publish_at: str | None = None) -> tuple[str, str]:
    """Upload a reel (local path or URL). Returns (video_id, shorts_url)."""
    body = build_metadata(caption, title, description, audio_language, category=category, topic=topic,
                          publish_at=publish_at)
    priv = body["status"]["privacyStatus"]
    if not publish_at:
        _warn_if_private(priv)
    if dry_run:
        credentials()
        if video.startswith("http"):
            r = requests.head(video, timeout=20)
            if not r.ok:
                raise YTError(f"reel URL not reachable: HTTP {r.status_code}")
        log.info("[dry-run] YouTube token OK; would upload as %s (categoryId=%s):\n  title: %s\n  tags: %s\n  description:\n%s",
                 priv, body["snippet"]["categoryId"], body["snippet"]["title"],
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
    log.info("uploaded to YouTube (%s): %s", priv, shorts_url(vid))
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
        priv = privacy()
        _warn_if_private(priv)
        log.info("YouTube token OK (scope: youtube.upload); uploads will be %s", priv)
    elif args.cmd == "metadata":
        from src import queue_store as q
        item = q.get(args.item_id)
        if not item:
            log.error("no queue item %s", args.item_id)
            return 1
        import json
        print(json.dumps(build_metadata(item.caption, category=item.category, topic=item.topic),
                         indent=2, ensure_ascii=False))
    else:
        publish_reel(args.video, args.caption_file.read_text(encoding="utf-8"), args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
