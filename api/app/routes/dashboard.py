"""Dashboard overview (read-only): one request, every widget.

GET /api/dashboard/overview?range=30|90&workspace=live|demo

Live: narrow-column reads of posts / generation_jobs / activity_log (never captions), aggregated by
src.dashboard_metrics. Demo: synthetic rows built in memory (src.dashboard_demo) and passed through the SAME
aggregator; the demo branch opens no database session at all. Nothing here writes, publishes, generates or
calls an outside service. Each source is read in its own session, so one failing table only blanks the
sections that need it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import and_, or_, select

from api.app.deps import CurrentUser, current_user
from api.app.ratelimit import RateLimiter
from api.app.settings import settings
from src import dashboard_demo, db
from src.config import get_env, load_brand
from src.dashboard_metrics import (APPROVAL_EVENTS, FEED_EVENTS, FEED_SIZE, Config, EventRow, JobRow, PostRow,
                                   aware, build_overview)
from src.db.models import ActivityLog, GenerationJob, Post

log = logging.getLogger("codexone.dashboard")
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

CACHE_SECONDS = 15
LIMIT_PER_MIN = 30
_limiter = RateLimiter()
_cache: dict[tuple, tuple[float, bytes, str]] = {}
_lock = threading.Lock()


def demo_enabled() -> bool:
    """DASHBOARD_DEMO_ENABLED wins; unset = on for local/dev (COOKIE_SECURE=false), off in production."""
    raw = get_env("DASHBOARD_DEMO_ENABLED", required=False)
    if raw is not None and raw.strip():
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return not settings().cookie_secure


def _config() -> Config:
    try:
        brand = load_brand() or {}
    except Exception:  # noqa: BLE001 -- a broken brand setting must not blank the page
        log.exception("dashboard: could not load the brand config")
        brand = {}
    weights = {str(k): float(v) for k, v in (brand.get("topics_weight") or {}).items()}
    slots = [str(s) for s in (brand.get("post_times_ist") or [])]
    from src.publish import MAX_ATTEMPTS  # noqa: PLC0415
    return Config(slots=slots, weights=weights, max_attempts=MAX_ATTEMPTS, handle=str(brand.get("handle") or ""),
                  demo_enabled=demo_enabled())


def _load_posts(now: datetime, days: int) -> list[PostRow] | None:
    since = now - timedelta(days=days + 8)
    cols = (Post.id, Post.kind, Post.group_id, Post.topic, Post.category, Post.status, Post.version, Post.publish_at,
            Post.created_at, Post.decided_at, Post.published_at, Post.updated_at, Post.attempts, Post.platforms,
            Post.error, Post.targets)
    stmt = select(*cols).where(or_(
        Post.created_at >= since,
        Post.status.in_(("pending", "approved", "publishing", "failed")),
        and_(Post.status == "expired", Post.updated_at >= now - timedelta(days=8)),
    ))
    try:
        with db.session() as s:
            return [PostRow(id=r.id, kind=r.kind, status=r.status, group_id=r.group_id or "", topic=r.topic or "",
                            category=r.category or "", version=r.version or 1, publish_at=r.publish_at,
                            created_at=r.created_at, decided_at=r.decided_at, published_at=r.published_at,
                            updated_at=r.updated_at, attempts=r.attempts or 0, error=r.error,
                            platforms=r.platforms if isinstance(r.platforms, dict) else {},
                            targets=r.targets if isinstance(r.targets, list) else None)
                    for r in s.execute(stmt)]
    except Exception:  # noqa: BLE001
        log.exception("dashboard: reading posts failed")
        return None


def _load_jobs(now: datetime) -> list[JobRow] | None:
    """The table is new and may not exist yet: that is 'unavailable', not an error."""
    try:
        with db.session() as s:
            stmt = select(GenerationJob.id, GenerationJob.status, GenerationJob.created_at, GenerationJob.trigger,
                          GenerationJob.failure_reason).where(GenerationJob.created_at >= now - timedelta(days=90))
            return [JobRow(id=r.id, status=r.status, created_at=r.created_at, trigger=r.trigger,
                           failure_reason=r.failure_reason) for r in s.execute(stmt)]
    except Exception:  # noqa: BLE001
        log.warning("dashboard: generation_jobs not readable (not migrated yet?)")
        return None


def _load_events(now: datetime, days: int) -> list[EventRow] | None:
    cols = (ActivityLog.id, ActivityLog.created_at, ActivityLog.event, ActivityLog.source, ActivityLog.level,
            ActivityLog.message, ActivityLog.post_id)
    try:
        with db.session() as s:
            feed = s.execute(select(*cols).where(ActivityLog.event.in_(sorted(FEED_EVENTS)))
                             .order_by(ActivityLog.id.desc()).limit(FEED_SIZE)).all()
            appr = s.execute(select(*cols).where(ActivityLog.event.in_(sorted(APPROVAL_EVENTS)),
                                                 ActivityLog.created_at >= now - timedelta(days=days + 1))
                             .order_by(ActivityLog.id.desc()).limit(1500)).all()
        seen: dict[int, EventRow] = {}
        for r in [*feed, *appr]:
            seen[r.id] = EventRow(id=r.id, created_at=r.created_at, event=r.event, source=r.source, level=r.level,
                                  message=r.message or "", post_id=r.post_id)
        return list(seen.values())
    except Exception:  # noqa: BLE001
        log.exception("dashboard: reading the activity log failed")
        return None


def _fill_thumbs(overview: dict) -> None:
    """First carousel slide of each recently shipped topic. Only https URLs are passed on."""
    sec = overview.get("recent_posts") or {}
    ids = [i["carousel_id"] for i in sec.get("items", []) if i.get("carousel_id")]
    if not ids:
        return
    try:
        with db.session() as s:
            media = dict(s.execute(select(Post.id, Post.media).where(Post.id.in_(ids))).all())
    except Exception:  # noqa: BLE001
        return
    for item in sec["items"]:
        slides = (media.get(item.get("carousel_id")) or {}).get("carousel") if isinstance(media.get(item.get("carousel_id")), dict) else None
        if isinstance(slides, list) and slides and isinstance(slides[0], str) and slides[0].startswith("https://"):
            item["thumb"] = slides[0]


def compute(workspace: str, days: int, now: datetime | None = None) -> dict:
    now = aware(now or datetime.now(timezone.utc))
    if workspace == "demo":
        posts, jobs, events, cfg = dashboard_demo.build_demo(now)   # no database access on this path
        return build_overview(posts, jobs, events, now=now, cfg=cfg, days=days, workspace="demo")
    cfg = _config()
    out = build_overview(_load_posts(now, days), _load_jobs(now), _load_events(now, days), now=now, cfg=cfg,
                         days=days, workspace="live")
    _fill_thumbs(out)
    return out


def _encode(payload: dict) -> tuple[bytes, str]:
    stable = {k: v for k, v in payload.items() if k != "generated_at"}
    etag = '"' + hashlib.sha1(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20] + '"'
    return json.dumps(payload, separators=(",", ":")).encode(), etag


@router.get("/overview")
def overview(request: Request, user: CurrentUser = Depends(current_user),
             range_: int = Query(30, alias="range"),
             workspace: Literal["live", "demo"] = "live") -> Response:
    if range_ not in (30, 90):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "range must be 30 or 90")
    if workspace == "demo" and not demo_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    key = f"dash:{user.id}"
    wait = _limiter.retry_after(key, LIMIT_PER_MIN, 60)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many refreshes. Try again in a moment.",
                            headers={"Retry-After": str(wait)})
    _limiter.hit(key)

    ck = (workspace, range_)
    with _lock:
        hit = _cache.get(ck)
    if not hit or time.monotonic() - hit[0] > CACHE_SECONDS:
        body, etag = _encode(compute(workspace, range_))
        hit = (time.monotonic(), body, etag)
        with _lock:
            _cache[ck] = hit
    _, body, etag = hit
    headers = {"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
