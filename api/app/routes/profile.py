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
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from api.app import mailer, otp
from api.app import ratelimit as rl
from api.app.deps import CurrentUser, current_user
from api.app.routes.auth import avatar_version, start_session
from api.app.security import clear_session_cookie, hash_password, password_problems, verify_password
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
        "role": "Administrator" if (u.role or "client") in ("owner", "admin") else "Client",
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


def _validate_and_normalize_categories(raw_cats: object) -> list[dict]:
    from src.user_taste import MAX_CATEGORIES, clean_category_name, normalize_categories
    if not isinstance(raw_cats, list):
        raise _bad("Categories must be a list.")
    if len(raw_cats) > MAX_CATEGORIES:
        raise _bad(f"You can configure at most {MAX_CATEGORIES} categories.")
    for entry in raw_cats:
        raw_name = entry.get("name") or entry.get("label") or "" if isinstance(entry, dict) else entry
        try:
            clean_category_name(raw_name)
        except ValueError as e:
            raise _bad(str(e)) from None
        if isinstance(entry, dict) and "weight" in entry and entry["weight"] is not None:
            try:
                w = int(entry["weight"])
            except (TypeError, ValueError):
                raise _bad("Category weight must be an integer between 1 and 100.") from None
            if not 1 <= w <= 100:
                raise _bad("Category weight must be between 1 and 100.")
    return [c.to_dict() for c in normalize_categories(raw_cats)]


def _normalize_substack_locator(locator: str) -> str:
    loc = locator.strip()
    if "://" not in loc:
        slug = loc.lower().strip("/")
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,62}$", slug):
            raise _bad("Substack slug must be letters, numbers, and dashes, or a full https:// URL.")
        return f"https://{slug}.substack.com/feed"
    return loc


def _validate_and_normalize_sources(raw_sources: object) -> list[dict]:
    from src.fetch_topics import validate_safe_feed_url
    from src.user_taste import normalize_sources
    if not isinstance(raw_sources, list):
        raise _bad("Sources must be a list.")
    if len(raw_sources) > 20:
        raise _bad("You can configure at most 20 custom sources.")
    cleaned: list[dict] = []
    for entry in raw_sources:
        if not isinstance(entry, dict):
            raise _bad("Each source must be an object.")
        st = str(entry.get("source_type") or "").strip().lower()
        loc = str(entry.get("locator") or "").strip()
        if st not in ("rss", "substack", "reddit"):
            raise _bad("Source type must be 'rss', 'substack', or 'reddit'.")
        if not loc:
            raise _bad("Source locator cannot be empty.")
        if st == "reddit":
            sub = re.sub(r"^/?r/", "", loc)
            if not re.match(r"^[A-Za-z0-9_]{2,32}$", sub):
                raise _bad("Subreddit name must be 2-32 letters, numbers, or underscores.")
            loc = sub
        else:
            if st == "substack":
                loc = _normalize_substack_locator(loc)
            try:
                loc = validate_safe_feed_url(loc)
            except ValueError as e:
                raise _bad(str(e)) from None
        cleaned.append({
            "source_type": st,
            "locator": loc,
            "label": str(entry.get("label") or "").strip()[:80],
            "category": str(entry.get("category") or "").strip()[:64],
            "enabled": bool(entry.get("enabled", True)),
        })
    return [s.to_dict() for s in normalize_sources(cleaned)]


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
            t_in = dict(data["taste"])
            if "default_language" in t_in and t_in["default_language"] is not None:
                if t_in["default_language"] not in ("en", "hi"):
                    raise _bad("Default narration language must be 'en' or 'hi'.")
            if "default_post_format" in t_in and t_in["default_post_format"] is not None:
                if t_in["default_post_format"] not in ("carousel", "image_reel"):
                    raise _bad("Default post format must be 'carousel' or 'image_reel'.")
            if "categories" in t_in and t_in["categories"] is not None:
                if len(t_in["categories"]) == 0:
                    t_in.pop("categories")
                else:
                    t_in["categories"] = _validate_and_normalize_categories(t_in["categories"])
            if "sources" in t_in and t_in["sources"] is not None:
                t_in["sources"] = _validate_and_normalize_sources(t_in["sources"])
            current_taste = dict(u.taste or {})
            current_taste.update(t_in)
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
ai_limiter = rl.RateLimiter()
AI_RATE_LIMIT, AI_WINDOW = 5, 600  # max 5 requests per 10 minutes per user


def _check_ai_rate(user_id: int) -> None:
    key = f"ai_sug:{user_id}"
    if wait := ai_limiter.retry_after(key, AI_RATE_LIMIT, AI_WINDOW):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many AI requests. Please wait {wait // 60 + 1} min before trying again.",
            headers={"Retry-After": str(wait)},
        )
    ai_limiter.hit(key)

@router.post("/suggest-schedule")
def suggest_schedule(cu: CurrentUser = Depends(current_user)) -> dict:
    """Ask Gemini for optimal posting times based on the user's niche and platforms."""
    _check_ai_rate(cu.id)
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


class SuggestCategoriesBody(BaseModel):
    niche: str | None = Field(default=None, max_length=120)
    content_type: str | None = Field(default=None, max_length=120)
    target_audience: str | None = Field(default=None, max_length=200)


@router.post("/suggest-categories")
def suggest_categories(
    body: SuggestCategoriesBody | None = Body(default=None),
    cu: CurrentUser = Depends(current_user),
) -> dict:
    """Ask Gemini to suggest 4-6 content categories for the user's niche."""
    _check_ai_rate(cu.id)
    import json as _json
    from src.config import get_env
    try:
        from google import genai
    except ImportError:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Gemini SDK not available")

    with db.session() as ses:
        u = _user(ses, cu)
        taste = dict(u.taste or {})

    niche = (body.niche.strip() if body and body.niche and body.niche.strip() else None) or taste.get("niche") or "Software Engineering & Dev"
    content_type = (body.content_type.strip() if body and body.content_type and body.content_type.strip() else None) or taste.get("content_type") or "Educational & How-To"
    audience = (body.target_audience.strip() if body and body.target_audience and body.target_audience.strip() else None) or taste.get("target_audience") or ""

    prompt = (
        f"You are a social media content strategist.\n\n"
        f"Creator profile:\n"
        f"- Niche: {niche}\n"
        f"- Content type: {content_type}\n"
        f"- Target audience: {audience or 'general'}\n\n"
        f"Suggest exactly 5 distinct content pillars/categories for this creator. "
        f"Each category should be a short label (1-3 words), have a 1-sentence description, "
        f"a relative weight (integer 1-100 summing near 100), and a short prompt_style directive. "
        f"Also suggest 3-5 relevant public subreddit names (without the r/ prefix).\n\n"
        f"Return ONLY valid JSON: "
        f'{{"categories": [{{"name": "Cat1", "description": "What fits here", "weight": 25, "prompt_style": "Tone/angle"}}], '
        f'"suggested_subreddits": ["sub1", "sub2"], "reasoning": "one sentence"}}'
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

    raw_cats = result.get("categories", [])
    if not isinstance(raw_cats, list) or len(raw_cats) < 2:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Unexpected response from Gemini; try again.")
    from src.user_taste import normalize_categories
    configs = normalize_categories(raw_cats[:8])
    if len(configs) < 2:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Unexpected response from Gemini; try again.")
    subs = [
        re.sub(r"^/?r/", "", str(s).strip())
        for s in (result.get("suggested_subreddits") or [])
        if re.match(r"^[A-Za-z0-9_]{2,32}$", re.sub(r"^/?r/", "", str(s).strip()))
    ][:6]
    return {
        "categories": [c.name for c in configs],
        "category_configs": [c.to_dict() for c in configs],
        "suggested_subreddits": subs,
        "reasoning": result.get("reasoning", ""),
    }


# --------------------------------------------------------------------------- #
# Dynamic Categories & Custom Sources
# --------------------------------------------------------------------------- #
source_test_limiter = rl.RateLimiter()
SOURCE_TEST_LIMIT, SOURCE_TEST_WINDOW = 10, 60


class CategoriesPutBody(BaseModel):
    categories: list[dict | str] = Field(min_length=1, max_length=12)
    sources: list[dict] | None = None


class SourceTestBody(BaseModel):
    source_type: Literal["rss", "substack", "reddit"] = "rss"
    locator: str = Field(min_length=1, max_length=500)


@router.get("/categories")
def get_categories(cu: CurrentUser = Depends(current_user)) -> dict:
    """Return the user's normalized category configs and custom topic sources."""
    from src.user_taste import get_user_taste
    taste = get_user_taste(cu.id)
    return {
        "niche": taste.niche,
        "categories": [c.to_dict() for c in taste.category_configs],
        "sources": [s.to_dict() for s in taste.sources],
    }


@router.put("/categories")
def put_categories(body: CategoriesPutBody, cu: CurrentUser = Depends(current_user)) -> dict:
    """Save the user's weighted categories (1-12) and optional custom sources."""
    norm_cats = _validate_and_normalize_categories(body.categories)
    if not norm_cats:
        raise _bad("At least 1 valid category is required.")
    norm_sources = _validate_and_normalize_sources(body.sources) if body.sources is not None else None

    with db.session() as ses:
        u = _user(ses, cu)
        current_taste = dict(u.taste or {})
        current_taste["categories"] = norm_cats
        if norm_sources is not None:
            current_taste["sources"] = norm_sources
        u.taste = current_taste
        ses.flush()
    try:
        from src.user_taste import invalidate as _inv
        _inv(cu.id)
    except Exception:  # noqa: BLE001
        pass
    from src.user_taste import get_user_taste
    taste = get_user_taste(cu.id)
    return {
        "niche": taste.niche,
        "categories": [c.to_dict() for c in taste.category_configs],
        "sources": [s.to_dict() for s in taste.sources],
    }


@router.post("/sources/test")
def test_source(body: SourceTestBody, cu: CurrentUser = Depends(current_user)) -> dict:
    """SSRF-validate and live-test a custom RSS, Substack, or Reddit source (up to 3 headlines)."""
    if wait := source_test_limiter.retry_after(f"src_test:{cu.id}", SOURCE_TEST_LIMIT, SOURCE_TEST_WINDOW):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many feed tests. Try again in {wait}s.",
            headers={"Retry-After": str(wait)},
        )
    source_test_limiter.hit(f"src_test:{cu.id}")

    import requests as _requests
    from src.fetch_topics import _session, fetch_reddit, fetch_rss, validate_safe_feed_url

    loc = body.locator.strip()
    if body.source_type == "reddit":
        sub = re.sub(r"^/?r/", "", loc)
        if not re.match(r"^[A-Za-z0-9_]{2,32}$", sub):
            raise _bad("Subreddit name must be 2-32 letters, numbers, or underscores.")
        try:
            items = fetch_reddit(_session(), limit=3, subs=[sub])
        except Exception as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not fetch r/{sub}: {e}") from None
        return {
            "ok": True,
            "resolved_url": f"https://www.reddit.com/r/{sub}",
            "headlines": [{"title": t.title, "url": t.url, "published": t.published} for t in items[:3]],
        }

    if body.source_type == "substack":
        loc = _normalize_substack_locator(loc)

    try:
        safe_url = validate_safe_feed_url(loc)
    except ValueError as e:
        raise _bad(str(e)) from None

    try:
        items = fetch_rss(_session(), safe_url, limit=3)
    except ValueError as e:
        raise _bad(str(e)) from None
    except _requests.RequestException as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not fetch feed: {e}") from None

    return {
        "ok": True,
        "resolved_url": safe_url,
        "headlines": [{"title": t.title, "url": t.url, "published": t.published} for t in items[:3]],
    }


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
def change_email(body: EmailBody, response: Response, cu: CurrentUser = Depends(current_user)) -> dict:
    try:
        return _change_email(body, cu, response)
    except IntegrityError:  # another account took this address at the same moment (QA-L-09)
        raise _bad("That email belongs to another account.", status.HTTP_409_CONFLICT) from None


def _change_email(body: EmailBody, cu: CurrentUser, response: Response | None = None) -> dict:
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
                u.token_version += 1
                if response is not None:
                    start_session(response, u)
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


# --------------------------------------------------------------------------- #
# Delete the account (src/account_deletion.py)
# --------------------------------------------------------------------------- #
@router.post("/delete/otp")
def delete_code(cu: CurrentUser = Depends(current_user)) -> dict:
    """Email a code that proves it's really you (accounts without a password, e.g. Google sign-in)."""
    with db.session() as ses:
        u = _user(ses, cu)
        if not u.email:
            raise _bad("This account has no email address to send a code to.", status.HTTP_409_CONFLICT)
        message = _send_code(ses, u, "delete_account", u.email)
    return _deliver(message)


class DeleteBody(BaseModel):
    confirm: str = Field(max_length=20)                       # the word DELETE, typed
    current_password: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=12)


@router.post("/delete")
def delete_account(body: DeleteBody, response: Response, cu: CurrentUser = Depends(current_user)) -> dict:
    """Close the account and erase its data, after proof: the password, or an emailed code without one."""
    from src import account_deletion
    if body.confirm.strip() != "DELETE":
        raise _bad("Type DELETE to confirm.")
    with db.session() as ses:
        u = _user(ses, cu)
        wait = rl.otp_limiter.retry_after(f"del:{u.id}", rl.OTP_TRY_PER_ACCOUNT, rl.WINDOW)
        if wait:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many attempts. Try again in {wait // 60 + 1} min.")
        rl.otp_limiter.hit(f"del:{u.id}")
        if u.password_hash:
            proven = bool(body.current_password) and verify_password(body.current_password, u.password_hash)
            wrong = "Your password isn't right."
        else:
            proven = bool(u.email and body.code) and otp.verify(ses, u, "delete_account", u.email, body.code)
            wrong = "That code is invalid or has expired. Check it, or ask for a new one."
    if not proven:
        raise _bad(wrong, status.HTTP_400_BAD_REQUEST)
    try:
        removed = account_deletion.delete_account(cu.id)
    except account_deletion.DeletionError as e:
        status_map = {"not_found": 404, "owner": 409, "billing": 502}
        code = status_map.get(e.code, status.HTTP_400_BAD_REQUEST)
        raise HTTPException(code, detail={"code": e.code, "message": e.message}) from None
    clear_session_cookie(response)
    log.info("account %s deleted (%s posts, %s media files)", cu.id, removed["posts"], removed["media_files"])
    return {"ok": True, **removed}


@router.post("/sessions/revoke")
def revoke_other_sessions(response: Response, cu: CurrentUser = Depends(current_user)) -> dict:
    """Sign out everywhere else (bumps the session version) and keep this device signed in."""
    with db.session() as ses:
        u = _user(ses, cu)
        u.token_version += 1
        ses.flush()
        csrf = start_session(response, u)
    return {"ok": True, "csrf": csrf}
