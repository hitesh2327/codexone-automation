"""Request dependencies: the signed-in user, and CSRF for state-changing requests."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from api.app.security import cookie_name, csrf_matches, decode_session_token
from src import db
from src.db.models import User

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class CurrentUser:
    id: int
    username: str | None
    email: str | None
    name: str
    csrf: str


def current_user(request: Request) -> CurrentUser:
    token = request.cookies.get(cookie_name())
    claims = decode_session_token(token) if token else None
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    with db.session() as s:
        user = s.get(User, int(claims["sub"]))
        if not user or not user.is_active or user.token_version != claims["tv"]:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
        return CurrentUser(user.id, user.username, user.email, user.name, claims["csrf"])


def require_csrf(request: Request, user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if request.method not in SAFE_METHODS and not csrf_matches(user.csrf, request.headers.get("X-CSRF-Token")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
    return user


# Use on every protected router: signed in + CSRF on writes.
protected = [Depends(require_csrf)]
