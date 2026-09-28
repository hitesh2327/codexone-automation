"""Approval queue persisted in data/queue.json (committed back to the repo in CI).

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
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from src.config import DATA_DIR, POSTED_FILE

QUEUE_FILE = DATA_DIR / "queue.json"
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
    post_dir: str                          # relative to project root (v2+ in <slug>/v<n>/)
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
    error: str | None = None
    attempts: int = 0


def make_id(date: str, kind: str, slug: str, version: int = 1) -> str:
    h = hashlib.sha1(f"{slug}:{version}".encode()).hexdigest()[:6]
    return f"{date.replace('-', '')}-{kind[0]}-{h}"  # short: fits Telegram's 64-byte callback_data


def load() -> list[Item]:
    if not QUEUE_FILE.exists():
        return []
    return [Item.model_validate(x) for x in json.loads(QUEUE_FILE.read_text(encoding="utf-8") or "[]")]


def save(items: list[Item]) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps([i.model_dump() for i in items], indent=2, ensure_ascii=False),
                          encoding="utf-8")


def upsert(item: Item) -> None:
    items = [i for i in load() if i.id != item.id]
    items.append(item)
    save(items)


def get(item_id: str) -> Item | None:
    return next((i for i in load() if i.id == item_id), None)


def record_posted(item: Item) -> None:
    """Append to data/posted.json so fetch_topics never suggests this topic again."""
    posted = json.loads(POSTED_FILE.read_text(encoding="utf-8") or "[]") if POSTED_FILE.exists() else []
    posted.append({"title": item.topic, "url": item.source_url, "category": item.category,
                   "kind": item.kind, "ig_media_id": item.ig_media_id, "date": item.date,
                   "published_at": item.published_at})
    POSTED_FILE.write_text(json.dumps(posted, indent=2, ensure_ascii=False), encoding="utf-8")
