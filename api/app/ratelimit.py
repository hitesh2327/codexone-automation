"""In-memory sliding-window rate limiter for the login endpoint.

Fine for a single API instance (the free-tier deployment). With several instances, move
this to Postgres or Redis so the limits are shared.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
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


login_limiter = RateLimiter()

WINDOW = 15 * 60
PER_ACCOUNT = 5      # failed attempts per (IP, username) per window
PER_IP = 20          # failed attempts per IP per window (password spraying)


# Emailed codes: asking for them and guessing them are limited separately from sign-in.
otp_limiter = RateLimiter()
OTP_SEND_PER_ADDRESS = 4     # code requests per account/address per window
OTP_SEND_PER_IP = 12
OTP_TRY_PER_ACCOUNT = 12     # code submissions per account per window (each code also dies after 5 wrong tries)
