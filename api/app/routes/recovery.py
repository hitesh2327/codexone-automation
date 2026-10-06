"""Forgot / reset password by emailed one-time code (public: the user is not signed in).

Also the way for a Google-only account (no password yet) to get its first password: ask for a code,
enter it, choose a password. Afterwards the person can sign in with that password and their email.

Privacy: /forgot answers the same way whether or not an account matches, so it can't be used to find
out who has an account.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from api.app import mailer, otp
from api.app import ratelimit as rl
from api.app.security import burn_time, hash_password, password_problems
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
    return request.client.host if request.client else "unknown"


def find_user(ses, identifier: str) -> User | None:
    ident = identifier.strip().lower()
    return ses.scalars(select(User).where(or_(func.lower(User.username) == ident,
                                              func.lower(User.email) == ident))).first()


def _too_many(wait: int) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many attempts. Try again in {wait // 60 + 1} min.",
                         headers={"Retry-After": str(wait)})


@router.post("/forgot")
def forgot(body: ForgotBody, request: Request) -> dict:
    ip, ident = _ip(request), body.identifier.strip().lower()
    for key, limit in ((f"send-ip:{ip}", rl.OTP_SEND_PER_IP), (f"send:{ident}", rl.OTP_SEND_PER_ADDRESS)):
        wait = rl.otp_limiter.retry_after(key, limit, rl.WINDOW)
        if wait:
            raise _too_many(wait)
        rl.otp_limiter.hit(key)

    generic = {"ok": True, "cooldown": otp.RESEND_COOLDOWN,
               "message": "If that matches an account with an email address, a 6-digit code is on its way."}
    message = None
    with db.session() as ses:
        user = find_user(ses, ident)
        if user is None or not user.is_active or not user.email:
            burn_time()
            log.info("password code requested for unknown/ineligible %r", ident)
            return generic
        try:
            code = otp.issue(ses, user, "reset", user.email)
        except otp.OtpCooldown:
            return generic  # one was just sent; same answer, no new mail
        message = mailer.otp_email(user.email, code, "reset", user.name)
    try:
        mailer.send(message)
    except mailer.MailError as e:
        log.error("password code email failed: %s", e)  # the person sees the generic answer; the admin sees this
    return generic


@router.post("/reset")
def reset(body: ResetBody, request: Request) -> dict:
    ip, ident = _ip(request), body.identifier.strip().lower()
    for key in (f"try:{ident}", f"try-ip:{ip}"):
        wait = rl.otp_limiter.retry_after(key, rl.OTP_TRY_PER_ACCOUNT * (3 if key.startswith("try-ip") else 1), rl.WINDOW)
        if wait:
            raise _too_many(wait)
        rl.otp_limiter.hit(key)

    problem: str | None = None
    with db.session() as ses:
        user = find_user(ses, ident)
        if user is None or not user.is_active or not user.email:
            burn_time()
            problem = GENERIC_FAIL
        elif issues := password_problems(body.new_password, user.username, user.email, user.name):
            problem = "Choose a stronger password: " + ", ".join(issues) + "."  # checked first: a weak try doesn't burn the code
        elif not otp.verify(ses, user, "reset", user.email, body.code):
            problem = GENERIC_FAIL  # the wrong-guess counter is committed when this block exits
        else:
            now = datetime.now(timezone.utc)
            user.password_hash = hash_password(body.new_password)
            user.password_changed_at = now
            user.email_verified_at = user.email_verified_at or now  # they just proved they own it
            user.token_version += 1  # every existing session is signed out
            log.info("password reset for %s", user.email)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST if problem == GENERIC_FAIL else status.HTTP_422_UNPROCESSABLE_CONTENT,
                            problem)
    rl.otp_limiter.reset(f"try:{ident}")
    return {"ok": True}
