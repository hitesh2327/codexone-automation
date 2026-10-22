"""The signed-in user's profile: details, picture, email, and password.

Mounted under /api (signed in + CSRF on writes, see main.py).

Password rules
  * account HAS a password  -> changing it needs the current password
  * account has NONE (Google-only) -> setting the first one needs a code emailed to the account address
Either way every other session is signed out and this one stays signed in with fresh credentials.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from api.app import mailer, otp
from api.app import ratelimit as rl
from api.app.deps import CurrentUser, current_user
from api.app.routes.auth import avatar_version, start_session
from api.app.security import hash_password, password_problems, verify_password
from api.app.settings import settings
from src import db, plan_limits
from src.db.models import User

log = logging.getLogger("codexone.api.profile")
router = APIRouter(prefix="/profile", tags=["profile"])

AVATAR_MAX_BYTES = 400 * 1024
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
PHONE_RE = re.compile(r"^[+0-9 ()\-.]{0,32}$")


# --------------------------------------------------------------------------- #
# Shape
# --------------------------------------------------------------------------- #
def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def profile_out(u: User) -> dict:
    s = settings()
    email = (u.email or "").lower()
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "email_verified": bool(u.email and u.email_verified_at),
        "name": u.name or "",
        "job_title": u.job_title or "",
        "bio": u.bio or "",
        "phone": u.phone or "",
        "timezone": u.timezone or "Asia/Kolkata",
        "role": "Administrator",
        "has_password": bool(u.password_hash),
        "google_allowed": bool(email and s.google_enabled and email in s.allowed_google_emails),
        "has_avatar": bool(u.avatar),
        "avatar_v": avatar_version(u),
        "member_since": _iso(u.created_at),
        "last_login_at": _iso(u.last_login_at),
        "password_changed_at": _iso(u.password_changed_at),
        "config_completed": bool(u.config_completed),
        "subscription_tier": u.subscription_tier or "free",
        "subscription_status": u.subscription_status or "active",
        "taste": u.taste or {
            "niche": "AI & Tech",
            "tone": "Engaging & Informative",
            "aesthetic": "Modern Minimalist",
            "default_targets": ["ig", "yt"],
        },
        "cadence": u.cadence or {
            "posts_per_day": 2,
            "slots": ["10:00", "18:00"],
        },
    }


def _user(ses, cu: CurrentUser) -> User:
    row = ses.get(User, cu.id)
    if row is None:  # signed in as a row that was deleted a moment ago
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return row


@router.get("")
def get_profile(cu: CurrentUser = Depends(current_user)) -> dict:
    with db.session() as ses:
        return profile_out(_user(ses, cu))


# --------------------------------------------------------------------------- #
# Details
# --------------------------------------------------------------------------- #
class ProfileBody(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    job_title: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=280)
    phone: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    username: str | None = Field(default=None, max_length=32)
    taste: dict | None = None
    cadence: dict | None = None
    config_completed: bool | None = None


def _bad(msg: str, code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(code, msg)


@router.patch("")
def update_profile(body: ProfileBody, cu: CurrentUser = Depends(current_user)) -> dict:
    try:
        return _update_profile(body, cu)
    except IntegrityError:  # two accounts took the same username at the same moment (QA-L-09)
        raise _bad("That username is taken.", status.HTTP_409_CONFLICT) from None


def _update_profile(body: ProfileBody, cu: CurrentUser) -> dict:
    data = body.model_dump(exclude_unset=True)
    with db.session() as ses:
        u = _user(ses, cu)
        if "name" in data:
            name = " ".join((data["name"] or "").split())
            if not name:
                raise _bad("Your name can't be empty.")
            u.name = name
        if "job_title" in data:
            u.job_title = " ".join((data["job_title"] or "").split())
        if "bio" in data:
            u.bio = (data["bio"] or "").strip()
        if "phone" in data:
            phone = (data["phone"] or "").strip()
            if not PHONE_RE.match(phone):
                raise _bad("Use digits, spaces and + ( ) - only for the phone number.")
            u.phone = phone
        if "timezone" in data:
            tz = (data["timezone"] or "").strip()
            try:
                ZoneInfo(tz)
            except (ZoneInfoNotFoundError, ValueError, OSError):
                raise _bad("That isn't a time zone we recognise (try Asia/Kolkata).") from None
            u.timezone = tz
        if "username" in data:
            uname = (data["username"] or "").strip().lower()
            if uname != (u.username or "").lower():
                if not USERNAME_RE.match(uname):
                    raise _bad("Usernames are 3-32 characters: letters, numbers, dot, dash, underscore.")
                taken = ses.scalars(select(User.id).where(func.lower(User.username) == uname, User.id != u.id)).first()
                if taken:
                    raise _bad("That username is taken.", status.HTTP_409_CONFLICT)
                u.username = uname
        try:  # the plan caps the schedule and the platforms (src/plan_limits.py)
            if data.get("cadence") is not None:
                plan_limits.check_cadence(u, {**(u.cadence or {}), **data["cadence"]})
            if data.get("taste") is not None and "default_targets" in data["taste"]:
                plan_limits.check_targets(u, data["taste"]["default_targets"])
        except plan_limits.PlanLimit as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail={"code": e.code, "message": e.message, **e.extra}) from None
        if "taste" in data and data["taste"] is not None:
            current_taste = dict(u.taste or {})
            current_taste.update(data["taste"])
            u.taste = current_taste
            try:
                from src.user_taste import invalidate as _inv
                _inv(cu.id)
            except Exception:  # noqa: BLE001
                pass
        if "cadence" in data and data["cadence"] is not None:
            current_cadence = dict(u.cadence or {})
            current_cadence.update(data["cadence"])
            u.cadence = current_cadence
        if "config_completed" in data and data["config_completed"] is not None:
            u.config_completed = bool(data["config_completed"])
        ses.flush()
        return profile_out(u)


# --------------------------------------------------------------------------- #
# AI schedule suggestions
# --------------------------------------------------------------------------- #
@router.post("/suggest-schedule")
def suggest_schedule(cu: CurrentUser = Depends(current_user)) -> dict:
    """Ask Gemini for optimal posting times based on the user's niche and platforms."""
    import json as _json
    from src.config import get_env
    try:
        from google import genai
    except ImportError:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Gemini SDK not available")

    with db.session() as ses:
        u = _user(ses, cu)
        taste = dict(u.taste or {})

    niche = taste.get("niche") or "Software Engineering & Dev"
    audience = taste.get("target_audience") or "Developers and tech enthusiasts"
    platforms: list[str] = taste.get("default_targets") or ["ig", "yt"]

    platform_names = {"ig": "Instagram Reels", "yt": "YouTube Shorts", "li": "LinkedIn"}
    plat_list = ", ".join(platform_names.get(p, p) for p in platforms)

    prompt = (
        f"You are a social media expert optimising posting schedules for maximum organic reach.\n\n"
        f"Creator profile:\n"
        f"- Niche: {niche}\n"
        f"- Target audience: {audience}\n"
        f"- Platforms: {plat_list}\n"
        f"- Timezone: IST (UTC+5:30)\n\n"
        f"Suggest the 2 best daily posting times (24h, IST) for each platform to maximise engagement. "
        f"Consider platform-specific peak hours, audience timezone, and content type (short-form video/carousels). "
        f"Times must be between 06:00 and 23:00 IST.\n\n"
        f"Return ONLY valid JSON with this exact structure (one key per platform slug + a reasoning key):\n"
        f'{{"ig": ["HH:MM", "HH:MM"], "yt": ["HH:MM", "HH:MM"], "reasoning": "one sentence"}}'
    )

    api_key = get_env("GEMINI_API_KEY", required=False)
    if not api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GEMINI_API_KEY not configured")

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        result: dict = _json.loads(resp.text)
    except Exception as e:
        log.error("suggest-schedule: Gemini failed: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not get schedule suggestions; try again.")

    # Validate / fill missing platforms with sensible defaults
    defaults = {"ig": ["10:00", "19:00"], "yt": ["10:00", "20:00"]}
    for p in platforms:
        if p not in result or not isinstance(result.get(p), list):
            result[p] = defaults.get(p, ["10:00", "19:00"])
    return result


@router.post("/suggest-categories")
def suggest_categories(cu: CurrentUser = Depends(current_user)) -> dict:
    """Ask Gemini to suggest 4-6 content categories for the user's niche."""
    import json as _json
    from src.config import get_env
    try:
        from google import genai
    except ImportError:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Gemini SDK not available")

    with db.session() as ses:
        u = _user(ses, cu)
        taste = dict(u.taste or {})

    niche = taste.get("niche") or "Software Engineering & Dev"
    content_type = taste.get("content_type") or "Educational & How-To"
    audience = taste.get("target_audience") or ""

    prompt = (
        f"You are a social media content strategist.\n\n"
        f"Creator profile:\n"
        f"- Niche: {niche}\n"
        f"- Content type: {content_type}\n"
        f"- Target audience: {audience or 'general'}\n\n"
        f"Suggest exactly 5 distinct content categories for this Instagram account. "
        f"Each category should be a short label (1-3 words) that represents a recurring theme "
        f"or content pillar for the niche. They should be different enough that content can be "
        f"spread evenly across them.\n\n"
        f"Return ONLY valid JSON: "
        f'{{ "categories": ["Cat1", "Cat2", "Cat3", "Cat4", "Cat5"], "reasoning": "one sentence" }}'
    )

    api_key = get_env("GEMINI_API_KEY", required=False)
    if not api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GEMINI_API_KEY not configured")

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        result: dict = _json.loads(resp.text)
    except Exception as e:
        log.error("suggest-categories: Gemini failed: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not get category suggestions; try again.")

    cats = result.get("categories", [])
    if not isinstance(cats, list) or len(cats) < 2:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Unexpected response from Gemini; try again.")
    return {"categories": [str(c).strip() for c in cats[:8]], "reasoning": result.get("reasoning", "")}


# --------------------------------------------------------------------------- #
# Picture (the browser crops and resizes; we accept a small JPEG/PNG/WebP as raw bytes)
# --------------------------------------------------------------------------- #
def _sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/avatar")
async def upload_avatar(request: Request, cu: CurrentUser = Depends(current_user)) -> dict:
    declared = int(request.headers.get("content-length") or 0)
    if declared > AVATAR_MAX_BYTES:
        raise _bad("That picture is too large. Keep it under 400 KB.", status.HTTP_413_CONTENT_TOO_LARGE)
    data = await request.body()
    if not data:
        raise _bad("No image received.")
    if len(data) > AVATAR_MAX_BYTES:
        raise _bad("That picture is too large. Keep it under 400 KB.", status.HTTP_413_CONTENT_TOO_LARGE)
    mime = _sniff(data)  # trust the bytes, not the header
    if mime is None:
        raise _bad("Use a JPEG, PNG or WebP picture.", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
    with db.session() as ses:
        u = _user(ses, cu)
        u.avatar, u.avatar_mime, u.avatar_updated_at = data, mime, datetime.now(timezone.utc)
        ses.flush()
        return profile_out(u)


@router.delete("/avatar")
def delete_avatar(cu: CurrentUser = Depends(current_user)) -> dict:
    with db.session() as ses:
        u = _user(ses, cu)
        u.avatar = u.avatar_mime = u.avatar_updated_at = None
        ses.flush()
        return profile_out(u)


@router.get("/avatar")
def get_avatar(cu: CurrentUser = Depends(current_user)) -> Response:
    with db.session() as ses:
        u = _user(ses, cu)
        if not u.avatar:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No picture")
        # The page adds ?v=<avatar_v>, so a new picture is a new URL; a cached one is safe to keep.
        return Response(u.avatar, media_type=u.avatar_mime or "image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


# --------------------------------------------------------------------------- #
# Email (changing it is confirmed with a code sent to the NEW address)
# --------------------------------------------------------------------------- #
class EmailOtpBody(BaseModel):
    email: str = Field(max_length=254)


class EmailBody(EmailOtpBody):
    code: str = Field(min_length=1, max_length=12)


def _send_code(ses, u: User, purpose: str, to: str) -> mailer.Message:
    if not mailer.configured_for_codes():  # QA-M-07: say so instead of "sent" (and issue no code)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, mailer.NOT_CONFIGURED)
    for key, limit in ((f"send:{u.id}:{purpose}", rl.OTP_SEND_PER_ADDRESS),):
        wait = rl.otp_limiter.retry_after(key, limit, rl.WINDOW)
        if wait:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many codes requested. Try again in {wait // 60 + 1} min.",
                                headers={"Retry-After": str(wait)})
        rl.otp_limiter.hit(key)
    try:
        code = otp.issue(ses, u, purpose, to)
    except otp.OtpCooldown as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"A code was just sent. You can ask for another in {e.seconds}s.",
                            headers={"Retry-After": str(e.seconds)}) from None
    return mailer.otp_email(to, code, purpose, u.name)


def _deliver(message: mailer.Message) -> dict:
    try:
        mailer.send(message)
    except mailer.MailError as e:
        log.error("email failed: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "We couldn't send the email right now. Check the mail settings, or try again shortly.") from e
    return {"ok": True, "cooldown": otp.RESEND_COOLDOWN, "sent_to": message.to}


@router.post("/email/otp")
def email_code(body: EmailOtpBody, cu: CurrentUser = Depends(current_user)) -> dict:
    new = body.email.strip().lower()
    if not EMAIL_RE.match(new):
        raise _bad("That doesn't look like an email address.")
    with db.session() as ses:
        u = _user(ses, cu)
        if (u.email or "").lower() == new and u.email_verified_at:
            raise _bad("That is already your verified email.", status.HTTP_409_CONFLICT)
        if ses.scalars(select(User.id).where(func.lower(User.email) == new, User.id != u.id)).first():
            raise _bad("That email belongs to another account.", status.HTTP_409_CONFLICT)
        message = _send_code(ses, u, "verify_email", new)
    return _deliver(message)


@router.post("/email")
def change_email(body: EmailBody, cu: CurrentUser = Depends(current_user)) -> dict:
    try:
        return _change_email(body, cu)
    except IntegrityError:  # another account took this address at the same moment (QA-L-09)
        raise _bad("That email belongs to another account.", status.HTTP_409_CONFLICT) from None


def _change_email(body: EmailBody, cu: CurrentUser) -> dict:
    new = body.email.strip().lower()
    ok, conflict = False, False
    with db.session() as ses:
        u = _user(ses, cu)
        wait = rl.otp_limiter.retry_after(f"try:{u.id}", rl.OTP_TRY_PER_ACCOUNT, rl.WINDOW)
        if wait:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many attempts. Try again in {wait // 60 + 1} min.")
        rl.otp_limiter.hit(f"try:{u.id}")
        ok = otp.verify(ses, u, "verify_email", new, body.code)
        if ok:
            if ses.scalars(select(User.id).where(func.lower(User.email) == new, User.id != u.id)).first():
                conflict, ok = True, False
            else:
                u.email, u.email_verified_at = new, datetime.now(timezone.utc)
                ses.flush()
                return profile_out(u)
    if conflict:
        raise _bad("That email belongs to another account.", status.HTTP_409_CONFLICT)
    raise _bad("That code is invalid or has expired. Check it, or ask for a new one.", status.HTTP_400_BAD_REQUEST)


# --------------------------------------------------------------------------- #
# Password
# --------------------------------------------------------------------------- #
@router.post("/password/otp")
def password_code(cu: CurrentUser = Depends(current_user)) -> dict:
    """Email a code to the account address (for setting a first password)."""
    with db.session() as ses:
        u = _user(ses, cu)
        if u.password_hash:
            raise _bad("This account already has a password. Use change password, or sign out and use 'Forgot password'.",
                       status.HTTP_409_CONFLICT)
        if not u.email:
            raise _bad("Add an email address first: we send the code there.", status.HTTP_409_CONFLICT)
        message = _send_code(ses, u, "set_password", u.email)
    return _deliver(message)


class PasswordBody(BaseModel):
    new_password: str = Field(min_length=1, max_length=200)
    current_password: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=12)


@router.post("/password")
def set_password(body: PasswordBody, response: Response, cu: CurrentUser = Depends(current_user)) -> dict:
    problem: HTTPException | None = None
    csrf = ""
    with db.session() as ses:
        u = _user(ses, cu)
        wait = rl.otp_limiter.retry_after(f"pw:{u.id}", rl.OTP_TRY_PER_ACCOUNT, rl.WINDOW)
        if wait:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many attempts. Try again in {wait // 60 + 1} min.")
        issues = password_problems(body.new_password, u.username, u.email, u.name)
        if issues:
            problem = _bad("Choose a stronger password: " + ", ".join(issues) + ".")
        elif u.password_hash:
            rl.otp_limiter.hit(f"pw:{u.id}")
            if not body.current_password or not verify_password(body.current_password, u.password_hash):
                problem = _bad("Your current password isn't right.", status.HTTP_400_BAD_REQUEST)
            elif verify_password(body.new_password, u.password_hash):
                problem = _bad("Pick a password you haven't been using.")
        else:
            rl.otp_limiter.hit(f"pw:{u.id}")
            if not u.email or not body.code or not otp.verify(ses, u, "set_password", u.email, body.code):
                problem = _bad("That code is invalid or has expired. Check it, or ask for a new one.", status.HTTP_400_BAD_REQUEST)
        if problem is None:
            now = datetime.now(timezone.utc)
            u.password_hash = hash_password(body.new_password)
            u.password_changed_at = now
            u.email_verified_at = u.email_verified_at or (now if body.code else None)
            u.token_version += 1  # signs out every other device ...
            ses.flush()
            csrf = start_session(response, u)  # ... and re-signs this one
            log.info("password %s for user %s", "set" if body.code else "changed", u.id)
            out = profile_out(u)
    if problem:
        raise problem
    rl.otp_limiter.reset(f"pw:{cu.id}")
    return {"ok": True, "csrf": csrf, "profile": out}


@router.post("/sessions/revoke")
def revoke_other_sessions(response: Response, cu: CurrentUser = Depends(current_user)) -> dict:
    """Sign out everywhere else (bumps the session version) and keep this device signed in."""
    with db.session() as ses:
        u = _user(ses, cu)
        u.token_version += 1
        ses.flush()
        csrf = start_session(response, u)
    return {"ok": True, "csrf": csrf}
