"""FastAPI app. Run locally:

    uvicorn api.app.main:app --reload --port 8000        # from the repo root

Every /api route except auth + public ones requires a session (see deps.protected).
If web/dist exists (production build), the SPA is served from here too (same origin).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from api.app.deps import protected
from api.app.routes import auth, config, dashboard, generate, logs, posts, profile, public, recovery, subscription
from api.app.security import hash_password, verify_password
from api.app.settings import settings
from src import db, redact
from src.config import get_env
from src.db.models import User

log = logging.getLogger("codexone.api")
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def _force_env_password() -> bool:
    return (get_env("ADMIN_PASSWORD_FORCE", required=False, default="false") or "").strip().lower() in ("1", "true", "yes")


ADMIN_SEED = "admin_seed"  # settings row: {"user_id", "at", "forced": HMAC marker of the last forced password}


def _force_marker(password: str) -> str:
    """Which env password a FORCE was applied for, without storing anything guessable offline (keyed by JWT_SECRET)."""
    return hmac.new(settings().jwt_secret.encode(), b"admin-force|" + password.encode(), hashlib.sha256).hexdigest()[:32]


def sync_admin() -> None:
    """Seed the password admin from ADMIN_USERNAME/ADMIN_PASSWORD exactly once (QA-H-03).

    The env password only seeds the account: on the first start with no password account at all, the admin is
    created and its id recorded (settings "admin_seed"). From then on the account is the user's own: it can be
    renamed, its password changed from the profile page or the emailed-code reset, and a restart never creates
    it again or puts the env password on any account (not on a renamed admin's old username, not on a
    Google-only account that happens to carry that username).

    Locked out: start with ADMIN_PASSWORD_FORCE=true. It sets the env password on the seeded account ONCE per
    distinct ADMIN_PASSWORD value (QA-L-07): left on, later cold starts only log a warning, so it can't
    silently revert a password changed afterwards. To force again, change ADMIN_PASSWORD.
    """
    from sqlalchemy.exc import IntegrityError
    from src.db.models import Setting
    s = settings()
    if not (s.admin_username and s.admin_password):
        log.warning("ADMIN_USERNAME/ADMIN_PASSWORD not set: no password admin")
        return
    force = _force_env_password()
    try:
        with db.session() as ses:
            row = ses.get(Setting, ADMIN_SEED)
            seed = dict(row.value) if row and isinstance(row.value, dict) else None
            if seed is None:
                named = ses.scalars(select(User).where(func.lower(User.username) == s.admin_username.lower())).first()
                if named is not None and named.password_hash:
                    seed = {"user_id": named.id}       # seeded before this marker existed: adopt, never overwrite
                elif ses.scalar(select(func.count()).select_from(User).where(User.password_hash.is_not(None))):
                    log.warning("ADMIN_USERNAME %r matches no password account, but password accounts exist: "
                                "not creating another admin (the env password only seeds a new install)", s.admin_username)
                    return
                elif named is not None:
                    log.warning("ADMIN_USERNAME %r belongs to an account without a password (e.g. Google sign-in): "
                                "not giving it the env password; choose another ADMIN_USERNAME", s.admin_username)
                    return
                else:
                    user = User(username=s.admin_username, password_hash=hash_password(s.admin_password), name="Admin")
                    ses.add(user)
                    ses.flush()
                    seed = {"user_id": user.id}
                    log.info("admin %r created", s.admin_username)
                seed["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if row:
                    row.value = seed
                else:
                    row = Setting(key=ADMIN_SEED, value=seed)
                    ses.add(row)
            if not force:
                return
            user = ses.get(User, seed.get("user_id"))
            marker = _force_marker(s.admin_password)
            if user is None:
                log.warning("ADMIN_PASSWORD_FORCE is set but the seeded admin account no longer exists; nothing changed")
            elif seed.get("forced") == marker:
                log.warning("ADMIN_PASSWORD_FORCE is still set: it was already applied for this ADMIN_PASSWORD and is "
                            "ignored now. Remove it (or change ADMIN_PASSWORD to force again).")
            else:
                if not (user.password_hash and verify_password(s.admin_password, user.password_hash)):
                    user.password_hash = hash_password(s.admin_password)
                    user.token_version += 1  # password changed: sign out existing sessions
                    log.warning("ADMIN_PASSWORD_FORCE: password of admin %r (id %s) set from env; remove the flag now",
                                user.username, user.id)
                row.value = {**seed, "forced": marker}
    except IntegrityError:  # another cold start seeded at the same moment
        log.info("admin seed done by a concurrent start")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings()  # fail fast on bad config
    from api.app import mailer
    mailer.startup_check()  # loud if reset codes can't be delivered (QA-M-07)
    sync_admin()
    yield


def create_app() -> FastAPI:
    s = settings()
    redact.install()  # scrub secrets from every log line, including the host's root handlers (Lambda, uvicorn)
    app = FastAPI(title="codexone admin", lifespan=lifespan,
                  docs_url="/api/docs" if s.debug else None, redoc_url=None, openapi_url="/api/openapi.json" if s.debug else None)

    # Signed cookie holding only the OAuth state/nonce during the Google redirect.
    app.add_middleware(SessionMiddleware, secret_key=s.session_secret, session_cookie="cx_oauth",
                       max_age=600, same_site="lax", https_only=s.cookie_secure)
    if s.cross_site:
        app.add_middleware(CORSMiddleware, allow_origins=[s.web_origin], allow_credentials=True,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Content-Type", "X-CSRF-Token"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if s.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(public.router)
    app.include_router(auth.router)
    app.include_router(recovery.router)  # public: forgot / reset password
    app.include_router(subscription.public_router, prefix="/api")

    # Everything else under /api: signed in + CSRF on writes. Later phases add routers here.
    api = APIRouter(prefix="/api", dependencies=protected)

    @api.get("/session/ping")
    def ping() -> dict:
        return {"ok": True}

    api.include_router(dashboard.router)
    api.include_router(posts.router)
    api.include_router(generate.router)
    api.include_router(logs.router)
    api.include_router(profile.router)
    api.include_router(config.router)
    api.include_router(subscription.router)
    app.include_router(api)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_not_found(path: str):
        return JSONResponse({"detail": "Not found"}, status_code=404)

    if WEB_DIST.exists():  # production: serve the built SPA from the same origin
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = (WEB_DIST / path).resolve()
            if path and f.is_file() and WEB_DIST in f.parents:
                return FileResponse(f)
            return FileResponse(WEB_DIST / "index.html")

    return app


app = create_app()
