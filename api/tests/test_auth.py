"""Auth tests: password login, sessions, CSRF, logout, rate limit, Google allowlist.

Run from the repo root:  python -m pytest api/tests -q
Uses a throwaway SQLite file; never touches Postgres.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp())
TEST_ENV = {
    "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "JWT_SECRET": "t" * 48,
    "SESSION_SECRET": "s" * 48,
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "correct horse battery",
    "COOKIE_SECURE": "false",
    "PUBLIC_URL": "http://testserver",
    "GOOGLE_WEB_CLIENT_ID": "test.apps.googleusercontent.com",
    "GOOGLE_WEB_CLIENT_SECRET": "secret",
    "ALLOWED_GOOGLE_EMAILS": "allowed@example.com, Other@Example.com",
}
os.environ.update(TEST_ENV)  # before importing the app (env beats .env)

from fastapi.testclient import TestClient  # noqa: E402

from api.app import ratelimit  # noqa: E402
from api.app.routes import auth as auth_routes  # noqa: E402
from api.app.settings import settings  # noqa: E402
from src import db  # noqa: E402
from src.config import load_brand  # noqa: E402
from src.db.models import Base  # noqa: E402

for fn in (settings, db.engine, db._sessionmaker, load_brand):
    fn.cache_clear()
Base.metadata.create_all(db.engine())

from api.app.main import create_app  # noqa: E402

GOOD = {"username": "admin", "password": "correct horse battery"}


@pytest.fixture()
def client():
    ratelimit.login_limiter._hits.clear()
    with TestClient(create_app()) as c:  # runs lifespan -> seeds the admin
        yield c


def login(client, body=GOOD):
    return client.post("/api/auth/login", json=body)


def test_providers_public(client):
    assert client.get("/api/auth/providers").json() == {"password": True, "google": True}


def test_protected_requires_session(client):
    assert client.get("/api/session/ping").status_code == 401


def test_wrong_password_rejected(client):
    r = login(client, {"username": "admin", "password": "nope"})
    assert r.status_code == 401 and "cx_session" not in r.cookies


def test_unknown_user_same_error(client):
    r = login(client, {"username": "ghost", "password": "nope"})
    assert r.status_code == 401 and r.json()["detail"] == "Wrong username or password"


def test_login_sets_httponly_cookie_and_returns_csrf(client):
    r = login(client)
    assert r.status_code == 200
    assert r.json()["username"] == "admin" and len(r.json()["csrf"]) > 20
    cookie = r.headers["set-cookie"].lower()
    assert "cx_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/session/ping").status_code == 200
    assert client.get("/api/auth/me").json()["csrf"] == r.json()["csrf"]


def test_username_case_insensitive(client):
    assert login(client, {"username": "ADMIN", "password": GOOD["password"]}).status_code == 200


def test_login_requires_json(client):
    r = client.post("/api/auth/login", data=GOOD)  # form-encoded, like a cross-site HTML form
    assert r.status_code in (415, 422)


def test_writes_need_csrf_and_logout_kills_all_sessions(client):
    csrf = login(client).json()["csrf"]
    old_cookie = client.cookies.get("cx_session")
    assert client.post("/api/auth/logout").status_code == 403                      # no header
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "x" * 43}).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    client.cookies.set("cx_session", old_cookie)                                   # replay old token
    assert client.get("/api/session/ping").status_code == 401


def test_rate_limit_after_five_failures(client):
    for _ in range(ratelimit.PER_ACCOUNT):
        assert login(client, {"username": "admin", "password": "bad"}).status_code == 401
    r = login(client)  # right password, but locked out
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_tampered_token_rejected(client):
    login(client)
    token = client.cookies.get("cx_session")
    client.cookies.set("cx_session", token[:-2] + ("A" if token[-1] != "A" else "B") + token[-1])
    assert client.get("/api/session/ping").status_code == 401


def test_security_headers(client):
    h = client.get("/api/auth/providers").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["cache-control"] == "no-store"


def test_unknown_api_route_404(client):
    assert client.get("/api/nope").status_code == 404


class _FakeGoogle:
    def __init__(self, info):
        self.info = info

    async def authorize_access_token(self, request):
        return {"userinfo": self.info}


@pytest.mark.parametrize("email,verified,allowed", [
    ("allowed@example.com", True, True),
    ("other@example.com", True, True),        # allowlist is case-insensitive
    ("intruder@example.com", True, False),
    ("allowed@example.com", False, False),    # unverified email
])
def test_google_allowlist(client, monkeypatch, email, verified, allowed):
    monkeypatch.setattr(auth_routes, "_google", lambda: _FakeGoogle({"email": email, "email_verified": verified}))
    r = client.get("/api/auth/google/callback", follow_redirects=False)
    assert r.status_code == 303
    if allowed:
        assert r.headers["location"] == "http://testserver/" and "cx_session=" in r.headers.get("set-cookie", "")
        assert client.get("/api/auth/me").json()["email"] == email
    else:
        assert r.headers["location"].startswith("http://testserver/login?error=")
        assert "cx_session=" not in r.headers.get("set-cookie", "")
