"""Sign-in: username/password (bcrypt) or Google (Authlib, allowlisted emails only)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from api.app import ratelimit as rl
from api.app.clientip import client_ip
from api.app.deps import CurrentUser, access_allowed, current_user, require_csrf
from api.app.security import check_password, clear_session_cookie, create_session_token, hash_password, password_problems, set_session_cookie
from api.app.settings import settings
from src import activity, db
from src.db.models import User

log = logging.getLogger("codexone.api.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

oauth = OAuth()
_google_registered = False

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


def _google():
    global _google_registered
    s = settings()
    if not s.google_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google sign-in is not configured")
    if not _google_registered:
        oauth.register(name="google", client_id=s.google_client_id, client_secret=s.google_client_secret,
                       server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                       client_kwargs={"scope": "openid email profile", "prompt": "select_account"})
        _google_registered = True
    return oauth.google


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class SignupBody(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(default="", max_length=128)


def avatar_version(u: User) -> int | None:
    """Changes whenever the picture does; the page adds it to the image URL to bust its cache."""
    if not (u.avatar and u.avatar_updated_at):
        return None
    ts = u.avatar_updated_at
    return int((ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).timestamp())


def _user_out(u: User, csrf: str) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "name": u.name or u.username or u.email,
        "csrf": csrf,
        "has_password": bool(u.password_hash),
        "avatar_v": avatar_version(u),
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


def start_session(response: Response, user: User) -> str:
    token, csrf = create_session_token(user.id, user.token_version)
    set_session_cookie(response, token)
    return csrf


@router.get("/providers")
def providers() -> dict:
    """Public: which sign-in options the login page should show."""
    return {"password": True, "google": settings().google_enabled}


@router.post("/signup")
def signup(body: SignupBody, request: Request, response: Response) -> dict:
    if "application/json" not in request.headers.get("content-type", ""):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "JSON body required")
    username = body.username.strip().lower()
    email = body.email.strip().lower()
    name = body.name.strip()

    if not USERNAME_RE.match(username):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Username must be 3-32 chars (letters, numbers, dots, dashes, underscores).")
    if not EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid email address.")

    issues = password_problems(body.password, username, email, name)
    if issues:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a stronger password: " + ", ".join(issues) + ".")

    ip = client_ip(request)
    with db.session() as s:
        existing = s.scalars(select(User).where(or_(func.lower(User.username) == username,
                                                   func.lower(User.email) == email))).first()
        if existing:
            if existing.username and existing.username.lower() == username:
                raise HTTPException(status.HTTP_409_CONFLICT, "That username is already registered.")
            raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered.")

        user = User(
            username=username,
            email=email,
            name=name or username,
            password_hash=hash_password(body.password),
            config_completed=False,
            subscription_tier="free",
            subscription_status="active",
            taste={
                "niche": "AI & Tech",
                "tone": "Engaging & Informative",
                "aesthetic": "Modern Minimalist",
                "default_targets": ["ig", "yt"],
            },
            cadence={
                "posts_per_day": 2,
                "slots": ["10:00", "18:00"],
            },
        )
        s.add(user)
        s.flush()
        user.last_login_at = datetime.now(timezone.utc)
        csrf = start_session(response, user)
        log.info("signup: %s (%s) from %s", username, email, ip)
        activity.record("signup.success", f"Registered new user account {username}", source="auth", actor=username, user_id=user.id)
        return _user_out(user, csrf)


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    if "application/json" not in request.headers.get("content-type", ""):
        # HTML forms can't send JSON cross-site without a CORS preflight: blocks login CSRF.
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "JSON body required")
    ip = client_ip(request)  # the real visitor, not CloudFront's edge (QA-M-05)
    account_key, ip_key = f"acct:{ip}:{body.username.lower()}", f"ip:{ip}"
    wait = max(rl.login_limiter.retry_after(account_key, rl.PER_ACCOUNT, rl.WINDOW),
               rl.login_limiter.retry_after(ip_key, rl.PER_IP, rl.WINDOW))
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Too many failed attempts. Try again in {wait // 60 + 1} min.",
                            headers={"Retry-After": str(wait)})

    with db.session() as s:
        ident = body.username.strip().lower()
        user = s.scalars(select(User).where(or_(func.lower(User.username) == ident,
                                                func.lower(User.email) == ident))).first()
        # bcrypt runs on every attempt (a dummy hash when there is no account / no password), so timing can't tell
        # unknown, Google-only and disabled accounts apart (QA-L-05); the other checks come after it.
        password_ok = check_password(body.password, user.password_hash if user else None)
        ok = password_ok and bool(user and user.is_active and access_allowed(user))
        if not ok:
            rl.login_limiter.hit(account_key)
            rl.login_limiter.hit(ip_key)
            # Never the typed name: it may be a password typed into the wrong box (QA-L-08).
            log.warning("failed login for %s from %s", f"account {user.id}" if user else "an unknown name", ip)
            # Only a real account name is kept (a mistyped password in the username box must not reach the log).
            activity.record("login.failed", "Failed sign-in" + ("" if user else " (no such account)"), level="warning",
                            source="auth", actor=(user.username or user.email) if user else "unknown")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
        user.last_login_at = datetime.now(timezone.utc)
        rl.login_limiter.reset(account_key)
        csrf = start_session(response, user)
        log.info("login: %s from %s", user.username or user.email, ip)
        activity.record("login.success", "Signed in with password", source="auth", actor=user.username or user.email)
        return _user_out(user, csrf)


@router.post("/logout")
def logout(response: Response, user: CurrentUser = Depends(require_csrf)) -> dict:
    with db.session() as s:
        row = s.get(User, user.id)
        if row:
            row.token_version += 1  # invalidates every session issued so far
    activity.record("logout", "Signed out", source="auth", actor=user.username or user.email)
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)) -> dict:
    with db.session() as s:
        row = s.get(User, user.id)
        return _user_out(row, user.csrf)


# --------------------------------------------------------------------------- #
# Google
# --------------------------------------------------------------------------- #
def _login_redirect(error: str) -> RedirectResponse:
    return RedirectResponse(f"{settings().public_url}/login?error={quote(error)}", status_code=303)


@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = f"{settings().public_url}/api/auth/google/callback"
    return await _google().authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request):
    try:
        token = await _google().authorize_access_token(request)
    except OAuthError as e:
        log.warning("google oauth error: %s", e.error)
        return _login_redirect("Google sign-in was cancelled or failed. Please try again.")
    info = token.get("userinfo") or {}
    email = (info.get("email") or "").lower()
    if not email or not info.get("email_verified"):
        return _login_redirect("Your Google account has no verified email.")
    if email not in settings().allowed_google_emails:
        log.warning("google login refused for %s (not in ALLOWED_GOOGLE_EMAILS)", email)
        activity.record("login.failed", "Google sign-in refused: email is not on the allowlist", level="warning",
                        source="auth", actor=email)
        return _login_redirect(f"{email} is not allowed to sign in.")

    response = RedirectResponse(f"{settings().public_url}/", status_code=303)
    with db.session() as s:
        user = s.scalars(select(User).where(func.lower(User.email) == email)).first()
        if user is None:
            user = User(email=email, name=info.get("name") or "", via_google=True)
            s.add(user)
            s.flush()
        if not user.is_active:
            return _login_redirect("This account is disabled.")
        user.last_login_at = datetime.now(timezone.utc)
        start_session(response, user)
    log.info("login via google: %s", email)
    activity.record("login.success", "Signed in with Google", source="auth", actor=email)
    return response
