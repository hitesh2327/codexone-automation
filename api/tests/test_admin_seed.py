"""QA-H-03 / QA-L-07: ADMIN_PASSWORD only seeds the first admin, once.

A renamed admin's old username never comes back as a login with the env password, a password-less (Google)
account is never given it, and ADMIN_PASSWORD_FORCE applies once per ADMIN_PASSWORD value.
The SQLite file is shared with the other tests: every test puts the admin back as it found it.
"""
from __future__ import annotations

import dataclasses

import pytest
from sqlalchemy import delete, select

from api.app import main as app_main
from api.app.security import hash_password, verify_password
from src import db
from src.db.models import Setting, User

from .conftest import GOOD

ENV_PW = GOOD["password"]


@pytest.fixture()
def admin(client):
    """The seeded admin (the client fixture's start-up seeded it); restored afterwards."""
    with db.session() as s:
        u = s.scalars(select(User).where(User.username == "admin")).one()
        uid, saved = u.id, (u.username, u.password_hash, u.token_version)
        seed = s.get(Setting, app_main.ADMIN_SEED)
        assert seed and seed.value["user_id"] == uid
        seed_value = dict(seed.value)
    yield uid
    with db.session() as s:
        s.execute(delete(User).where(User.username.in_(["admin", "planted"]), User.id != uid))
        u = s.get(User, uid)
        u.username, u.password_hash, u.token_version = saved
        row = s.get(Setting, app_main.ADMIN_SEED)
        if row:
            row.value = seed_value
        else:
            s.add(Setting(key=app_main.ADMIN_SEED, value=seed_value))


def _login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password}).status_code


def test_renamed_admin_old_username_never_returns(client, admin):
    with db.session() as s:
        u = s.get(User, admin)
        u.username, u.password_hash = "boss", hash_password("the-new-password-123")
    app_main.sync_admin()                                     # a Lambda cold start
    with db.session() as s:
        assert s.scalars(select(User).where(User.username == "admin")).first() is None
    assert _login(client, "admin", ENV_PW) == 401
    assert _login(client, "boss", "the-new-password-123") == 200


def test_env_password_never_planted_on_a_passwordless_account(client, admin, monkeypatch):
    with db.session() as s:
        s.add(User(username="planted", email="google.user@example.com", password_hash=None))
    real = app_main.settings()
    monkeypatch.setattr(app_main, "settings", lambda: dataclasses.replace(real, admin_username="planted"))
    app_main.sync_admin()
    with db.session() as s:                                   # also with no seed marker (pre-fix database)
        s.execute(delete(Setting).where(Setting.key == app_main.ADMIN_SEED))
    app_main.sync_admin()
    with db.session() as s:
        assert s.scalars(select(User).where(User.username == "planted")).one().password_hash is None
    assert _login(client, "planted", ENV_PW) == 401


def test_force_is_one_shot(client, admin, monkeypatch):
    with db.session() as s:
        s.get(User, admin).password_hash = hash_password("forgotten-password-1")
    monkeypatch.setenv("ADMIN_PASSWORD_FORCE", "true")
    app_main.sync_admin()                                     # locked out: force once
    with db.session() as s:
        u = s.get(User, admin)
        assert verify_password(ENV_PW, u.password_hash)
        tv = u.token_version
        u.password_hash = hash_password("chosen-after-force-2")  # the admin picks a new password
    app_main.sync_admin()                                     # flag left on: later cold starts
    app_main.sync_admin()
    with db.session() as s:
        u = s.get(User, admin)
        assert verify_password("chosen-after-force-2", u.password_hash) and u.token_version == tv
