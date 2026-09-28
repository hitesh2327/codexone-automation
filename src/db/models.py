"""SQLAlchemy models. Change the schema here, then create an Alembic revision:

    cd api && alembic revision --autogenerate -m "<what changed>"
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB on Postgres (indexable, compact); plain JSON elsewhere (e.g. SQLite in tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Post(Base):
    """One publishable item (a carousel or a reel) moving through the approval flow.

    Mirrors src.queue_store.Item; status flow is documented there.
    """
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)            # carousel | reel
    date: Mapped[date] = mapped_column(Date, index=True)
    topic: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    angle: Mapped[str] = mapped_column(Text, default="")
    post_dir: Mapped[str] = mapped_column(Text)
    caption: Mapped[str] = mapped_column(Text)
    media: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    voice: Mapped[str] = mapped_column(String(64), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    feedback: Mapped[str] = mapped_column(Text, default="")
    tg_message_ids: Mapped[list] = mapped_column(JSONType, default=list)
    tg_control_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ig_media_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    platforms: Mapped[dict] = mapped_column(JSONType, default=dict)     # {"ig"|"yt": {status, id, url, ...}}
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PostedTopic(Base):
    """Publishing history (was data/posted.json): topic dedupe + per-platform outcome."""
    __tablename__ = "posted_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str | None] = mapped_column(String(40), unique=True)  # posts.id; null for legacy rows
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(32), index=True)
    kind: Mapped[str | None] = mapped_column(String(16))
    date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ig_media_id: Mapped[str | None] = mapped_column(String(64))
    platforms: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    """Key -> JSON value. Keys: "brand" (was brand/config.yaml), "tg_offset", ..."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | int | str | None] = mapped_column(JSONType)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base):
    """Dashboard login. Password users have username + password_hash; Google users have email."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bumped on logout; tokens carry it, so logging out invalidates every issued session.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
