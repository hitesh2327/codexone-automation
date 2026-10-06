"""Passwords (bcrypt), session tokens (JWT in an httpOnly cookie) and CSRF.

CSRF: each session token carries a random `csrf` claim. /api/auth/me returns it to the
same-origin page, which sends it back as the X-CSRF-Token header on every non-GET
request. Other sites can't read that response, so they can't forge the header.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Response

from api.app.settings import settings

ALGORITHM = "HS256"
BCRYPT_MAX_BYTES = 72


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    raw = password.encode()
    if len(raw) > BCRYPT_MAX_BYTES:
        raise ValueError(f"password longer than {BCRYPT_MAX_BYTES} bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    raw = password.encode()
    if not hashed or len(raw) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, hashed.encode())
    except ValueError:
        return False


_COMMON = {"password", "password1", "password123", "1234567890", "12345678910", "qwertyuiop", "qwerty12345",
           "letmein123", "iloveyou123", "admin12345", "welcome123", "abc1234567", "changeme123"}


def password_problems(password: str, *identity: str | None) -> list[str]:
    """Why this password isn't acceptable (empty list = fine). `identity`: username/email/name to keep out of it."""
    out: list[str] = []
    if len(password) < 10:
        out.append("use at least 10 characters")
    if len(password.encode()) > BCRYPT_MAX_BYTES:
        out.append(f"keep it under {BCRYPT_MAX_BYTES} bytes")
    if len(set(password)) < 5:
        out.append("use a wider mix of characters")
    if password.lower() in _COMMON:
        out.append("that password is too common")
    low = password.lower()
    for ident in identity:
        piece = (ident or "").split("@")[0].strip().lower()
        if len(piece) >= 4 and piece in low:
            out.append("don't include your name or username")
            break
    return out


# A real hash to compare against when the user doesn't exist, so response time doesn't
# reveal whether a username is valid.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=12)).decode()


def burn_time() -> None:
    bcrypt.checkpw(b"x", _DUMMY_HASH.encode())


# --------------------------------------------------------------------------- #
# Session tokens
# --------------------------------------------------------------------------- #
def cookie_name() -> str:
    # __Host- prefix: browser only accepts it Secure, host-only, path=/ (no subdomain tricks).
    return "__Host-cx_session" if settings().cookie_secure else "cx_session"


def create_session_token(user_id: int, token_version: int) -> tuple[str, str]:
    """Returns (jwt, csrf_token)."""
    s = settings()
    now = datetime.now(timezone.utc)
    csrf = secrets.token_urlsafe(32)
    token = jwt.encode({"sub": str(user_id), "tv": token_version, "csrf": csrf, "typ": "session",
                        "iat": now, "exp": now + timedelta(hours=s.session_hours)},
                       s.jwt_secret, algorithm=ALGORITHM)
    return token, csrf


def decode_session_token(token: str) -> dict | None:
    try:
        claims = jwt.decode(token, settings().jwt_secret, algorithms=[ALGORITHM],
                            options={"require": ["sub", "exp", "tv", "csrf"]})
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == "session" else None


def set_session_cookie(response: Response, token: str) -> None:
    s = settings()
    response.set_cookie(cookie_name(), token, max_age=s.session_hours * 3600, httponly=True,
                        secure=s.cookie_secure, samesite="none" if s.cross_site else "lax", path="/")


def clear_session_cookie(response: Response) -> None:
    s = settings()
    response.delete_cookie(cookie_name(), path="/", secure=s.cookie_secure, httponly=True,
                           samesite="none" if s.cross_site else "lax")


def csrf_matches(expected: str | None, provided: str | None) -> bool:
    return bool(expected and provided) and hmac.compare_digest(expected, provided)
