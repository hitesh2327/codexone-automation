"""Publish APPROVED queue items to Instagram and (reels) YouTube Shorts.

Safety: only items whose status is "approved" (set by a Telegram button press) or
"failed" (an approved item whose publish errored) can be published. There is no
flag to bypass this.

Instagram: create container(s) → poll status_code until FINISHED → media_publish.
YouTube:   reels only, via src/publish_youtube.py (same MP4). Skipped if YT_* secrets are unset.

Order is Instagram, then YouTube; a failure on one never blocks the other. Each
platform's result is stored on the item and in data/posted.json, and a retry only
redoes platforms that have not succeeded.

Usage:
    python -m src.publish check                   # token/account/limit check (read-only)
    python -m src.publish item <item_id> [--platform ig|yt|all] [--dry-run]
    python -m src.publish due [--platform ig|yt|all] [--dry-run]   # approved + slot time passed
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

import requests

from src import activity
from src import publish_youtube as yt
from src import queue_store as q
from src.approve_bot import IST, item_publish_at, notify
from src.config import get_env
from src.logger import get_logger
from src.redact import redact, redact_exc

log = get_logger("publish")

MAX_ATTEMPTS = 3
TRANSIENT_CODES = {1, 2, 4, 17, 32, 341, 613, 9004, 2207001, 2207003, 2207020}


class IGError(RuntimeError):
    pass


def _base() -> str:
    return f"https://graph.instagram.com/{get_env('IG_API_VERSION', required=False, default='v21.0')}"


def _call(method: str, path: str, retries: int = 4, **params) -> dict:
    """Call the IG API with retries on network errors, 5xx and transient IG error codes.

    The token travels as the documented `access_token` parameter: in the form body for POST, and in the
    query string for GET (Meta documents only the query form for GET /me, container status and
    refresh_access_token). A GET URL therefore contains the token, so a network error's text (which
    `requests` builds from the URL) is never kept raw: it is scrubbed before it can reach a log line,
    an IGError, the post's `error` field, the activity log or Telegram.
    """
    params["access_token"] = get_env("IG_ACCESS_TOKEN")
    url = f"{_base()}/{path.lstrip('/')}"
    for attempt in range(1, retries + 1):
        try:
            r = requests.request(method, url, params=params if method == "GET" else None,
                                 data=params if method != "GET" else None, timeout=60)
        except requests.RequestException as e:
            err, transient = f"network error: {redact_exc(e, 300)}", True
        else:
            if r.ok:
                return r.json()
            try:
                e = r.json().get("error", {})
            except ValueError:
                e = {}
            code = e.get("code")
            sub = e.get("error_subcode")
            msg = redact(e.get("error_user_msg") or e.get("message") or r.text[:300])
            err = f"HTTP {r.status_code}, IG error {code}/{sub}: {msg}"
            transient = r.status_code >= 500 or e.get("is_transient") or code in TRANSIENT_CODES \
                or sub in TRANSIENT_CODES
            if code == 190:
                raise IGError(f"Instagram access token is invalid or expired ({msg}). "
                              "Generate a new long-lived token and update IG_ACCESS_TOKEN.")
        if not transient or attempt == retries:
            raise IGError(f"{method} {path} failed: {err}")
        wait = 10 * attempt
        log.warning("%s %s: %s -- retrying in %ds (%d/%d)", method, path, err, wait, attempt, retries)
        time.sleep(wait)
    raise IGError("unreachable")


def _wait_finished(container_id: str, timeout: int = 600, interval: int = 8) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _call("GET", container_id, fields="status_code,status")
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise IGError(f"container {container_id} {code}: {status.get('status', '')}")
        log.debug("container %s: %s", container_id, code)
        time.sleep(interval)
    raise IGError(f"container {container_id} not ready after {timeout}s")


_resolved_user: str | None = None


def _user() -> str:
    """Numeric IG user id. If IG_USER_ID is unset or not numeric (e.g. the @username),
    resolve it from the token via /me."""
    global _resolved_user
    if _resolved_user:
        return _resolved_user
    configured = get_env("IG_USER_ID", required=False, default="")
    if configured.isdigit():
        _resolved_user = configured
    else:
        me = _call("GET", "me", fields="user_id,username")
        _resolved_user = str(me["user_id"])
        log.warning("IG_USER_ID %r is not a numeric id; using %s (@%s) from the token. "
                    "Set IG_USER_ID=%s to skip this lookup.",
                    configured, _resolved_user, me.get("username"), _resolved_user)
    return _resolved_user


# --------------------------------------------------------------------------- #
# Publishing
# --------------------------------------------------------------------------- #
def publish_carousel(image_urls: list[str], caption: str) -> str:
    if not 2 <= len(image_urls) <= 10:
        raise IGError(f"carousel needs 2-10 images, got {len(image_urls)}")
    children = []
    for i, url in enumerate(image_urls, 1):
        c = _call("POST", f"{_user()}/media", image_url=url, is_carousel_item="true")
        children.append(c["id"])
        log.info("child %d/%d container %s", i, len(image_urls), c["id"])
    for cid in children:
        _wait_finished(cid, timeout=180, interval=4)
    parent = _call("POST", f"{_user()}/media", media_type="CAROUSEL",
                   children=",".join(children), caption=caption)["id"]
    _wait_finished(parent, timeout=180, interval=4)
    return _call("POST", f"{_user()}/media_publish", creation_id=parent)["id"]


def publish_reel(video_url: str, caption: str) -> str:
    # No cover_url: IG put containers into ERROR with our Cloudinary cover JPEG. The first
    # frame (thumb_offset 0) is the hook screen, which is designed to be the thumbnail.
    params = {"media_type": "REELS", "video_url": video_url, "caption": caption,
              "share_to_feed": "true", "thumb_offset": "0"}
    container = _call("POST", f"{_user()}/media", **params)["id"]
    log.info("reel container %s, waiting for processing…", container)
    _wait_finished(container, timeout=900, interval=10)
    return _call("POST", f"{_user()}/media_publish", creation_id=container)["id"]


def check() -> dict:
    """Read-only sanity check: token works, account matches, publishing quota."""
    me = _call("GET", "me", fields="user_id,username,account_type")
    if str(me.get("user_id")) != _user():
        raise IGError(f"IG_USER_ID {_user()} does not match the token's account "
                      f"{me.get('user_id')} (@{me.get('username')})")
    limit = _call("GET", f"{_user()}/content_publishing_limit", fields="quota_usage,config")
    data = (limit.get("data") or [{}])[0]
    log.info("account @%s (%s); published last 24h: %s/%s", me.get("username"), me.get("account_type"),
             data.get("quota_usage"), (data.get("config") or {}).get("quota_total"))
    return {"me": me, "limit": data}


PLATFORMS = ("ig", "yt")
LABEL = {"ig": "Instagram", "yt": "YouTube"}


def _targets(item: q.Item, platforms: tuple[str, ...]) -> list[str]:
    """The requested platforms that this item is set to go to (item.targets; carousels are IG-only)."""
    return [p for p in platforms if p in item.effective_targets]


def _done(item: q.Item, p: str) -> bool:
    return item.platforms.get(p, {}).get("status") in ("published", "skipped")


def _retryable(item: q.Item, platforms: tuple[str, ...]) -> bool:
    """A failed item is retried while some failed platform is still under MAX_ATTEMPTS."""
    return any(item.platforms.get(p, {}).get("status") == "failed"
               and item.platforms[p].get("attempts", 1) < MAX_ATTEMPTS
               for p in _targets(item, platforms))


def _publish_ig(item: q.Item) -> dict:
    if item.kind == "carousel":
        media_id = publish_carousel(item.media["carousel"], item.caption)
    else:
        media_id = publish_reel(item.media["reel"], item.caption)
    item.ig_media_id = media_id
    permalink = ""
    try:
        permalink = _call("GET", media_id, fields="permalink").get("permalink", "")
    except IGError:
        pass
    return {"status": "published", "id": media_id, "url": permalink}


def _publish_yt(item: q.Item) -> dict:
    if not yt.configured():
        return {"status": "skipped", "error": "YT_CLIENT_ID/YT_CLIENT_SECRET/YT_REFRESH_TOKEN not set"}
    vid, url = yt.publish_reel(item.media["reel"], item.caption, title=item.yt_title,
                               description=item.yt_description)
    return {"status": "published", "id": vid, "url": url, "privacy": yt.privacy()}


def _log_platform(item: q.Item, p: str, rec: dict, tries: int) -> None:
    st = rec.get("status")
    if st == "published":
        activity.record("post.published", f"Published {item.kind} “{item.topic}” to {LABEL[p]}",
                        source="publisher", post_id=item.id,
                        detail={"platform": p, "url": rec.get("url"), "media_id": rec.get("id")})
    elif st == "skipped":
        activity.record("publish.skipped", f"Skipped {LABEL[p]} for {item.kind} “{item.topic}”: {rec.get('error')}",
                        level="warning", source="publisher", post_id=item.id, detail={"platform": p})
    else:
        giving_up = tries >= MAX_ATTEMPTS
        activity.record("publish.failed",
                        f"{LABEL[p]} publish failed for {item.kind} “{item.topic}” "
                        f"(attempt {tries}/{MAX_ATTEMPTS}{', giving up' if giving_up else ''})",
                        level="error", source="publisher", post_id=item.id,
                        detail={"platform": p, "error": rec.get("error"), "attempt": tries})


def publish_item(item: q.Item, dry_run: bool = False, platforms: tuple[str, ...] = PLATFORMS) -> q.Item:
    # "published" is allowed so a platform that failed or was added later can be completed;
    # pending/rejected/expired items can never be published.
    if item.status not in ("approved", "publishing", "failed", "published"):
        raise PermissionError(f"{item.id} is '{item.status}' -- only Telegram-approved items can be published")
    if item.ig_media_id and "ig" not in item.platforms:  # published before per-platform tracking
        item.platforms["ig"] = {"status": "published", "id": item.ig_media_id}

    targets = _targets(item, platforms)
    todo = [p for p in targets if not _done(item, p)]
    if not todo:
        log.info("%s already published on %s", item.id, ", ".join(LABEL[p] for p in targets) or "nothing")
        return item

    if dry_run:
        for p in todo:
            if p == "ig":
                check()
                urls = item.media.get("carousel", []) if item.kind == "carousel" else [item.media.get("reel")]
                for u in urls:
                    r = requests.head(u, timeout=20)
                    log.info("[dry-run] media %s → %s %s", u.rsplit("/", 1)[-1], r.status_code,
                             r.headers.get("content-type"))
                    if not r.ok:
                        raise IGError(f"media URL not reachable: {u}")
                log.info("[dry-run] would publish %s %s to Instagram with %d-char caption",
                         item.kind, item.id, len(item.caption))
            elif yt.configured():
                yt.publish_reel(item.media["reel"], item.caption, dry_run=True, title=item.yt_title,
                                description=item.yt_description)
            else:
                log.info("[dry-run] YouTube not configured (YT_* unset); would skip")
        return item

    # A scheduled poll and a manual/dashboard publish can overlap, and Instagram accepts the
    # same post twice. Whoever claims the item publishes it; the other backs off.
    if item.status != "publishing" and not q.claim_for_publish(item.id):
        log.warning("%s is already being published by another run; skipping", item.id)
        return q.get(item.id) or item
    item.status = "publishing"

    item.attempts += 1
    for p in todo:  # Instagram first, then YouTube; saved after each so nothing double-posts
        tries = item.platforms.get(p, {}).get("attempts", 0) + 1
        try:
            rec = _publish_ig(item) if p == "ig" else _publish_yt(item)
        except Exception as e:  # noqa: BLE001 -- one platform failing must not stop the other
            rec = {"status": "failed", "error": str(e)[:300]}
            log.error("%s: %s publish failed (attempt %d/%d): %s", item.id, LABEL[p], tries, MAX_ATTEMPTS, e)
        rec["attempts"] = tries
        rec["at"] = q.now_iso()
        _log_platform(item, p, rec, tries)
        item.platforms[p] = rec
        q.upsert(item)

    failed = [p for p in targets if item.platforms.get(p, {}).get("status") == "failed"]
    published = [p for p in targets if item.platforms.get(p, {}).get("status") == "published"]
    item.status = "failed" if failed else "published"
    item.error = "; ".join(f"{LABEL[p]}: {item.platforms[p]['error']}" for p in failed) or None
    if published and not item.published_at:
        item.published_at = q.now_iso()
    q.upsert(item)
    q.record_posted(item)

    head = "🚀" if published else "⚠️"
    lines = [f"{head} <b>{item.kind.capitalize()}</b> — {item.topic}"]
    for p in targets:
        r = item.platforms.get(p, {})
        if r.get("status") == "published":
            extra = f" ({r['privacy']})" if r.get("privacy") and r["privacy"] != "public" else ""
            lines.append(f"✅ {LABEL[p]}{extra}: {r.get('url') or r.get('id')}")
        elif r.get("status") == "skipped":
            lines.append(f"⏭ {LABEL[p]}: skipped ({r.get('error')})")
        else:
            retry = " — will retry" if r.get("attempts", 1) < MAX_ATTEMPTS else " — giving up"
            lines.append(f"❌ {LABEL[p]}: {r.get('error', 'failed')}{retry}")
    notify("\n".join(lines), item.tg_control_id)
    log.info("%s → %s", item.id, {p: item.platforms[p]["status"] for p in targets})
    return item


def publish_due(dry_run: bool = False, platforms: tuple[str, ...] = PLATFORMS) -> list[q.Item]:
    """Publish approved items whose slot time (item.publish_at) has passed."""
    now = datetime.now(IST)
    done = []
    for item in q.load():
        ready = item.status == "approved" or (item.status == "failed" and _retryable(item, platforms))
        if not ready:
            continue
        if now < item_publish_at(item):
            log.info("%s approved; waiting for its slot %s IST", item.id, f"{item_publish_at(item):%d %b %H:%M}")
            continue
        try:
            done.append(publish_item(item, dry_run, platforms))
        except Exception:  # noqa: BLE001
            log.exception("publish %s crashed", item.id)
    return done


def platforms_arg(value: str) -> tuple[str, ...]:
    return PLATFORMS if value == "all" else (value,)


def mark(item: q.Item, platform: str, media_id: str) -> q.Item:
    """Record a post made outside the normal flow (e.g. an upload whose result was lost)."""
    url = yt.shorts_url(media_id) if platform == "yt" else ""
    item.platforms[platform] = {"status": "published", "id": media_id, "url": url,
                                "attempts": item.platforms.get(platform, {}).get("attempts", 0),
                                "at": q.now_iso(), "note": "marked manually"}
    if platform == "ig":
        item.ig_media_id = media_id
    if not any(r.get("status") == "failed" for r in item.platforms.values()):
        item.status, item.error = "published", None
    q.upsert(item)
    q.record_posted(item)
    log.info("marked %s as published on %s: %s", item.id, LABEL[platform], url or media_id)
    return item


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Publish approved items to Instagram / YouTube")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="read-only token/account/quota check")
    p1 = sub.add_parser("item", help="publish one approved item now (ignores post time)")
    p1.add_argument("item_id")
    p2 = sub.add_parser("due", help="publish all approved items whose post time has passed")
    for sp in (p1, p2):
        sp.add_argument("--platform", choices=["ig", "yt", "all"], default="all")
        sp.add_argument("--dry-run", action="store_true")
    p3 = sub.add_parser("mark", help="record an existing post (id) for an item without publishing")
    p3.add_argument("item_id")
    p3.add_argument("platform", choices=["ig", "yt"])
    p3.add_argument("media_id", help="IG media id, or YouTube video id / Shorts URL")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        check()
    elif args.cmd == "mark":
        item = q.get(args.item_id)
        if not item:
            log.error("no queue item %s", args.item_id)
            return 1
        mark(item, args.platform, args.media_id.rstrip("/").rsplit("/", 1)[-1].split("?")[0])
    elif args.cmd == "item":
        item = q.get(args.item_id)
        if not item:
            log.error("no queue item %s", args.item_id)
            return 1
        item = publish_item(item, args.dry_run, platforms_arg(args.platform))
        return 1 if item.status == "failed" else 0
    else:
        publish_due(args.dry_run, platforms_arg(args.platform))
    return 0


if __name__ == "__main__":
    sys.exit(main())
