"""Shared test setup: throwaway SQLite DB, fake secrets, no Telegram, no real publishing."""
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
    "TELEGRAM_SYNC": "false",          # never call Telegram from tests
    "PUBLISH_ENABLED": "true",         # publish_item is replaced by a fake in the tests that need it
    "GITHUB_DISPATCH_TOKEN": "",       # never trigger real workflows
    "GITHUB_REPOSITORY": "test-owner/test-repo",  # there is no owner default any more (R-20)
    "CONFIG_MASTER_KEY": "",           # config-store tests set their own throwaway key
}
os.environ.update(TEST_ENV)  # before importing the app (env beats .env)

from fastapi.testclient import TestClient  # noqa: E402

from api.app import ratelimit  # noqa: E402
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


@pytest.fixture()
def authed(client):
    """Signed-in client that sends the CSRF header on every request."""
    r = client.post("/api/auth/login", json=GOOD)
    assert r.status_code == 200
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    return client
