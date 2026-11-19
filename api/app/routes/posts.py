"""Posts: list/filter topic groups, inspect items, and act on them (approve, schedule, reject,
publish now, retry, regenerate, edit). All logic lives in src/ (actions, queue_store)."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import zipfile
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from api.app.deps import CurrentUser, current_user
from api.app.routes.generate import require_admin
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
        "feedback": item.feedback, "error": item.error, "voice": item.voice, "language": item.language,
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
        current = {k: _current([m for m in members if m.kind == k]) for k in ("carousel", "image", "reel")}
        head = current["reel"] or current["carousel"] or current["image"]
        out.append({"group_id": gid, "topic": head.topic, "category": head.category, "date": head.date,
                    "key": (_slot(head), max(_created(m) for m in members), gid),
                    "members": members, "current": current})
    return sorted(out, key=_order, reverse=True)


def _order(g: dict) -> tuple[float, float, str]:
    return g["key"]


def _groups(items: list[q.Item]) -> list[dict]:
    out = []
    for g in _group_meta(items):
        head = g["current"]["reel"] or g["current"]["carousel"] or g["current"]["image"]
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
def _require_post(item_id: str, user: CurrentUser) -> q.Item:
    effective_uid = None if user.role in ("owner", "admin") else user.id
    item = q.get(item_id, user_id=effective_uid)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return item


@router.get("")
def list_posts(status_: str | None = Query(None, alias="status"), platform: str | None = None,
               category: str | None = None, date_from: date | None = None, date_to: date | None = None,
               search: str | None = Query(None, alias="q", max_length=100),
               limit: int = Query(DEFAULT_GROUPS, ge=1, le=MAX_GROUPS),
               offset: int = Query(0, ge=0),
               cursor: str | None = Query(None, max_length=600),
               all_users: bool = Query(False),
               user: CurrentUser = Depends(current_user)) -> dict:
    """Topic groups, newest first, `limit` per page; pass `next_cursor` back as `cursor` (or `offset`) for the next page.
    Filters, counts and categories cover every post; only the page's groups are read in full."""
    effective_uid = None if (all_users and user.role in ("owner", "admin")) else user.id
    groups = _group_meta(q.load_light(user_id=effective_uid))

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
        offset = 0
    page = matching[offset : offset + limit]
    more = len(matching) > offset + limit
    full = {g["group_id"]: g for g in _groups(q.load(group_ids=[g["group_id"] for g in page], user_id=effective_uid))} if page else {}
    return {"groups": [full[g["group_id"]] for g in page if g["group_id"] in full],
            "categories": sorted({g["category"] for g in groups}),
            "counts": counts,
            "total": total,                                  # groups matching the filters, all pages
            "has_more": more, "next_cursor": _cursor_out(page[-1]) if more else None,
            "publishing_enabled": actions.publishing_enabled()}


@router.get("/{item_id}")
def get_post(item_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    item = _require_post(item_id, user)
    effective_uid = None if user.role in ("owner", "admin") else user.id
    history = sorted((i for i in q.load(group_ids=[item.group_id], user_id=effective_uid) if i.kind == item.kind),
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
def edit_post(item_id: str, body: EditBody, user: CurrentUser = Depends(current_user)) -> dict:
    _require_post(item_id, user)
    return _run(actions.edit, item_id, **body.model_dump())


@router.post("/{item_id}/approve")
def approve_post(item_id: str, body: TargetsBody, user: CurrentUser = Depends(current_user)) -> dict:
    """Approve for its scheduled slot (publishes at the next check after that time)."""
    _require_post(item_id, user)
    return _run(actions.approve, item_id, targets=body.targets)


@router.post("/{item_id}/schedule")
def schedule_post(item_id: str, body: ScheduleBody, user: CurrentUser = Depends(current_user)) -> dict:
    _require_post(item_id, user)
    if body.publish_at.tzinfo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "publish_at needs a timezone offset")
    return _run(actions.approve, item_id, targets=body.targets, publish_at=body.publish_at)


@router.post("/{item_id}/reject")
def reject_post(item_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    _require_post(item_id, user)
    return _run(actions.reject, item_id)


@router.post("/{item_id}/publish-now")
def publish_now(item_id: str, body: TargetsBody, background: BackgroundTasks, user: CurrentUser = Depends(current_user)) -> dict:
    _require_post(item_id, user)
    out = _run(actions.start_publish_now, item_id, targets=body.targets)
    if out["status"] == "publishing":  # inline mode; in dispatch mode the poll job publishes
        background.add_task(actions.finish_publish, item_id)
    return out


@router.post("/{item_id}/retry")
def retry_post(item_id: str, body: RetryBody, background: BackgroundTasks, user: CurrentUser = Depends(current_user)) -> dict:
    _require_post(item_id, user)
    out = _run(actions.start_retry, item_id, body.platform)
    if out["status"] == "publishing":
        background.add_task(actions.finish_publish, item_id, (body.platform,))
    return out


@router.post("/regenerate")
def regenerate(body: RegenerateBody, user: CurrentUser = Depends(current_user)) -> dict:
    for item_id in body.item_ids:
        _require_post(item_id, user)
    actions.take_dispatch_notice()
    try:
        items = actions.regenerate(body.item_ids, body.feedback)
    except actions.ActionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return {"items": [item_out(i) for i in items], "notice": actions.take_dispatch_notice()}


@router.post("/sync-telegram", dependencies=[Depends(require_admin)])
def sync_telegram() -> dict:
    """Apply Telegram button presses now (same code + offset as the scheduled poll)."""
    if not approve_bot.sync_enabled():
        return {"enabled": False, "changes": []}
    try:
        changes = approve_bot.poll()
    except Exception as e:  # noqa: BLE001 -- Telegram being down must not break the page
        return {"enabled": True, "changes": [], "error": str(e)[:200]}
    return {"enabled": True, "changes": [{"id": i, "change": c} for i, c in changes]}


# --------------------------------------------------------------------------- #
# Web Download Mode (MNT-105): SSRF-safe Media Proxy & ZIP Carousel Bundling
# --------------------------------------------------------------------------- #
def _validate_media_url(raw_url: str) -> None:
    if not raw_url or not isinstance(raw_url, str):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing media URL")
    try:
        parts = urlsplit(raw_url)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid media URL")
    if parts.scheme != "https":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insecure media URL scheme")
    if parts.username or parts.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Userinfo not permitted in media URL")
    if parts.port not in (None, 443):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Non-standard port in media URL")
    host = (parts.hostname or "").lower()
    if not (host == "res.cloudinary.com" or host.endswith(".cloudinary.com")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Host not permitted for media download")


def _resolve_media_url(item: q.Item, media_key: str, slide_index: int = 0) -> tuple[str, str]:
    """Returns (url, filename)."""
    media = item.media or {}
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", item.id).strip("_") or "post"
    if media_key == "reel":
        url = media.get("reel") or media.get("image_reel")
        ext = "mp4"
        fname = f"{slug}-reel.{ext}"
    elif media_key in ("cover", "image_cover"):
        url = media.get(media_key) or media.get("cover")
        ext = "png"
        fname = f"{slug}-cover.{ext}"
    elif media_key == "carousel":
        slides = media.get("carousel") or []
        if isinstance(slides, list) and 0 <= slide_index < len(slides):
            url = slides[slide_index]
        else:
            url = media.get("cover")
        ext = "png" if str(url or "").endswith(".png") else "jpg"
        fname = f"{slug}-slide-{slide_index+1:02d}.{ext}"
    else:
        url = media.get(media_key)
        ext = "png"
        fname = f"{slug}-{media_key}.{ext}"

    if not url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Media '{media_key}' not found on this post")
    return url, fname


@router.get("/{item_id}/download-media")
async def download_media(
    item_id: str,
    media_key: str = Query("reel", pattern="^(reel|cover|image_reel|image_cover|carousel)$"),
    slide_index: int = Query(0, ge=0, le=30),
    user: CurrentUser = Depends(current_user),
):
    item = _require_post(item_id, user)
    url, filename = _resolve_media_url(item, media_key, slide_index)
    _validate_media_url(url)

    async def stream_chunks():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Failed to fetch upstream media")
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    ctype = "video/mp4" if filename.endswith(".mp4") else ("image/png" if filename.endswith(".png") else "image/jpeg")
    return StreamingResponse(
        stream_chunks(),
        media_type=ctype,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/{item_id}/download-zip")
async def download_carousel_zip(
    item_id: str,
    user: CurrentUser = Depends(current_user),
):
    item = _require_post(item_id, user)
    media = item.media or {}
    slides = media.get("carousel") or []
    if not isinstance(slides, list) or not slides:
        cover = media.get("cover")
        slides = [cover] if cover else []
    if not slides:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No carousel slide media found on this post")

    for url in slides:
        _validate_media_url(url)

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        tasks = [client.get(u) for u in slides]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", item.id).strip("_") or "post"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, resp in enumerate(responses):
            if isinstance(resp, Exception) or resp.status_code != 200:
                continue
            ext = "png" if slides[idx].endswith(".png") else "jpg"
            zf.writestr(f"slide_{idx+1:02d}.{ext}", resp.content)
        caption_text = (item.caption or "").strip()
        zf.writestr("caption.txt", caption_text.encode("utf-8"))

    zip_bytes = buf.getvalue()
    zip_filename = f"{slug}-carousel.zip"
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )

