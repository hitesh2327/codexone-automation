"""Forgot / reset password by emailed one-time code (public: the user is not signed in).

Also the way for a Google-only account (no password yet) to get its first password: ask for a code,
enter it, choose a password. Afterwards the person can sign in with that password and their email.

Privacy (QA-M-04): neither endpoint reveals whether an account exists. /forgot answers the same way either
way; /reset checks the code BEFORE the password strength, so "choose a stronger password" (422) is only ever
said to someone holding a valid code. Both do the same kind of work on every branch (no bcrypt-only branch for
unknown names) and answer no sooner than RECOVERY_MIN_MS (default 1500 ms) after the request arrived, so
response time doesn't tell the branches apart either (mail delivery included).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from api.app import mailer, otp
from api.app import ratelimit as rl
from api.app.clientip import client_ip
from api.app.deps import access_allowed
from api.app.security import hash_password, password_problems
from src import db
from src.db.models import User

log = logging.getLogger("codexone.api.recovery")
router = APIRouter(prefix="/api/auth/password", tags=["auth"])

GENERIC_FAIL = "That code is invalid or has expired. Check it, or ask for a new one."


class ForgotBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=254, description="email or username")


class ResetBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    code: str = Field(min_length=1, max_length=12)
    new_password: str = Field(min_length=1, max_length=200)


def _ip(request: Request) -> str:
    return client_ip(request)


def _floor_seconds() -> float:
    try:
        return max(0.0, int(os.environ.get("RECOVERY_MIN_MS") or "1500") / 1000)
    except ValueError:
        return 1.5


def _pad(started: float) -> None:
    """Answer no sooner than the floor after the request started, whichever branch ran."""
    left = _floor_seconds() - (time.monotonic() - started)
    if left > 0:
        time.sleep(left)


def _limit(keys: tuple[tuple[str, int], ...]) -> None:
    for key, limit in keys:
        wait = rl.otp_limiter.retry_after(key, limit, rl.WINDOW)
        if wait:
            raise _too_many(wait)
    for key, _ in keys:
        rl.otp_limiter.hit(key)


def _eligible(user: User | None) -> bool:
    return bool(user and user.is_active and user.email and access_allowed(user))


def find_user(ses, identifier: str) -> User | None:
    ident = identifier.strip().lower()
    return ses.scalars(select(User).where(or_(func.lower(User.username) == ident,
                                              func.lower(User.email) == ident))).first()


def _too_many(wait: int) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many attempts. Try again in {wait // 60 + 1} min.",
                         headers={"Retry-After": str(wait)})


def _send_otp_mail(message: mailer.Message) -> None:
    try:
        mailer.send(message)
    except mailer.MailError as e:
        log.error("password code email failed: %s", e)
    except Exception as e:
        log.error("unexpected error sending password code email: %s", e)


@router.post("/forgot")
def forgot(body: ForgotBody, request: Request, background_tasks: BackgroundTasks) -> dict:
    started = time.monotonic()
    ip, ident = _ip(request), body.identifier.strip().lower()
    # Per client AND per account: one client can't use up the account's quota (and with it the victim's
    # ability to get a code) on its own (QA-L-06).
    _limit(((f"send-ip:{ip}", rl.OTP_SEND_PER_IP), (f"send:{ident}:{ip}", rl.OTP_SEND_PER_ADDRESS_IP),
            (f"send:{ident}", rl.OTP_SEND_PER_ADDRESS)))

    generic = {"ok": True, "cooldown": otp.RESEND_COOLDOWN,
               "message": "If that matches an account with an email address, a 6-digit code is on its way."}
    try:
        with db.session() as ses:
            user = find_user(ses, ident)
            if not _eligible(user):
                log.info("password code requested for an unknown/ineligible account")
                return generic
            if not mailer.configured_for_codes():
                log.error("password code NOT sent: email isn't configured for production (see MAIL_DRIVER)")
                return generic
            try:
                code = otp.issue(ses, user, "reset", user.email)
            except otp.OtpCooldown:
                return generic  # one was just sent; same answer, no new mail
            message = mailer.otp_email(user.email, code, "reset", user.name)
            background_tasks.add_task(_send_otp_mail, message)
        return generic
    finally:
        _pad(started)


@router.post("/reset")
def reset(body: ResetBody, request: Request) -> dict:
    started = time.monotonic()
    ip, ident = _ip(request), body.identifier.strip().lower()
    # Check per-client IP limits before checking code (QA-L-06: client brute force protection)
    wait_ip = rl.otp_limiter.retry_after(f"try-ip:{ip}", rl.OTP_TRY_PER_ACCOUNT * 3, rl.WINDOW)
    wait_client = rl.otp_limiter.retry_after(f"try:{ident}:{ip}", rl.OTP_TRY_PER_ACCOUNT_IP, rl.WINDOW)
    if wait_ip or wait_client:
        wait = max(wait_ip, wait_client)
        raise _too_many(wait)

    problem: str | None = None
    is_failed_guess = False
    try:
        with db.session() as ses:
            user = find_user(ses, ident)
            if _eligible(user):
                row = otp.check(ses, user, "reset", user.email, body.code)
            else:
                row = None
                otp.dummy_check(ident, body.code)  # same work as a wrong code for a real account
            if row is None:
                is_failed_guess = True
                rl.otp_limiter.hit(f"try-ip:{ip}")
                rl.otp_limiter.hit(f"try:{ident}:{ip}")
                rl.otp_limiter.hit(f"try:{ident}")
                problem = GENERIC_FAIL
            elif issues := password_problems(body.new_password, user.username, user.email, user.name):
                # Only someone holding the valid code gets here; the code stays usable for a stronger try.
                problem = "Choose a stronger password: " + ", ".join(issues) + "."
            else:
                otp.consume(row)
                now = datetime.now(timezone.utc)
                user.password_hash = hash_password(body.new_password)
                user.password_changed_at = now
                user.email_verified_at = user.email_verified_at or now  # they just proved they own it
                user.token_version += 1  # every existing session is signed out
                log.info("password reset for account %s", user.id)
    finally:
        _pad(started)
    if problem:
        if is_failed_guess:
            wait_acct = rl.otp_limiter.retry_after(f"try:{ident}", rl.OTP_TRY_PER_ACCOUNT, rl.WINDOW)
            if wait_acct:
                raise _too_many(wait_acct)
        raise HTTPException(status.HTTP_400_BAD_REQUEST if problem == GENERIC_FAIL else status.HTTP_422_UNPROCESSABLE_CONTENT,
                            problem)
    rl.otp_limiter.reset(f"try:{ident}")
    rl.otp_limiter.reset(f"try:{ident}:{ip}")
    return {"ok": True}
