"""One-time email codes (password reset, set a first password, verify a new email address).

Rules: 6 digits, valid 10 minutes, usable once, at most 5 wrong tries, and one code per
(user, purpose) at a time (asking again replaces the old one, no faster than every 60 s).
Only an HMAC of the code is stored, keyed with the server secret, so a leaked table is not a
list of working codes.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.app.settings import settings
from src.db.models import OtpCode, User

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = 60  # seconds
PURPOSES = ("reset", "set_password", "verify_email")


class OtpCooldown(Exception):
    def __init__(self, seconds: int) -> None:
        super().__init__(f"wait {seconds}s")
        self.seconds = seconds


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite hands back naive datetimes


def _digest(user_id: int, purpose: str, email: str, code: str) -> str:
    msg = f"{user_id}:{purpose}:{email.lower()}:{code}".encode()
    return hmac.new(settings().jwt_secret.encode(), msg, hashlib.sha256).hexdigest()


def issue(ses: Session, user: User, purpose: str, email: str) -> str:
    """Create a fresh code and return it (the caller emails it). Raises OtpCooldown if asked too soon."""
    assert purpose in PURPOSES
    now = _now()
    live = ses.scalars(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.purpose == purpose,
                                             OtpCode.used_at.is_(None))).all()
    for old in live:
        wait = RESEND_COOLDOWN - int((now - _aware(old.created_at)).total_seconds())
        if wait > 0:
            raise OtpCooldown(wait)
    for old in live:
        old.used_at = now  # only the newest code works
    code = f"{secrets.randbelow(10 ** 6):06d}"
    ses.add(OtpCode(user_id=user.id, purpose=purpose, email=email.lower(), code_hash=_digest(user.id, purpose, email, code),
                    created_at=now, expires_at=now + CODE_TTL))
    return code


def verify(ses: Session, user: User, purpose: str, email: str, code: str) -> bool:
    """True once for the right, unexpired code. Wrong guesses are counted; the 5th kills the code."""
    code = (code or "").strip().replace(" ", "")
    now = _now()
    row = ses.scalars(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.purpose == purpose,
                                            OtpCode.email == email.lower(), OtpCode.used_at.is_(None))
                      .order_by(OtpCode.id.desc())).first()
    if row is None or _aware(row.expires_at) <= now or row.attempts >= MAX_ATTEMPTS:
        return False
    if not (code.isdigit() and len(code) == 6) or not hmac.compare_digest(row.code_hash, _digest(user.id, purpose, email, code)):
        row.attempts += 1
        if row.attempts >= MAX_ATTEMPTS:
            row.used_at = now
        return False
    row.used_at = now
    return True
