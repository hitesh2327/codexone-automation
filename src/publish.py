"""Publish APPROVED queue items to Instagram (Instagram Login API, graph.instagram.com).

Safety: only items whose status is "approved" (set by a Telegram button press) or
"failed" (an approved item whose publish errored) can be published. There is no
flag to bypass this.

Flow:  create container(s) → poll status_code until FINISHED → media_publish.

Usage:
    python -m src.publish check                   # token/account/limit check (read-only)
    python -m src.publish item <item_id> [--dry-run]
    python -m src.publish due [--dry-run]         # approved items whose post time has passed
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

import requests

from src import queue_store as q
from src.approve_bot import IST, item_publish_at, notify
from src.config import get_env
from src.logger import get_logger

log = get_logger("publish")

MAX_ATTEMPTS = 3
TRANSIENT_CODES = {1, 2, 4, 17, 32, 341, 613, 9004, 2207001, 2207003, 2207020}


class IGError(RuntimeError):
    pass


def _base() -> str:
    return f"https://graph.instagram.com/{get_env('IG_API_VERSION', required=False, default='v21.0')}"


def _call(method: str, path: str, retries: int = 4, **params) -> dict:
    """Call the IG API with retries on network errors, 5xx and transient IG error codes."""
    params["access_token"] = get_env("IG_ACCESS_TOKEN")
    url = f"{_base()}/{path.lstrip('/')}"
    for attempt in range(1, retries + 1):
        try:
            r = requests.request(method, url, params=params if method == "GET" else None,
                                 data=params if method != "GET" else None, timeout=60)
        except requests.RequestException as e:
            err, transient = f"network error: {e}", True
        else:
            if r.ok:
                return r.json()
            try:
                e = r.json().get("error", {})
            except ValueError:
                e = {}
            code = e.get("code")
            sub = e.get("error_subcode")
            msg = e.get("error_user_msg") or e.get("message") or r.text[:300]
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


def publish_item(item: q.Item, dry_run: bool = False) -> q.Item:
    if item.status not in ("approved", "failed"):
        raise PermissionError(f"{item.id} is '{item.status}' -- only Telegram-approved items can be published")
    if item.ig_media_id:
        raise IGError(f"{item.id} already published as {item.ig_media_id}")

    if dry_run:
        check()
        urls = item.media.get("carousel", []) if item.kind == "carousel" else [item.media.get("reel")]
        for u in urls:
            r = requests.head(u, timeout=20)
            log.info("[dry-run] media %s → %s %s", u.rsplit("/", 1)[-1], r.status_code,
                     r.headers.get("content-type"))
            if not r.ok:
                raise IGError(f"media URL not reachable: {u}")
        log.info("[dry-run] would publish %s %s with %d-char caption:\n%s",
                 item.kind, item.id, len(item.caption), item.caption)
        return item

    item.attempts += 1
    try:
        if item.kind == "carousel":
            media_id = publish_carousel(item.media["carousel"], item.caption)
        else:
            media_id = publish_reel(item.media["reel"], item.caption)
    except Exception as e:
        item.status, item.error = "failed", str(e)
        q.upsert(item)
        log.error("publish %s failed (attempt %d/%d): %s", item.id, item.attempts, MAX_ATTEMPTS, e)
        notify(f"⚠️ Publish failed for <b>{item.kind}</b> <code>{item.id}</code> "
               f"(attempt {item.attempts}/{MAX_ATTEMPTS}):\n{e}", item.tg_control_id)
        raise
    item.status, item.ig_media_id, item.error = "published", media_id, None
    item.published_at = q.now_iso()
    q.upsert(item)
    q.record_posted(item)
    permalink = ""
    try:
        permalink = _call("GET", media_id, fields="permalink").get("permalink", "")
    except IGError:
        pass
    log.info("published %s → %s %s", item.id, media_id, permalink)
    notify(f"🚀 Published {item.kind}: {permalink or media_id}", item.tg_control_id)
    return item


def publish_due(dry_run: bool = False) -> list[q.Item]:
    """Publish approved items whose slot time (item.publish_at) has passed."""
    now = datetime.now(IST)
    done = []
    for item in q.load():
        ready = item.status == "approved" or (item.status == "failed" and item.attempts < MAX_ATTEMPTS)
        if not ready:
            continue
        if now < item_publish_at(item):
            log.info("%s approved; waiting for its slot %s IST", item.id, f"{item_publish_at(item):%d %b %H:%M}")
            continue
        try:
            done.append(publish_item(item, dry_run))
        except Exception:
            continue  # already logged + notified; other items still get a chance
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Publish approved items to Instagram")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="read-only token/account/quota check")
    p1 = sub.add_parser("item", help="publish one approved item now (ignores post time)")
    p1.add_argument("item_id")
    p1.add_argument("--dry-run", action="store_true")
    p2 = sub.add_parser("due", help="publish all approved items whose post time has passed")
    p2.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        check()
    elif args.cmd == "item":
        item = q.get(args.item_id)
        if not item:
            log.error("no queue item %s", args.item_id)
            return 1
        publish_item(item, args.dry_run)
    else:
        publish_due(args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
