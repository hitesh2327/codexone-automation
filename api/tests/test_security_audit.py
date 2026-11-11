"""Defensive security verification tests confirming resolutions for MNT-1201 through MNT-1209."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from sqlalchemy import delete, select

from src import activity, db, generation, queue_store
from src.credentials import active_user_id, get_for_user
from src.db.models import ActivityLog, GenerationJob, User
from api.app.security import hash_password
from api.app import ratelimit as rl
from api.app.settings import settings


def _create_user(username: str, email: str, role: str = "client") -> int:
    with db.session() as s:
        user = User(
            username=username,
            email=email,
            name=username.capitalize(),
            password_hash=hash_password("password123"),
            role=role,
            is_active=True,
            subscription_tier="pro",
            subscription_status="active",
        )
        s.add(user)
        s.flush()
        return user.id


def _login(client, username: str) -> None:
    r = client.post("/api/auth/login", json={"username": username, "password": "password123"})
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf"]


def test_idor_generation_idempotency_key_prevented(client):
    """MNT-1201: Idempotency keys must be scoped to user_id so tenants cannot snoop or replay each other's jobs."""
    u1_id = _create_user("owner_user", "owner@example.com", role="owner")
    u2_id = _create_user("client_attacker", "attacker@example.com", role="client")

    slot_dt = datetime.now(timezone.utc).replace(hour=12, minute=30, second=0, microsecond=0)
    key = "secret-idemp-12345"

    j1 = generation.create(
        trigger="dashboard",
        user_id=u1_id,
        slot_at=slot_dt,
        status="running",
        idempotency_key=key,
        topic="Confidential Q4 Strategy Topic",
        category="Finance",
    )

    try:
        with patch("src.github_actions.configured", return_value=True):
            # User 2 makes a request with User 1's idempotency key
            _login(client, "client_attacker")
            r = client.post("/api/generate", json={
                "slot": "auto",
                "topic": "Dummy Topic That Wont Be Used",
                "category": "Finance",
                "idempotency_key": key,
            })
            # Must NOT return 200 replaying User 1's job!
            assert r.status_code != 200
            assert "Confidential Q4 Strategy Topic" not in r.text

            # User 1 replays their own job successfully
            _login(client, "owner_user")
            r_owner = client.post("/api/generate", json={
                "slot": "auto",
                "topic": "Another Dummy Topic",
                "category": "Finance",
                "idempotency_key": key,
            })
            assert r_owner.status_code == 200
            data = r_owner.json()
            assert data["id"] == j1["id"]
            assert data["topic"] == "Confidential Q4 Strategy Topic"
    finally:
        with db.session() as s:
            s.execute(delete(GenerationJob).where(GenerationJob.id == j1["id"]))


def test_activity_record_attributes_to_user():
    """MNT-1206: activity.record should attribute events to explicit user_id or active_user_id."""
    u2_id = _create_user("user_two_log", "u2log@example.com", role="client")
    activity.record("test.event.explicit", "Action done with explicit user_id", actor="user_two_log", user_id=u2_id)

    tok = active_user_id.set(u2_id)
    try:
        activity.record("test.event.context", "Action done with context user_id", actor="user_two_log")
    finally:
        active_user_id.reset(tok)

    with db.session() as s:
        log_explicit = s.scalars(select(ActivityLog).where(ActivityLog.event == "test.event.explicit")).first()
        assert log_explicit is not None
        assert log_explicit.user_id == u2_id

        log_context = s.scalars(select(ActivityLog).where(ActivityLog.event == "test.event.context")).first()
        assert log_context is not None
        assert log_context.user_id == u2_id


def test_arbitrary_tg_chat_id_binding_disallowed(client):
    """MNT-1204: Direct binding of TG_CHAT_ID via PUT is rejected; requires 1-click connect."""
    u2_id = _create_user("user_two_tg", "u2tg@example.com", role="client")
    _login(client, "user_two_tg")

    victim_chat = "-100987654321"
    r = client.put("/api/integrations/TG_CHAT_ID", json={"value": victim_chat})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "telegram.direct_bind_disallowed"

    from src import user_config_store
    stored = user_config_store.lookup("TG_CHAT_ID", u2_id)
    assert stored != victim_chat


def test_email_change_bumps_token_version_and_updates_session(client):
    """MNT-1207: Email change must bump token_version and reissue session to invalidate stale tokens."""
    u_id = _create_user("user_email_test", "original@example.com", role="client")
    _login(client, "user_email_test")

    with db.session() as s:
        user_before = s.get(User, u_id)
        tv_before = user_before.token_version

    with patch("api.app.otp.verify", return_value=True):
        r = client.post("/api/profile/email", json={"email": "new_email@example.com", "code": "123456"})
        assert r.status_code == 200

    with db.session() as s:
        user_after = s.get(User, u_id)
        assert user_after.email == "new_email@example.com"
        assert user_after.token_version == tv_before + 1


def test_confused_deputy_credential_fallback_prevented():
    """MNT-1202: Non-admin client users must never fall back to global env for PER_USER_FIELD_NAMES."""
    client_uid = _create_user("client_test_creds", "client_creds@example.com", role="client")
    tok = active_user_id.set(client_uid)
    try:
        with patch.dict(os.environ, {"IG_ACCESS_TOKEN": "GLOBAL_ADMIN_IG_SECRET"}):
            resolved = get_for_user("IG_ACCESS_TOKEN")
            assert resolved is None
    finally:
        active_user_id.reset(tok)

    # Owner user should still resolve global fallback
    owner_uid = _create_user("owner_test_creds", "owner_creds@example.com", role="owner")
    tok2 = active_user_id.set(owner_uid)
    try:
        with patch.dict(os.environ, {"IG_ACCESS_TOKEN": "GLOBAL_ADMIN_IG_SECRET"}):
            resolved_owner = get_for_user("IG_ACCESS_TOKEN")
            assert resolved_owner == "GLOBAL_ADMIN_IG_SECRET"
    finally:
        active_user_id.reset(tok2)


def test_telegram_rename_shared_bot_forbidden_for_clients(client):
    """MNT-1203: Renaming the shared platform bot requires admin/owner role."""
    u_client = _create_user("client_tg_name", "client_tg@example.com", role="client")
    _login(client, "client_tg_name")

    with patch.dict(os.environ, {"TG_BOT_TOKEN": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"}):
        r = client.put("/api/integrations/telegram/name", json={"name": "AttackerBot"})
        assert r.status_code == 403


def test_signup_rate_limiting(client):
    """MNT-1205: Signups are rate limited to 5 per hour per IP."""
    rl.login_limiter.clear()
    for i in range(5):
        r = client.post("/api/auth/signup", json={
            "username": f"limituser{i}",
            "email": f"limit{i}@example.com",
            "password": "Password123!",
        })
        assert r.status_code in (200, 201), r.text

    # 6th attempt should be blocked
    r = client.post("/api/auth/signup", json={
        "username": "limituser6",
        "email": "limit6@example.com",
        "password": "Password123!",
    })
    assert r.status_code == 429


def test_queue_store_owner_fallback():
    """MNT-1208: _owner_cache fallback is strictly {1}."""
    queue_store._owner_cache = (-1.0, {1})
    with patch("src.db.enabled", return_value=False):
        assert queue_store.get_owner_user_ids() == {1}

    # When DB returns empty set of owners, fallback is {1}
    with db.session() as s:
        with patch.object(s, "scalars") as mock_scalars:
            mock_scalars.return_value.all.return_value = []
            queue_store._owner_cache = (-1.0, {1})
            with patch("src.db.session") as mock_session:
                mock_session.return_value.__enter__.return_value = s
                assert queue_store.get_owner_user_ids() == {1}


def test_session_secret_hmac_derivation():
    """MNT-1209: Fallback session_secret uses HMAC SHA256 derivation with 'starlette-session-key'."""
    jwt_sec = "a" * 32
    expected = hmac.new(jwt_sec.encode(), b"starlette-session-key", hashlib.sha256).hexdigest()

    with patch.dict(os.environ, {"JWT_SECRET": jwt_sec}, clear=False):
        os.environ.pop("SESSION_SECRET", None)
        settings.cache_clear()
        s = settings()
        assert s.session_secret == expected
        assert s.session_secret != jwt_sec[::-1]
