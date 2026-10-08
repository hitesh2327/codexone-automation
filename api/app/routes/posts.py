"""Posts: list/filter topic groups, inspect items, and act on them (approve, schedule, reject,
publish now, retry, regenerate, edit). All logic lives in src/ (actions, queue_store)."""
from __future__ import annotations

import base64
import json
from datetime import date, datetime, timezone

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


def _ts(value: str | datetime | None) -> float:
    """Sortable instant of an ISO string (full items) or a datetime (light rows); naive = UTC (SQLite)."""
    if value is None or value == "":
        return 0.0
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def _created(i) -> float:
    return _ts(i.created_dt if isinstance(i, q.Light) else i.created_at)


def _slot(i) -> float:
    if isinstance(i, q.Light) and i.publish_dt is not None:
        return _ts(i.publish_dt)
    return _ts(item_publish_at(i))


def _current(items: list) -> q.Item | None:
    """Newest version that hasn't been replaced (or simply the newest)."""
    live = [i for i in items if i.status != "replaced"] or items
    return max(live, key=lambda i: (i.version, _created(i))) if live else None


def _group_meta(items: list) -> list[dict]:
    """Per topic group: its current carousel/reel and sort key (numbers, no formatting). Newest first."""
    by_group: dict[str, list] = {}
    for i in items:
        by_group.setdefault(i.group_id, []).append(i)
    out = []
    for gid, members in by_group.items():
        current = {k: _current([m for m in members if m.kind == k]) for k in ("carousel", "reel")}
        head = current["reel"] or current["carousel"]
        out.append({"group_id": gid, "topic": head.topic, "category": head.category, "date": head.date,
                    "key": (_slot(head), max(_created(m) for m in members), gid),
                    "members": members, "current": current})
    return sorted(out, key=_order, reverse=True)


def _order(g: dict) -> tuple[float, float, str]:
    return g["key"]


def _groups(items: list[q.Item]) -> list[dict]:
    out = []
    for g in _group_meta(items):
        head = g["current"]["reel"] or g["current"]["carousel"]
        out.append({"group_id": g["group_id"], "topic": g["topic"], "category": g["category"], "date": g["date"],
                    "publish_at": item_publish_at(head).isoformat(),
                    "created_at": max(m.created_at for m in g["members"]),
                    "versions": max(m.version for m in g["members"]),
                    "items": {k: item_out(v) if v else None for k, v in g["current"].items()}})
    return out


# Pages of topic groups (QA-M-08: the full list grew without bound; at 50k posts it was 79 MB, past Lambda's 6 MB
# response limit). The default keeps today's page unchanged for ~100 days of posts (2 groups/day).
DEFAULT_GROUPS, MAX_GROUPS = 200, 500


def _cursor_out(g: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(list(_order(g))).encode()).decode()


def _cursor_in(raw: str) -> tuple[float, float, str]:
    try:
        key = json.loads(base64.urlsafe_b64decode(raw.encode()))
        if isinstance(key, list) and len(key) == 3 and all(isinstance(x, (int, float)) for x in key[:2]) \
                and isinstance(key[2], str):
            return float(key[0]), float(key[1]), key[2]
    except (ValueError, TypeError):
        pass
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid cursor")


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
@router.get("")
def list_posts(status_: str | None = Query(None, alias="status"), platform: str | None = None,
               category: str | None = None, date_from: date | None = None, date_to: date | None = None,
               search: str | None = Query(None, alias="q", max_length=100),
               limit: int = Query(DEFAULT_GROUPS, ge=1, le=MAX_GROUPS),
               cursor: str | None = Query(None, max_length=600)) -> dict:
    """Topic groups, newest first, `limit` per page; pass `next_cursor` back as `cursor` for the next page.
    Filters, counts and categories cover every post; only the page's groups are read in full."""
    groups = _group_meta(q.load_light())

    def keep(g: dict) -> bool:
        current = [i for i in g["current"].values() if i]
        if status_ and not any(i.status == status_ for i in current):
            return False
        if platform and not any(platform in i.effective_targets for i in current):
            return False
        if category and g["category"] != category:
            return False
        d = date.fromisoformat(g["date"])
        if (date_from and d < date_from) or (date_to and d > date_to):
            return False
        return not search or search.lower() in g["topic"].lower()

    counts: dict[str, int] = {}
    for g in groups:
        for i in g["current"].values():
            if i:
                counts[i.status] = counts.get(i.status, 0) + 1
    matching = [g for g in groups if keep(g)]
    total = len(matching)
    if cursor:
        after = _cursor_in(cursor)
        matching = [g for g in matching if _order(g) < after]
    page, more = matching[:limit], len(matching) > limit
    full = {g["group_id"]: g for g in _groups(q.load(group_ids=[g["group_id"] for g in page]))} if page else {}
    return {"groups": [full[g["group_id"]] for g in page if g["group_id"] in full],
            "categories": sorted({g["category"] for g in groups}),
            "counts": counts,
            "total": total,                                  # groups matching the filters, all pages
            "has_more": more, "next_cursor": _cursor_out(page[-1]) if more else None,
            "publishing_enabled": actions.publishing_enabled()}


@router.get("/{item_id}")
def get_post(item_id: str) -> dict:
    item = q.get(item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    history = sorted((i for i in q.load(group_ids=[item.group_id]) if i.kind == item.kind),
                     key=lambda i: i.version)
    return {"item": item_out(item),
            "history": [{"id": h.id, "version": h.version, "status": h.status, "created_at": h.created_at,
                         "feedback": h.feedback} for h in history]}


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def _run(fn, *args, **kwargs) -> dict:
    actions.take_dispatch_notice()  # start clean
    try:
        out = item_out(fn(*args, **kwargs))
    except actions.ActionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    if notice := actions.take_dispatch_notice():  # QA-M-01: the GitHub job couldn't be started
        out["notice"] = notice
    return out


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
    actions.take_dispatch_notice()
    try:
        items = actions.regenerate(body.item_ids, body.feedback)
    except actions.ActionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return {"items": [item_out(i) for i in items], "notice": actions.take_dispatch_notice()}


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
