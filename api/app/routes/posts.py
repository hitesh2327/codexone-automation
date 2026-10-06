"""Posts: list/filter topic groups, inspect items, and act on them (approve, schedule, reject,
publish now, retry, regenerate, edit). All logic lives in src/ (actions, queue_store)."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field

from src import actions, approve_bot
from src import queue_store as q
from src.approve_bot import item_publish_at
from src.publish_youtube import build_metadata, split_caption

router = APIRouter(prefix="/posts", tags=["posts"])

Platform = str  # "ig" | "yt"


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def item_out(item: q.Item) -> dict:
    body, tags = split_caption(item.caption)
    out = {
        "id": item.id, "kind": item.kind, "status": item.status, "version": item.version,
        "group_id": item.group_id, "topic": item.topic, "category": item.category, "date": item.date,
        "caption": body, "hashtags": tags, "caption_length": len(item.caption),
        "media": item.media, "publish_at": item_publish_at(item).isoformat(),
        "targets": item.effective_targets, "allowed_targets": q.DEFAULT_TARGETS[item.kind],
        "platforms": {p: {k: v for k, v in r.items() if k in ("status", "id", "url", "error", "at", "privacy")}
                      for p, r in item.platforms.items()},
        "feedback": item.feedback, "error": item.error, "voice": item.voice,
        "created_at": item.created_at, "decided_at": item.decided_at, "published_at": item.published_at,
        "editable": item.status in q.EDITABLE,
        "can": {a: item.status in allowed for a, allowed in q.DECIDABLE.items()},
        "source_url": item.source_url,
    }
    if item.kind == "reel":
        meta = build_metadata(item.caption, item.yt_title, item.yt_description)["snippet"]
        out["youtube"] = {"title": meta["title"], "description": meta["description"], "tags": meta["tags"],
                          "title_is_custom": bool(item.yt_title), "description_is_custom": bool(item.yt_description)}
    return out


def _current(items: list[q.Item]) -> q.Item | None:
    """Newest version that hasn't been replaced (or simply the newest)."""
    live = [i for i in items if i.status != "replaced"] or items
    return max(live, key=lambda i: (i.version, i.created_at)) if live else None


def _groups(items: list[q.Item]) -> list[dict]:
    by_group: dict[str, list[q.Item]] = {}
    for i in items:
        by_group.setdefault(i.group_id, []).append(i)
    out = []
    for gid, members in by_group.items():
        current = {k: _current([m for m in members if m.kind == k]) for k in ("carousel", "reel")}
        head = current["reel"] or current["carousel"]
        out.append({
            "group_id": gid, "topic": head.topic, "category": head.category, "date": head.date,
            "publish_at": item_publish_at(head).isoformat(),
            "created_at": max(m.created_at for m in members),
            "versions": max(m.version for m in members),
            "items": {k: item_out(v) if v else None for k, v in current.items()},
        })
    return sorted(out, key=lambda g: (g["publish_at"], g["created_at"]), reverse=True)


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
@router.get("")
def list_posts(status_: str | None = Query(None, alias="status"), platform: str | None = None,
               category: str | None = None, date_from: date | None = None, date_to: date | None = None,
               search: str | None = Query(None, alias="q", max_length=100)) -> dict:
    items = q.load()
    groups = _groups(items)

    def keep(g: dict) -> bool:
        current = [i for i in g["items"].values() if i]
        if status_ and not any(i["status"] == status_ for i in current):
            return False
        if platform and not any(platform in i["targets"] for i in current):
            return False
        if category and g["category"] != category:
            return False
        d = date.fromisoformat(g["date"])
        if (date_from and d < date_from) or (date_to and d > date_to):
            return False
        return not search or search.lower() in g["topic"].lower()

    counts: dict[str, int] = {}
    for g in groups:
        for i in g["items"].values():
            if i:
                counts[i["status"]] = counts.get(i["status"], 0) + 1
    return {"groups": [g for g in groups if keep(g)],
            "categories": sorted({g["category"] for g in groups}),
            "counts": counts,
            "publishing_enabled": actions.publishing_enabled()}


@router.get("/{item_id}")
def get_post(item_id: str) -> dict:
    item = q.get(item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    history = sorted((i for i in q.load() if i.group_id == item.group_id and i.kind == item.kind),
                     key=lambda i: i.version)
    return {"item": item_out(item),
            "history": [{"id": h.id, "version": h.version, "status": h.status, "created_at": h.created_at,
                         "feedback": h.feedback} for h in history]}


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def _run(fn, *args, **kwargs) -> dict:
    try:
        return item_out(fn(*args, **kwargs))
    except actions.ActionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


class TargetsBody(BaseModel):
    targets: list[Platform] | None = None


class ScheduleBody(BaseModel):
    publish_at: datetime                      # ISO with offset, e.g. 2026-09-29T19:00:00+05:30
    targets: list[Platform] | None = None


class EditBody(BaseModel):
    caption: str | None = Field(None, max_length=2200)
    hashtags: list[str] | None = Field(None, max_length=40)
    yt_title: str | None = Field(None, max_length=200)
    yt_description: str | None = Field(None, max_length=5000)
    targets: list[Platform] | None = None


class RetryBody(BaseModel):
    platform: Platform


class RegenerateBody(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=2)
    feedback: str = Field("", max_length=2000)


@router.patch("/{item_id}")
def edit_post(item_id: str, body: EditBody) -> dict:
    return _run(actions.edit, item_id, **body.model_dump())


@router.post("/{item_id}/approve")
def approve_post(item_id: str, body: TargetsBody) -> dict:
    """Approve for its scheduled slot (publishes at the next check after that time)."""
    return _run(actions.approve, item_id, targets=body.targets)


@router.post("/{item_id}/schedule")
def schedule_post(item_id: str, body: ScheduleBody) -> dict:
    if body.publish_at.tzinfo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "publish_at needs a timezone offset")
    return _run(actions.approve, item_id, targets=body.targets, publish_at=body.publish_at)


@router.post("/{item_id}/reject")
def reject_post(item_id: str) -> dict:
    return _run(actions.reject, item_id)


@router.post("/{item_id}/publish-now")
def publish_now(item_id: str, body: TargetsBody, background: BackgroundTasks) -> dict:
    out = _run(actions.start_publish_now, item_id, targets=body.targets)
    if out["status"] == "publishing":  # inline mode; in dispatch mode the poll job publishes
        background.add_task(actions.finish_publish, item_id)
    return out


@router.post("/{item_id}/retry")
def retry_post(item_id: str, body: RetryBody, background: BackgroundTasks) -> dict:
    out = _run(actions.start_retry, item_id, body.platform)
    if out["status"] == "publishing":
        background.add_task(actions.finish_publish, item_id, (body.platform,))
    return out


@router.post("/regenerate")
def regenerate(body: RegenerateBody) -> dict:
    try:
        items = actions.regenerate(body.item_ids, body.feedback)
    except actions.ActionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return {"items": [item_out(i) for i in items]}


@router.post("/sync-telegram")
def sync_telegram() -> dict:
    """Apply Telegram button presses now (same code + offset as the scheduled poll)."""
    if not approve_bot.sync_enabled():
        return {"enabled": False, "changes": []}
    try:
        changes = approve_bot.poll()
    except Exception as e:  # noqa: BLE001 -- Telegram being down must not break the page
        return {"enabled": True, "changes": [], "error": str(e)[:200]}
    return {"enabled": True, "changes": [{"id": i, "change": c} for i, c in changes]}
