"""Request dependencies: the signed-in user, RBAC, impersonation read-only guard, and CSRF."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status

from api.app.security import cookie_name, csrf_matches, decode_session_token
from api.app.settings import settings
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
    role: str = "client"
    impersonated_by: int | None = None
    read_only: bool = False
    impersonation_expires_at: str | None = None
    impersonation_reason: str | None = None


def access_allowed(user: User) -> bool:
    """In multi-user SaaS mode, all active accounts are allowed. If allowed_google_emails is configured and not '*', it checks against the allowlist."""
    if not user.via_google or not settings().allowed_google_emails or "*" in settings().allowed_google_emails:
        return True
    return (user.email or "").lower() in settings().allowed_google_emails


def current_user(request: Request) -> CurrentUser:
    token = request.cookies.get(cookie_name())
    claims = decode_session_token(token) if token else None
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    with db.session() as s:
        user = s.get(User, int(claims["sub"]))
        if not user or not user.is_active or user.token_version != claims["tv"] or not access_allowed(user):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
        if claims.get("typ") == "impersonation":
            if (user.role or "client") != "client":
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Impersonation target must be a client account")
            admin_user = s.get(User, int(claims["impersonated_by"]))
            if (
                not admin_user
                or not admin_user.is_active
                or (admin_user.role or "client") not in ("owner", "admin")
                or admin_user.token_version != claims.get("atv")
            ):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Impersonation session expired")
            exp_iso = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc).isoformat(timespec="seconds")
            return CurrentUser(
                user.id,
                user.username,
                user.email,
                user.name,
                claims["csrf"],
                user.role or "client",
                impersonated_by=admin_user.id,
                read_only=bool(claims.get("read_only", True)),
                impersonation_expires_at=exp_iso,
                impersonation_reason=claims.get("reason"),
            )
        return CurrentUser(user.id, user.username, user.email, user.name, claims["csrf"], user.role or "client")


def require_csrf(request: Request, user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if request.method not in SAFE_METHODS and not csrf_matches(user.csrf, request.headers.get("X-CSRF-Token")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
    if (
        user.impersonated_by is not None
        and user.read_only
        and request.method not in SAFE_METHODS
        and request.url.path != "/api/admin/impersonation/exit"
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "impersonation_read_only",
                "message": "Read-only support impersonation is active: write operations are disabled.",
            },
        )
    return user


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if user.impersonated_by is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Exit support impersonation before accessing admin endpoints")
    if user.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


# Use on every protected router: signed in + CSRF on writes + read-only impersonation guard.
protected = [Depends(require_csrf)]
