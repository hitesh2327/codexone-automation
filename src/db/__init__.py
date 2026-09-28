"""Postgres access shared by the pipeline (src/) and the admin API (api/).

The database is used when DATABASE_URL is set; otherwise the pipeline keeps using
the JSON files in data/ (see src/queue_store.py). Schema changes go through Alembic
(api/migrations).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_env


def database_url() -> str | None:
    url = get_env("DATABASE_URL", required=False)
    if not url:
        return None
    # Hosted providers hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def enabled() -> bool:
    return database_url() is not None


@lru_cache(maxsize=1)
def engine() -> Engine:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def _sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=engine(), expire_on_commit=False, future=True)


@contextmanager
def session() -> Iterator[Session]:
    """Transaction scope: commits on success, rolls back on error."""
    s = _sessionmaker()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Settings (key -> JSON value): brand config, Telegram offset, ...
# --------------------------------------------------------------------------- #
def get_setting(key: str, default: Any = None) -> Any:
    from src.db.models import Setting
    with session() as s:
        row = s.get(Setting, key)
        return row.value if row else default


def set_setting(key: str, value: Any) -> None:
    from src.db.models import Setting
    with session() as s:
        row = s.get(Setting, key)
        if row:
            row.value = value
            row.updated_at = datetime.now(timezone.utc)
        else:
            s.add(Setting(key=key, value=value))


def all_settings() -> dict[str, Any]:
    from src.db.models import Setting
    with session() as s:
        return {r.key: r.value for r in s.scalars(select(Setting))}
