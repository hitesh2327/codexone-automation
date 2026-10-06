"""Activity log: a small, durable record of what happened (shown on the dashboard's Logs page).

    from src import activity
    activity.record("post.approved", "Approved reel 'Prompt injection'", source="dashboard", post_id=item.id, actor="admin")

record() NEVER raises -- logging must not break an approval or a publish -- and does nothing when
there is no DATABASE_URL (file mode). Never put passwords, codes, tokens or IP addresses in a message.
"""
from __future__ import annotations

import logging
import random
from datetime import timedelta

from sqlalchemy import delete

from src import db
from src.db.models import ActivityLog, utcnow
from src.redact import redact, redact_obj

log = logging.getLogger("codexone.activity")

LEVELS = ("info", "warning", "error")
RETENTION_DAYS = 90
_PRUNE_ODDS = 0.02  # prune on ~1 in 50 writes: cheap, and the poll job also calls prune() every run


def record(event: str, message: str, *, level: str = "info", source: str = "system", post_id: str | None = None,
           actor: str | None = None, detail: dict | None = None) -> None:
    try:
        if not db.enabled():
            return
        # Scrubbed even though callers are told not to pass secrets: exception text is a common leak path.
        row = ActivityLog(level=level if level in LEVELS else "info", source=(source or "system")[:24],
                          event=event[:48], message=redact((message or "")[:2000]), post_id=(post_id or None) and post_id[:160],
                          actor=(actor or None) and actor[:254], detail=redact_obj(detail) if detail else None)
        with db.session() as s:
            s.add(row)
            if random.random() < _PRUNE_ODDS:
                s.execute(delete(ActivityLog).where(ActivityLog.created_at < utcnow() - timedelta(days=RETENTION_DAYS)))
    except Exception as e:  # noqa: BLE001 -- must never break the caller
        try:
            log.warning("could not record activity %s: %s", event, e)
        except Exception:  # noqa: BLE001
            pass


def prune(days: int = RETENTION_DAYS) -> int:
    """Delete entries older than `days`. Returns how many went (0 on any error)."""
    try:
        if not db.enabled():
            return 0
        with db.session() as s:
            return s.execute(delete(ActivityLog).where(ActivityLog.created_at < utcnow() - timedelta(days=days))).rowcount or 0
    except Exception as e:  # noqa: BLE001
        log.warning("could not prune activity log: %s", e)
        return 0
