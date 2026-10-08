"""Approval queue + publishing history.

Storage: Postgres when DATABASE_URL is set (tables `posts`, `posted_topics`), otherwise
the JSON files data/queue.json and data/posted.json. Callers use the same functions
either way.

One item per publishable post (carousel and reel are approved independently).
Status flow:  pending → approved → publishing → published
                      → rejected
                      → regenerate → (new pending item; old one becomes "replaced")
              approved → failed (publish error; retried on the next poll)
              pending  → expired (no decision within EXPIRE_HOURS)
              expired  → approved (revived from the dashboard: schedule or approve it again)
              approved → publishing (dashboard "publish now" in progress) → published | failed
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date as date_cls, datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Literal, get_args

from pydantic import BaseModel, Field, ValidationError

from src import db
from src.config import DATA_DIR, POSTED_FILE

QUEUE_FILE = DATA_DIR / "queue.json"
log = logging.getLogger("codexone.queue")
IST = timezone(timedelta(hours=5, minutes=30))
Status = Literal["pending", "approved", "publishing", "rejected", "regenerate", "replaced",
                 "published", "failed", "expired"]
PLATFORMS = ("ig", "yt")
DEFAULT_TARGETS = {"reel": ["ig", "yt"], "carousel": ["ig"]}
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
    group_id: str = ""                     # "<date>/<slug>": a topic's carousel + reel + regenerations
    targets: list[str] | None = None       # platforms to publish to; None = DEFAULT_TARGETS[kind]
    yt_title: str | None = None            # YouTube overrides (else built from the caption)
    yt_description: str | None = None

    def model_post_init(self, _ctx) -> None:
        if not self.group_id:
            self.group_id = group_of(self.post_dir, self.date)

    @property
    def effective_targets(self) -> list[str]:
        allowed = DEFAULT_TARGETS[self.kind]
        return [p for p in (self.targets if self.targets is not None else allowed) if p in allowed]


def group_of(post_dir: str, day: str = "") -> str:
    """output/<date>/<slug>[/v2-reel] -> "<date>/<slug>"."""
    parts = [p for p in post_dir.replace("\\", "/").split("/") if p]
    if "output" in parts and len(parts) > parts.index("output") + 2:
        i = parts.index("output")
        return f"{parts[i + 1]}/{parts[i + 2]}"
    return f"{day}/{parts[-1] if parts else 'post'}"


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
def _valid_items(rows, convert) -> list[Item]:
    """Convert rows one by one: a single row the code can't read (e.g. a status written by a newer version, or
    by hand) is skipped with a warning instead of failing every page and the poll job (QA-L-12)."""
    out: list[Item] = []
    for r in rows:
        try:
            out.append(convert(r))
        except (ValidationError, ValueError, TypeError, AttributeError) as e:
            rid = getattr(r, "id", None) or (r.get("id") if isinstance(r, dict) else None)
            log.warning("skipping unreadable post %s: %s", rid, str(e).splitlines()[0][:200])
    return out


def load(statuses: tuple[str, ...] | None = None, group_ids: list[str] | None = None) -> list[Item]:
    """Queue items, oldest first. `statuses` / `group_ids` narrow it in the query (QA-M-08: the table grows forever,
    so request paths read only what they need)."""
    if db.enabled():
        from sqlalchemy import select
        from src.db.models import Post
        stmt = select(Post).order_by(Post.created_at)
        if statuses is not None:
            stmt = stmt.where(Post.status.in_(statuses))
        if group_ids is not None:
            stmt = stmt.where(Post.group_id.in_(group_ids))
        with db.session() as s:
            return _valid_items(s.scalars(stmt), _from_row)
    if not QUEUE_FILE.exists():
        return []
    items = _valid_items(json.loads(QUEUE_FILE.read_text(encoding="utf-8") or "[]"), Item.model_validate)
    return [i for i in items if (statuses is None or i.status in statuses)
            and (group_ids is None or i.group_id in group_ids)]


def load_window(start: datetime, end: datetime) -> list[Item]:
    """Items whose slot (publish_at) is within [start, end]."""
    if db.enabled():
        from sqlalchemy import select
        from src.db.models import Post
        with db.session() as s:
            return _valid_items(s.scalars(select(Post).where(Post.publish_at >= start, Post.publish_at <= end)
                                          .order_by(Post.created_at)), _from_row)
    return [i for i in load() if i.publish_at and start <= datetime.fromisoformat(i.publish_at) <= end]


_LIGHT = ("id", "kind", "date", "topic", "category", "status", "version", "publish_at", "created_at", "group_id",
          "targets", "post_dir")
_STATUSES = frozenset(get_args(Status))


@dataclass(slots=True)
class Light:
    """The few fields the Posts list groups, sorts, filters and counts by (no captions, media, platform records).
    Duck-types the Item attributes those code paths read; timestamps are converted only when used."""
    id: str
    kind: str
    date: str
    topic: str
    category: str
    status: str
    version: int
    publish_dt: datetime | None
    created_dt: datetime | None
    group_id: str
    targets: list[str] | None

    @property
    def publish_at(self) -> str | None:
        return _iso(self.publish_dt, IST)

    @property
    def created_at(self) -> str:
        return _iso(self.created_dt) or ""

    @property
    def effective_targets(self) -> list[str]:
        allowed = DEFAULT_TARGETS.get(self.kind, [])
        return [p for p in (self.targets if self.targets is not None else allowed) if p in allowed]


def load_light() -> list[Light]:
    """Every item, light (QA-M-08: the Posts list pages over these and reads full items only for its page)."""
    if not db.enabled():
        return load()  # type: ignore[return-value] -- file mode is small; full items have the same attributes
    from sqlalchemy import select
    from src.db.models import Post

    def convert(r) -> Light:
        if r.status not in _STATUSES or r.kind not in DEFAULT_TARGETS:
            raise ValueError(f"unknown status/kind {r.status!r}/{r.kind!r}")
        return Light(r.id, r.kind, r.date.isoformat(), r.topic or "", r.category or "", r.status, r.version or 1,
                     r.publish_at, r.created_at, r.group_id or group_of(r.post_dir or "", r.date.isoformat()),
                     r.targets if isinstance(r.targets, list) else None)
    with db.session() as s:
        return _valid_items(s.execute(select(*(getattr(Post, c) for c in _LIGHT)).order_by(Post.created_at)), convert)


def recent_topic_rows(limit: int) -> list[tuple[str, str]]:
    """(title, date) of the newest posts, then of the newest publishing records; newest first, bounded."""
    if db.enabled():
        from sqlalchemy import select
        from src.db.models import Post, PostedTopic
        with db.session() as s:
            posts = s.execute(select(Post.topic, Post.date).order_by(Post.created_at.desc()).limit(limit * 3)).all()
            hist = s.execute(select(PostedTopic.title, PostedTopic.date)
                             .order_by(PostedTopic.created_at.desc(), PostedTopic.id.desc()).limit(limit * 3)).all()
        return [(t or "", d.isoformat() if d else "") for t, d in [*posts, *hist]]
    rows = [(i.topic, i.date) for i in sorted(load(), key=lambda i: i.created_at, reverse=True)]
    return rows + [(p.get("title", ""), p.get("date") or "") for p in reversed(posted_entries())]


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


def update_if(item: Item, from_status: str | tuple[str, ...]) -> bool:
    """Write this item only if its stored status is still one of `from_status` (compare-and-set).

    Every read-modify-write that changes a status goes through here, so a stale copy can never
    overwrite what another process did meanwhile (e.g. put an item a publisher has just claimed
    back to "approved", which would publish it twice). Returns False, writing nothing, if the
    row's status changed (or the row is gone).
    """
    allowed = (from_status,) if isinstance(from_status, str) else tuple(from_status)
    if db.enabled():
        from sqlalchemy import update
        from src.db.models import Post
        values = _to_row_values(item)
        values.pop("id")
        with db.session() as s:
            result = s.execute(update(Post).where(Post.id == item.id, Post.status.in_(allowed)).values(**values))
            return result.rowcount == 1
    items = load()
    current = next((i for i in items if i.id == item.id), None)
    if current is None or current.status not in allowed:
        return False
    save([item if i.id == item.id else i for i in items])
    return True


def get(item_id: str) -> Item | None:
    if db.enabled():
        from src.db.models import Post
        with db.session() as s:
            row = s.get(Post, item_id)
            found = _valid_items([row], _from_row) if row else []
            return found[0] if found else None
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


# --------------------------------------------------------------------------- #
# Concurrency: only one publisher may publish an item
# --------------------------------------------------------------------------- #
CLAIMABLE = ("approved", "failed")


PUBLISHABLE = ("approved", "failed", "published")  # "published": complete a platform that failed/was added


def claim_for_publish(item_id: str, from_status: tuple[str, ...] = CLAIMABLE) -> bool:
    """Atomically take ownership of an item for publishing.

    Two publishers can run at once (a scheduled poll and a manual/dashboard publish), and
    Instagram happily accepts the same post twice. This flips <from_status> -> publishing
    in a single UPDATE; only the caller that changes a row may publish. A crash leaves the
    item in "publishing", which expire_stale() recovers. "publishing" itself is never
    claimable: whoever holds it is the publisher.
    """
    allowed = tuple(s for s in from_status if s in PUBLISHABLE)
    if not allowed:
        return False
    if not db.enabled():  # file mode: a single process, but keep the same state rule
        item = get(item_id)
        if not item or item.status not in allowed:
            return False
        item.status = "publishing"
        upsert(item)
        return True
    from sqlalchemy import update
    from src.db.models import Post
    with db.session() as s:
        result = s.execute(
            update(Post)
            .where(Post.id == item_id, Post.status.in_(allowed))
            .values(status="publishing")
        )
        return result.rowcount == 1


def release_stuck_publishing(minutes: int, dry_run: bool = False) -> list[str]:
    """Release items left in "publishing" by a crashed publisher, so they can be retried.

    Uses the row's own updated_at (set when it was claimed), so a publish that is genuinely
    still running is never taken away from it.
    """
    if not db.enabled():
        return []
    from datetime import timedelta
    from sqlalchemy import select, update
    from src.db.models import Post
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with db.session() as s:
        stuck = list(s.scalars(select(Post.id).where(Post.status == "publishing",
                                                     Post.updated_at < cutoff)))
        if stuck and not dry_run:
            s.execute(update(Post).where(Post.id.in_(stuck))
                      .values(status="failed", error="Publishing was interrupted; it will be retried."))
        return stuck


# --------------------------------------------------------------------------- #
# Decisions (shared by the Telegram bot and the dashboard, so they can't diverge)
# --------------------------------------------------------------------------- #
DECISIONS = {"approve": "approved", "reject": "rejected", "regen": "regenerate"}
DECIDABLE = {"approve": {"pending", "approved", "expired", "failed", "regenerate"},   # approving again = reschedule; expired/failed/stuck = revive
             "reject": {"pending", "approved", "regenerate", "failed"},
             "regen": {"pending", "approved", "failed", "expired"}}
EDITABLE = {"pending", "approved", "failed", "expired", "regenerate"}


class DecisionError(ValueError):
    pass


def apply_decision(item: Item, action: str, *, feedback: str = "") -> Item:
    """Pure state change for approve / reject / regen. Raises DecisionError if not allowed now."""
    if action not in DECISIONS:
        raise DecisionError(f"unknown action {action!r}")
    if item.status not in DECIDABLE[action]:
        raise DecisionError(f"{item.kind} is already {item.status}")
    item.status = DECISIONS[action]  # type: ignore[assignment]
    item.decided_at = now_iso()
    if feedback.strip():
        item.feedback = (item.feedback + "\n" + feedback.strip()).strip()
    return item
