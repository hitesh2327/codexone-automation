"""Sliding-window rate limits for sign-in and emailed codes.

Shared limiters (sign-in, codes) count in Postgres (table rate_limit_events), so every API process and every
Lambda container sees the same counts (QA-M-05: in-memory counters multiplied with concurrency). File mode (no
DATABASE_URL) and the per-user UI limiters keep counts in memory. A database error never locks anyone out and
never lets an attempt through uncounted silently: it falls back to the in-memory counts and logs a warning.

Keys carry the real client IP from api.app.clientip, never a spoofable header.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

log = logging.getLogger("codexone.api.ratelimit")


class RateLimiter:
    """In-memory sliding window (one process)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, window: float, now: float) -> deque[float]:
        q = self._hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        return q

    def retry_after(self, key: str, limit: int, window: float) -> int:
        """Seconds until another attempt is allowed (0 = allowed now)."""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, window, now)
            return 0 if len(q) < limit else int(q[0] + window - now) + 1

    def hit(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


class SharedRateLimiter(RateLimiter):
    """Same interface, counted in the database under `<namespace>|<key>`."""

    KEEP = timedelta(days=1)

    def __init__(self, namespace: str) -> None:
        super().__init__()
        self.namespace = namespace

    def _db(self) -> bool:
        from src import db
        return db.enabled()

    def _k(self, key: str) -> str:
        return f"{self.namespace}|{key}"[:200]

    def retry_after(self, key: str, limit: int, window: float) -> int:
        if not self._db():
            return super().retry_after(key, limit, window)
        from sqlalchemy import select
        from src import db
        from src.db.models import RateLimitEvent
        now = datetime.now(timezone.utc)
        try:
            with db.session() as s:
                times = list(s.scalars(select(RateLimitEvent.at)
                                       .where(RateLimitEvent.key == self._k(key),
                                              RateLimitEvent.at > now - timedelta(seconds=window))
                                       .order_by(RateLimitEvent.at)))
        except Exception as e:  # noqa: BLE001
            log.warning("rate limit store unavailable (%s); using this process's counts", type(e).__name__)
            return super().retry_after(key, limit, window)
        if len(times) < limit:
            return 0
        oldest = times[len(times) - limit]
        oldest = oldest if oldest.tzinfo else oldest.replace(tzinfo=timezone.utc)
        return max(1, int((oldest + timedelta(seconds=window) - now).total_seconds()) + 1)

    def hit(self, key: str) -> None:
        if not self._db():
            return super().hit(key)
        from sqlalchemy import delete
        from src import db
        from src.db.models import RateLimitEvent
        now = datetime.now(timezone.utc)
        try:
            with db.session() as s:
                s.add(RateLimitEvent(key=self._k(key), at=now))
                if random.random() < 0.02:  # keep the table small without a scheduled job
                    s.execute(delete(RateLimitEvent).where(RateLimitEvent.at < now - self.KEEP))
        except Exception as e:  # noqa: BLE001
            log.warning("rate limit store unavailable (%s); counting in this process", type(e).__name__)
            super().hit(key)

    def reset(self, key: str) -> None:
        super().reset(key)
        if not self._db():
            return
        from sqlalchemy import delete
        from src import db
        from src.db.models import RateLimitEvent
        try:
            with db.session() as s:
                s.execute(delete(RateLimitEvent).where(RateLimitEvent.key == self._k(key)))
        except Exception as e:  # noqa: BLE001
            log.warning("rate limit store unavailable (%s)", type(e).__name__)

    def clear(self) -> None:
        super().clear()
        if not self._db():
            return
        from sqlalchemy import delete
        from src import db
        from src.db.models import RateLimitEvent
        try:
            with db.session() as s:
                s.execute(delete(RateLimitEvent).where(RateLimitEvent.key.like(f"{self.namespace}|%")))
        except Exception:  # noqa: BLE001
            pass


login_limiter = SharedRateLimiter("login")

WINDOW = 15 * 60
PER_ACCOUNT = 5      # failed attempts per (IP, username) per window
PER_IP = 20          # failed attempts per IP per window (password spraying)


# Emailed codes: asking for them and guessing them are limited separately from sign-in.
otp_limiter = SharedRateLimiter("otp")
OTP_SEND_PER_ADDRESS = 8     # code requests per account/address per window (from any IP)
OTP_SEND_PER_ADDRESS_IP = 3  # ... of which one client may make this many (QA-L-06: one client can't use them all)
OTP_SEND_PER_IP = 12
OTP_TRY_PER_ACCOUNT = 12     # code submissions per account per window, all clients (each code also dies after 5 wrong tries)
OTP_TRY_PER_ACCOUNT_IP = 6   # ... of which one client may make this many (QA-L-06)
