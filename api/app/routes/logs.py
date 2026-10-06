"""Activity log (read-only): what happened, who did it. Written by src.activity.record()."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from src import db
from src.db.models import ActivityLog

router = APIRouter(prefix="/logs", tags=["logs"])
ESC = chr(92)  # LIKE escape character
IST = timezone(timedelta(hours=5, minutes=30))


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:  # SQLite hands back naive UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _out(r: ActivityLog) -> dict:
    return {"id": r.id, "created_at": _iso(r.created_at), "level": r.level, "source": r.source, "event": r.event,
            "message": r.message, "post_id": r.post_id, "actor": r.actor, "detail": r.detail}


def _like(text: str) -> str:
    return text.replace(ESC, ESC * 2).replace("%", ESC + "%").replace("_", ESC + "_")


@router.get("")
def list_logs(level: list[str] | None = Query(None), source: str | None = Query(None, max_length=24),
              event: str | None = Query(None, max_length=48), post_id: str | None = Query(None, max_length=160),
              q: str | None = Query(None, max_length=100), date_from: date | None = None, date_to: date | None = None,
              before_id: int | None = Query(None, ge=1), limit: int = Query(100, ge=1, le=500)) -> dict:
    """Newest first. Dates are IST calendar days. `level` may repeat. `facets` count the rows that match
    every filter except the facet's own, so the filter chips show what choosing them would give."""
    def conds(skip: str = "") -> list:
        c = []
        if level and skip != "level":
            c.append(ActivityLog.level.in_(level))
        if source and skip != "source":
            c.append(ActivityLog.source == source)
        if event:
            c.append(ActivityLog.event.like(_like(event) + "%", escape=ESC))
        if post_id:
            c.append(ActivityLog.post_id == post_id)
        if q:
            c.append(ActivityLog.message.ilike(f"%{_like(q)}%", escape=ESC))
        if date_from:
            c.append(ActivityLog.created_at >= datetime.combine(date_from, time.min, IST).astimezone(timezone.utc))
        if date_to:
            c.append(ActivityLog.created_at < datetime.combine(date_to + timedelta(days=1), time.min, IST)
                     .astimezone(timezone.utc))
        return c

    with db.session() as s:
        stmt = select(ActivityLog).where(*conds())
        if before_id:
            stmt = stmt.where(ActivityLog.id < before_id)
        rows = s.scalars(stmt.order_by(ActivityLog.id.desc()).limit(limit + 1)).all()
        more = len(rows) > limit
        rows = rows[:limit]
        facets = {
            "level": dict(s.execute(select(ActivityLog.level, func.count()).where(*conds("level"))
                                    .group_by(ActivityLog.level)).all()),
            "source": dict(s.execute(select(ActivityLog.source, func.count()).where(*conds("source"))
                                     .group_by(ActivityLog.source)).all()),
        }
        return {"items": [_out(r) for r in rows], "facets": facets,
                "next_before_id": rows[-1].id if more and rows else None}


@router.get("/summary")
def summary() -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    with db.session() as s:
        counts = dict(s.execute(select(ActivityLog.level, func.count()).where(ActivityLog.created_at >= since)
                                .group_by(ActivityLog.level)).all())
        last_error = s.scalars(select(ActivityLog).where(ActivityLog.level == "error")
                               .order_by(ActivityLog.id.desc()).limit(1)).first()
        last_publish = s.scalars(select(ActivityLog).where(ActivityLog.event == "post.published")
                                 .order_by(ActivityLog.id.desc()).limit(1)).first()
        return {"last_24h": {lv: counts.get(lv, 0) for lv in ("info", "warning", "error")},
                "last_error": _out(last_error) if last_error else None,
                "last_publish": _out(last_publish) if last_publish else None}
