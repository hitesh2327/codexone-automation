"""FastAPI app. Run locally:

    uvicorn api.app.main:app --reload --port 8000        # from the repo root

Every /api route except auth + public ones requires a session (see deps.protected).
If web/dist exists (production build), the SPA is served from here too (same origin).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from api.app.deps import protected
from api.app.routes import auth, public
from api.app.security import hash_password, verify_password
from api.app.settings import settings
from src import db
from src.db.models import User

log = logging.getLogger("codexone.api")
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def sync_admin() -> None:
    """Create the password admin from ADMIN_USERNAME/ADMIN_PASSWORD, or update its password."""
    s = settings()
    if not (s.admin_username and s.admin_password):
        log.warning("ADMIN_USERNAME/ADMIN_PASSWORD not set: no password admin")
        return
    with db.session() as ses:
        user = ses.scalars(select(User).where(func.lower(User.username) == s.admin_username.lower())).first()
        if user is None:
            ses.add(User(username=s.admin_username, password_hash=hash_password(s.admin_password), name="Admin"))
            log.info("admin %r created", s.admin_username)
        elif not verify_password(s.admin_password, user.password_hash):
            user.password_hash = hash_password(s.admin_password)
            user.token_version += 1  # password changed: sign out existing sessions
            log.info("admin %r password updated from env", s.admin_username)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings()  # fail fast on bad config
    sync_admin()
    yield


def create_app() -> FastAPI:
    s = settings()
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

    # Everything else under /api: signed in + CSRF on writes. Later phases add routers here.
    api = APIRouter(prefix="/api", dependencies=protected)

    @api.get("/session/ping")
    def ping() -> dict:
        return {"ok": True}

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
