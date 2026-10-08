"""SQLAlchemy models. Change the schema here, then create an Alembic revision:

    cd api && alembic revision --autogenerate -m "<what changed>"
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, text
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
    # A topic's carousel + reel (and their regenerated versions) share one group: "<date>/<slug>".
    group_id: Mapped[str] = mapped_column(String(120), index=True, default="")
    # Where this item should go: reel -> ["ig", "yt"], carousel -> ["ig"]. Null = the kind's default.
    targets: Mapped[list | None] = mapped_column(JSONType)
    yt_title: Mapped[str | None] = mapped_column(Text)          # overrides the title built from the caption
    yt_description: Mapped[str | None] = mapped_column(Text)    # overrides the built description
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, default=1, server_default="1")
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

    # Profile. Server defaults keep older code (which doesn't know these columns) working.
    job_title: Mapped[str] = mapped_column(String(80), default="", server_default="")
    bio: Mapped[str] = mapped_column(String(280), default="", server_default="")
    phone: Mapped[str] = mapped_column(String(32), default="", server_default="")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", server_default="Asia/Kolkata")
    # Profile picture: a small (<= 400 KB) JPEG/PNG/WebP kept in the row; the browser crops and resizes it first.
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)
    avatar_mime: Mapped[str | None] = mapped_column(String(32))
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Created by Google sign-in: access (including a password set later) lasts only while the email is on
    # ALLOWED_GOOGLE_EMAILS (QA-M-06). The seeded password admin is False.
    via_google: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Taste, niche, tone, aesthetic & prompt instructions (QA Task 3)
    taste: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    # Cadence: custom posts per day & slot times (QA Task 4)
    cadence: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    # Subscription status & Stripe customer details (QA Task 3)
    subscription_tier: Mapped[str] = mapped_column(String(32), default="free", server_default="free")
    subscription_status: Mapped[str] = mapped_column(String(32), default="active", server_default="active")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100))
    # Config completion gate flag (QA Task 2)
    config_completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class OtpCode(Base):
    """A one-time 6-digit code emailed to a user (password reset, set a first password, verify a new email).

    Only an HMAC of the code is stored. A code works once, for 10 minutes, and dies after 5 wrong tries.
    """
    __tablename__ = "otp_codes"
    __table_args__ = (Index("ix_otp_codes_user_purpose", "user_id", "purpose"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(24))          # reset | set_password | verify_email
    email: Mapped[str] = mapped_column(String(254))           # where the code was sent
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityLog(Base):
    """What happened and who did it (dashboard clicks, Telegram decisions, publishing, sign-ins).

    Written through src.activity.record(); shown on the dashboard's Logs page. Pruned after ~90 days.
    """
    __tablename__ = "activity_log"
    __table_args__ = (Index("ix_activity_log_created_at", "created_at"),
                      Index("ix_activity_log_post_id", "post_id"))

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[str] = mapped_column(String(8), default="info", server_default="info")     # info | warning | error
    source: Mapped[str] = mapped_column(String(24), default="system", server_default="system")
    event: Mapped[str] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text, default="", server_default="")
    post_id: Mapped[str | None] = mapped_column(String(160))
    actor: Mapped[str | None] = mapped_column(String(254))
    detail: Mapped[dict | None] = mapped_column(JSONType)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, default=1, server_default="1")


class RateLimitEvent(Base):
    """One counted attempt (failed sign-in, code request, code guess) for api.app.ratelimit, shared by every API
    process / Lambda container (QA-M-05). Rows older than a day are pruned as new ones arrive."""
    __tablename__ = "rate_limit_events"
    __table_args__ = (Index("ix_rate_limit_events_key_at", "key", "at"),
                      Index("ix_rate_limit_events_at", "at"))

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GenerationJob(Base):
    """One generation request (dashboard click or scheduled run) and where it is. See src.generation.

    The partial unique index is the lock: at most one non-terminal job per trigger, so a double click or
    a second tab can't start two dashboard runs. Pruned after ~90 days.
    """
    __tablename__ = "generation_jobs"
    __table_args__ = (
        Index("uq_generation_jobs_one_active", "trigger", unique=True,
              postgresql_where=text("status IN ('queued', 'running')"),
              sqlite_where=text("status IN ('queued', 'running')")),
        Index("ix_generation_jobs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)          # the request id (also in the run name)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    trigger: Mapped[str] = mapped_column(String(16))                       # dashboard | scheduled
    requested_by: Mapped[str | None] = mapped_column(String(254))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, default=1, server_default="1")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    # What was asked for
    slot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category: Mapped[str | None] = mapped_column(String(32))
    topic: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    force: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    allow_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Progress: queued | running | succeeded | failed | skipped | cancelled
    status: Mapped[str] = mapped_column(String(12), default="queued")
    phase: Mapped[str | None] = mapped_column(String(20))
    failure_reason: Mapped[str | None] = mapped_column(String(24))
    message: Mapped[str | None] = mapped_column(Text)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    github_run_id: Mapped[int | None] = mapped_column(BigInteger)
    github_run_url: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What came out
    topic_title: Mapped[str | None] = mapped_column(Text)
    topic_category: Mapped[str | None] = mapped_column(String(32))
    post_group_id: Mapped[str | None] = mapped_column(String(120))
    post_ids: Mapped[list | None] = mapped_column(JSONType)


# --------------------------------------------------------------------------- #
# Config store (src/config_store.py): settings entered on the dashboard's Config page.
# Secrets are AES-256-GCM ciphertext under a data key that is itself wrapped by CONFIG_MASTER_KEY
# (which never touches the database). A database dump alone reveals no secret.
# --------------------------------------------------------------------------- #
class ConfigKey(Base):
    """The data-encryption key (DEK), wrapped (encrypted) by the master key. One active row."""
    __tablename__ = "config_keys"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    kek_id: Mapped[str] = mapped_column(String(16))         # which master key wrapped it (HMAC tag, not the key)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    rewrapped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConfigValue(Base):
    """One setting. Secrets: ciphertext + nonce (value_plain is null). Non-secrets: value_plain."""
    __tablename__ = "config_values"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=True)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    value_plain: Mapped[str | None] = mapped_column(Text)
    dek_version: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)               # optimistic concurrency
    fingerprint: Mapped[str | None] = mapped_column(String(16))           # HMAC prefix, never the value
    source: Mapped[str] = mapped_column(String(12), default="ui")          # ui | import | refresh | oauth
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(254))


class ConfigCheck(Base):
    """One verification result for an integration (what the Config page and readiness read)."""
    __tablename__ = "config_checks"
    __table_args__ = (Index("ix_config_checks_integration_ran_at", "integration", "ran_at"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    integration: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(10))                         # valid | warning | invalid | unknown | not_set
    depth: Mapped[str] = mapped_column(String(8), default="live")           # format | live | deep
    error_class: Mapped[str | None] = mapped_column(String(16))
    code: Mapped[str | None] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSONType, default=dict)            # checks + evidence (never a secret)
    values_fp: Mapped[str | None] = mapped_column(String(16))               # which values were checked
    config_version: Mapped[int] = mapped_column(Integer, default=0)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ran_in: Mapped[str] = mapped_column(String(8), default="api")           # api | runner | cli
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    actor: Mapped[str | None] = mapped_column(String(254))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConfigMeta(Base):
    """Singleton (id=1): the canary that proves the master key matches, and the config version."""
    __tablename__ = "config_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canary: Mapped[bytes | None] = mapped_column(LargeBinary)
    canary_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    config_version: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
