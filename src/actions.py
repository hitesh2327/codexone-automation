"""High-level post actions used by the admin dashboard.

State changes go through queue_store.apply_decision (the same rules the Telegram bot
uses) and every decision is mirrored to the Telegram preview, so approving in either
place updates both.

Env switches (for local development against real credentials):
    PUBLISH_ENABLED=false  -> "publish now" / "retry" refuse instead of posting
    TELEGRAM_SYNC=false    -> no Telegram calls at all (see approve_bot.sync_enabled)
"""
from __future__ import annotations

import re
from datetime import datetime

import requests

from src import activity, approve_bot
from src import queue_store as q
from src.approve_bot import IST
from src.config import get_env
from src.logger import get_logger
from src.publish_youtube import TITLE_MAX, split_caption
from src.redact import redact

log = get_logger("actions")

CAPTION_MAX = 2200     # Instagram
HASHTAGS_MAX = 30      # Instagram
_TAG = re.compile(r"^#?(\w{1,100})$")


class ActionError(ValueError):
    pass


def publishing_enabled() -> bool:
    return (get_env("PUBLISH_ENABLED", required=False, default="true") or "true").lower() not in ("0", "false", "no")


def _get(item_id: str) -> q.Item:
    item = q.get(item_id)
    if not item:
        raise ActionError("Post not found")
    return item


def _decide(item: q.Item, action: str, feedback: str = "") -> None:
    try:
        q.apply_decision(item, action, feedback=feedback)
    except q.DecisionError as e:
        raise ActionError(str(e)) from e


def _set_targets(item: q.Item, targets: list[str] | None) -> None:
    if targets is None:
        return
    allowed = q.DEFAULT_TARGETS[item.kind]
    bad = [t for t in targets if t not in allowed]
    if bad:
        raise ActionError(f"a {item.kind} can't go to {', '.join(bad)}")
    item.targets = [t for t in allowed if t in targets]


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
def approve(item_id: str, *, targets: list[str] | None = None, publish_at: datetime | None = None,
            source: str = "dashboard") -> q.Item:
    """Approve (or reschedule). No platforms selected -> the item is rejected instead."""
    item = _get(item_id)
    _set_targets(item, targets)
    if not item.effective_targets:
        return reject(item_id, source=source, reason="no platforms selected", item=item)
    if publish_at is not None:
        if publish_at.tzinfo is None:
            raise ActionError("publish time needs a timezone")
        item.publish_at = publish_at.astimezone(IST).isoformat(timespec="seconds")
    _decide(item, "approve")
    q.upsert(item)
    approve_bot.mark_decided(item, approve_bot.decision_note("approve", item, f"from the {source}"))
    log.info("%s approved (%s) for %s -> %s", item.id, source, item.publish_at, item.effective_targets)
    activity.record("post.scheduled" if publish_at is not None else "post.approved",
                    f"Approved {item.kind} “{item.topic}” for {str(item.publish_at or 'the next slot')[:16].replace('T', ' ')} IST "
                    f"-> {', '.join(item.effective_targets)}", source=source, post_id=item.id,
                    detail={"targets": item.effective_targets, "publish_at": item.publish_at})
    return item


def reject(item_id: str, *, source: str = "dashboard", reason: str = "", item: q.Item | None = None) -> q.Item:
    item = item or _get(item_id)
    _decide(item, "reject")
    if reason:
        item.error = reason
    q.upsert(item)
    approve_bot.mark_decided(item, approve_bot.decision_note("reject", item, f"from the {source}"))
    log.info("%s rejected (%s)%s", item.id, source, f": {reason}" if reason else "")
    activity.record("post.rejected", f"Rejected {item.kind} “{item.topic}”" + (f" ({reason})" if reason else ""),
                    source=source, post_id=item.id)
    return item


def regenerate(item_ids: list[str], feedback: str = "", source: str = "dashboard") -> list[q.Item]:
    """Mark items for regeneration. Both formats of one topic -> one new shared script."""
    items = [_get(i) for i in item_ids]
    for item in items:
        _decide(item, "regen", feedback)
    for item in items:
        q.upsert(item)
        approve_bot.mark_decided(item, approve_bot.decision_note("regen", item, f"from the {source}"))
        activity.record("post.regenerate", f"Asked for a new version of {item.kind} “{item.topic}”",
                        source=source, post_id=item.id, detail={"feedback": feedback[:500]} if feedback else None)
    trigger_pipeline_run()
    return items


# --------------------------------------------------------------------------- #
# Edits
# --------------------------------------------------------------------------- #
def normalize_hashtags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for t in tags:
        for part in t.replace(",", " ").split():
            m = _TAG.match(part.strip())
            if not m:
                raise ActionError(f"invalid hashtag {part!r} (letters, digits and _ only)")
            tag = "#" + m.group(1)
            if tag.lower() not in (x.lower() for x in out):
                out.append(tag)
    if len(out) > HASHTAGS_MAX:
        raise ActionError(f"Instagram allows at most {HASHTAGS_MAX} hashtags")
    return out


def edit(item_id: str, *, caption: str | None = None, hashtags: list[str] | None = None,
         yt_title: str | None = None, yt_description: str | None = None,
         targets: list[str] | None = None) -> q.Item:
    item = _get(item_id)
    if item.status not in q.EDITABLE:
        raise ActionError(f"can't edit a {item.status} post")
    body, current_tags = split_caption(item.caption)
    body = body if caption is None else caption.strip()
    tags = current_tags if hashtags is None else normalize_hashtags(hashtags)
    if not body:
        raise ActionError("caption can't be empty")
    new_caption = body + ("\n\n" + " ".join(tags) if tags else "")
    if len(new_caption) > CAPTION_MAX:
        raise ActionError(f"caption + hashtags is {len(new_caption)} chars; Instagram's limit is {CAPTION_MAX}")
    item.caption = new_caption
    if yt_title is not None:  # "" = go back to the automatic title
        if len(yt_title.strip()) > TITLE_MAX:
            raise ActionError(f"YouTube titles are limited to {TITLE_MAX} characters")
        item.yt_title = yt_title.strip() or None
    if yt_description is not None:
        item.yt_description = yt_description.strip() or None
    _set_targets(item, targets)
    q.upsert(item)
    if item.status == "pending":
        approve_bot.refresh_preview(item)
    return item


# --------------------------------------------------------------------------- #
# Publishing (the API runs finish_publish in the background)
# --------------------------------------------------------------------------- #
def _require_publishing() -> None:
    if not publishing_enabled():
        raise ActionError("Publishing is turned off in this environment (PUBLISH_ENABLED=false)")


def publish_via_dispatch() -> bool:
    """True where the API can't publish itself (e.g. AWS Lambda freezes once a response is sent).

    Publishing then always happens in the GitHub Actions poll job -- the one publisher -- and the
    API just marks the post ready and kicks that job.
    """
    return (get_env("PUBLISH_VIA", required=False, default="inline") or "inline").lower() == "dispatch"


def start_publish_now(item_id: str, targets: list[str] | None = None, source: str = "dashboard") -> q.Item:
    """Approve for right now. Inline mode marks it publishing (call finish_publish() next); dispatch
    mode leaves it approved (slot = now) and starts the poll job, which publishes it."""
    _require_publishing()
    item = approve(item_id, targets=targets, publish_at=datetime.now(IST), source=source)
    if item.status != "approved":  # e.g. rejected because no platforms were selected
        return item
    if publish_via_dispatch():
        trigger_pipeline_run()  # if it can't start, the next scheduled poll publishes it
        return item
    item.status = "publishing"
    q.upsert(item)
    activity.record("publish.requested", f"Publish now: {item.kind} “{item.topic}”", source=source,
                    post_id=item.id, detail={"targets": item.effective_targets})
    return item


def start_retry(item_id: str, platform: str) -> q.Item:
    _require_publishing()
    item = _get(item_id)
    rec = item.platforms.get(platform, {})
    if rec.get("status") != "failed":
        raise ActionError(f"{platform.upper()} hasn't failed for this post")
    if item.status not in ("failed", "published"):
        raise ActionError(f"can't retry a {item.status} post")
    rec["attempts"] = 0  # a manual retry gets a fresh set of attempts
    activity.record("publish.retry", f"Retry {platform.upper()} for {item.kind} “{item.topic}”",
                    source="dashboard", post_id=item.id, detail={"platform": platform})
    if publish_via_dispatch():
        item.status = "failed"  # what publish_due() retries
        q.upsert(item)
        trigger_pipeline_run()
        return item
    item.status = "publishing"
    q.upsert(item)
    return item


def finish_publish(item_id: str, platforms: tuple[str, ...] = q.PLATFORMS) -> q.Item:
    from src.publish import publish_item
    item = _get(item_id)
    try:
        return publish_item(item, platforms=platforms)
    except Exception as e:  # noqa: BLE001 -- never leave an item stuck in "publishing"
        log.exception("publish %s crashed", item_id)
        activity.record("publish.crashed", f"Publishing crashed: {str(e)[:200]}", level="error", source="publisher",
                        post_id=item_id)
        item = _get(item_id)
        if item.status == "publishing":
            item.status, item.error = "failed", str(e)[:300]
            q.upsert(item)
        return item


# --------------------------------------------------------------------------- #
# Kick the GitHub Actions poll job (regeneration needs Chromium + FFmpeg, which run there)
# --------------------------------------------------------------------------- #
def trigger_pipeline_run(workflow: str = "poll-approvals.yml", inputs: dict | None = None) -> bool:
    from src.github_actions import repository
    token = get_env("GITHUB_DISPATCH_TOKEN", required=False)
    repo = repository()  # no default: never dispatch into a repository nobody configured
    if not token or not repo:
        log.info("%s not set; the next scheduled run will pick this up",
                 "GITHUB_DISPATCH_TOKEN" if not token else "GITHUB_REPOSITORY (owner/name)")
        return False
    r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"},
                      json={"ref": "main", **({"inputs": inputs} if inputs else {})}, timeout=20)
    if r.status_code != 204:
        log.warning("workflow dispatch failed: HTTP %s %s", r.status_code, redact(r.text[:200]))
        return False
    return True
