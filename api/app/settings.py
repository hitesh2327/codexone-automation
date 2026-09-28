"""API configuration from the environment (.env locally, host env vars in production)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.config import get_env


def _bool(name: str, default: bool) -> bool:
    v = get_env(name, required=False)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    session_secret: str
    session_hours: int
    cookie_secure: bool
    public_url: str                 # browser-facing origin, e.g. https://admin.example.com
    web_origin: str | None          # set only when the web app is on a different origin (CORS)
    admin_username: str | None
    admin_password: str | None
    google_client_id: str | None
    google_client_secret: str | None
    allowed_google_emails: frozenset[str]
    debug: bool

    @property
    def cross_site(self) -> bool:
        return bool(self.web_origin) and self.web_origin.rstrip("/") != self.public_url.rstrip("/")

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.allowed_google_emails)


@lru_cache(maxsize=1)
def settings() -> Settings:
    jwt_secret = get_env("JWT_SECRET")
    if len(jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters (python -c \"import secrets; print(secrets.token_urlsafe(48))\")")
    emails = get_env("ALLOWED_GOOGLE_EMAILS", required=False, default="") or ""
    return Settings(
        jwt_secret=jwt_secret,
        session_secret=get_env("SESSION_SECRET", required=False) or jwt_secret[::-1],
        session_hours=int(get_env("SESSION_HOURS", required=False, default="12")),
        cookie_secure=_bool("COOKIE_SECURE", True),
        public_url=(get_env("PUBLIC_URL", required=False, default="http://localhost:5173") or "").rstrip("/"),
        web_origin=get_env("WEB_ORIGIN", required=False),
        admin_username=get_env("ADMIN_USERNAME", required=False),
        admin_password=get_env("ADMIN_PASSWORD", required=False),
        google_client_id=get_env("GOOGLE_WEB_CLIENT_ID", required=False),
        google_client_secret=get_env("GOOGLE_WEB_CLIENT_SECRET", required=False),
        allowed_google_emails=frozenset(e.strip().lower() for e in emails.split(",") if e.strip()),
        debug=_bool("API_DEBUG", False),
    )
