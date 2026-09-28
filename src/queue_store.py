"""Approval queue + publishing history.

Storage: Postgres when DATABASE_URL is set (tables `posts`, `posted_topics`), otherwise
the JSON files data/queue.json and data/posted.json. Callers use the same functions
either way.

One item per publishable post (carousel and reel are approved independently).
Status flow:  pending → approved → published
                      → rejected
                      → regenerate → (new pending item; old one becomes "replaced")
              approved → failed (publish error; retried on the next poll)
              pending  → expired (no decision within EXPIRE_HOURS)
"""
from __future__ import annotations

import hashlib
import json
from datetime import date as date_cls, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field

from src import db
from src.config import DATA_DIR, POSTED_FILE

QUEUE_FILE = DATA_DIR / "queue.json"
IST = timezone(timedelta(hours=5, minutes=30))
Status = Literal["pending", "approved", "rejected", "regenerate", "replaced", "published", "failed",
                 "expired"]
Kind = Literal["carousel", "reel"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Item(BaseModel):
    id: str
    kind: Kind
    date: str
    topic: str
    category: str
    source_url: str = ""
    angle: str = ""
    post_dir: str                          # relative to project root (v2+ in <slug>/v<n>-<kind>/)
    caption: str                           # full IG caption incl. hashtags
    media: dict = Field(default_factory=dict)
    status: Status = "pending"
    publish_at: str | None = None          # ISO time (IST) of the slot this post is for
    voice: str = ""                        # reels: edge-tts voice used
    version: int = 1
    feedback: str = ""                     # text reply in Telegram → used by Regenerate
    tg_message_ids: list[int] = Field(default_factory=list)
    tg_control_id: int | None = None
    created_at: str = Field(default_factory=now_iso)
    decided_at: str | None = None
    published_at: str | None = None
    ig_media_id: str | None = None
    # Per-platform results: {"ig"|"yt": {"status": published|failed|skipped, "id", "url", "error", "at"}}
    platforms: dict = Field(default_factory=dict)
    error: str | None = None
    attempts: int = 0


def make_id(date: str, kind: str, slug: str, version: int = 1) -> str:
    h = hashlib.sha1(f"{slug}:{version}".encode()).hexdigest()[:6]
    return f"{date.replace('-', '')}-{kind[0]}-{h}"  # short: fits Telegram's 64-byte callback_data


# --------------------------------------------------------------------------- #
# Item <-> row conversion (DB stores real timestamps; Item keeps ISO strings)
# --------------------------------------------------------------------------- #
_TS_FIELDS = ("created_at", "decided_at", "published_at")


def _parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _iso(value: datetime | None, tz: timezone = timezone.utc) -> str | None:
    return value.astimezone(tz).isoformat(timespec="seconds") if value else None


def _to_row_values(item: Item) -> dict:
    d = item.model_dump()
    d["date"] = date_cls.fromisoformat(item.date)
    d["publish_at"] = _parse_ts(item.publish_at)
    for f in _TS_FIELDS:
        d[f] = _parse_ts(d[f])
    return d


def _from_row(row) -> Item:
    d = {c: getattr(row, c) for c in Item.model_fields}
    d["date"] = row.date.isoformat()
    d["publish_at"] = _iso(row.publish_at, IST)  # slots are IST; keep them IST for display/compare
    for f in _TS_FIELDS:
        d[f] = _iso(getattr(row, f))
    return Item.model_validate(d)


# --------------------------------------------------------------------------- #
# Queue
# --------------------------------------------------------------------------- #
def load() -> list[Item]:
    if db.enabled():
        from sqlalchemy import select
        from src.db.models import Post
        with db.session() as s:
            return [_from_row(r) for r in s.scalars(select(Post).order_by(Post.created_at))]
    if not QUEUE_FILE.exists():
        return []
    return [Item.model_validate(x) for x in json.loads(QUEUE_FILE.read_text(encoding="utf-8") or "[]")]


def save(items: list[Item]) -> None:
    """Persist these items. DB: upserts them (other rows untouched). Files: rewrites the queue."""
    if db.enabled():
        from src.db.models import Post
        with db.session() as s:
            for item in items:
                s.merge(Post(**_to_row_values(item)))
        return
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps([i.model_dump() for i in items], indent=2, ensure_ascii=False),
                          encoding="utf-8")


def upsert(item: Item) -> None:
    if db.enabled():
        save([item])
        return
    items = [i for i in load() if i.id != item.id]
    items.append(item)
    save(items)


def get(item_id: str) -> Item | None:
    if db.enabled():
        from src.db.models import Post
        with db.session() as s:
            row = s.get(Post, item_id)
            return _from_row(row) if row else None
    return next((i for i in load() if i.id == item_id), None)


# --------------------------------------------------------------------------- #
# Publishing history
# --------------------------------------------------------------------------- #
def _posted_entry(item: Item) -> dict:
    return {"id": item.id, "title": item.topic, "url": item.source_url, "category": item.category,
            "kind": item.kind, "ig_media_id": item.ig_media_id, "date": item.date,
            "published_at": item.published_at,
            "platforms": {p: {k: v for k, v in r.items() if k in ("status", "id", "url", "error", "at")}
                          for p, r in item.platforms.items()}}


def record_posted(item: Item) -> None:
    """Upsert this item's publishing record (per-platform status), so fetch_topics never
    suggests the topic again and every platform's outcome is on record."""
    entry = _posted_entry(item)
    if db.enabled():
        from sqlalchemy import select
        from src.db.models import PostedTopic
        with db.session() as s:
            row = s.scalars(select(PostedTopic).where(PostedTopic.item_id == item.id)).first()
            values = dict(item_id=item.id, title=entry["title"], url=entry["url"] or "",
                          category=entry["category"], kind=entry["kind"],
                          date=date_cls.fromisoformat(item.date), ig_media_id=entry["ig_media_id"],
                          published_at=_parse_ts(entry["published_at"]), platforms=entry["platforms"])
            if row:
                for k, v in values.items():
                    setattr(row, k, v)
            else:
                s.add(PostedTopic(**values))
        return
    posted = json.loads(POSTED_FILE.read_text(encoding="utf-8") or "[]") if POSTED_FILE.exists() else []
    posted = [e for e in posted if e.get("id") != item.id] + [entry]
    POSTED_FILE.write_text(json.dumps(posted, indent=2, ensure_ascii=False), encoding="utf-8")


def posted_entries() -> list[dict]:
    """Publishing history, oldest first, as dicts shaped like data/posted.json entries."""
    if db.enabled():
        from sqlalchemy import select
        from src.db.models import PostedTopic
        with db.session() as s:
            rows = s.scalars(select(PostedTopic).order_by(PostedTopic.created_at, PostedTopic.id)).all()
            return [{"id": r.item_id, "title": r.title, "url": r.url, "category": r.category,
                     "kind": r.kind, "ig_media_id": r.ig_media_id,
                     "date": r.date.isoformat() if r.date else None,
                     "published_at": _iso(r.published_at), "platforms": r.platforms or {}} for r in rows]
    if not POSTED_FILE.exists():
        return []
    try:
        return json.loads(POSTED_FILE.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError:
        return []
