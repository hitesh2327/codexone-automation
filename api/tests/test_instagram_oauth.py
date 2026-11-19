"""Unit tests for Instagram 1-Click OAuth flow and account integration."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from api.app.routes.integrations import _sign_oauth_state, _verify_oauth_state
from src import user_config_store


def test_instagram_oauth_link_generation_not_configured(authed, monkeypatch):
    """POST /api/integrations/instagram/link fails gracefully with 422 if no app credentials exist."""
    monkeypatch.delenv("INSTAGRAM_APP_ID", raising=False)
    monkeypatch.delenv("META_APP_ID", raising=False)
    monkeypatch.delenv("IG_APP_ID", raising=False)
    monkeypatch.delenv("INSTAGRAM_APP_SECRET", raising=False)
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    monkeypatch.delenv("IG_APP_SECRET", raising=False)

    resp = authed.post("/api/integrations/instagram/link")
    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"]["code"] == "instagram.not_configured"


def test_instagram_oauth_link_generation_success(authed, monkeypatch):
    """POST /api/integrations/instagram/link generates a valid Meta OAuth URL with signed state."""
    monkeypatch.setenv("INSTAGRAM_APP_ID", "123456789012345")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", "mock_meta_app_secret")

    resp = authed.post("/api/integrations/instagram/link")
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "instagram.com/oauth/authorize" in data["url"]
    assert "client_id=123456789012345" in data["url"]
    assert "response_type=code" in data["url"]
    assert "scope=instagram_business_basic%2Cinstagram_business_content_publish" in data["url"]
    assert "state=" in data["url"]


def test_instagram_oauth_state_signature_and_replay():
    """State tokens are cryptographically signed, single-use, and expire."""
    user_id = 99
    state = _sign_oauth_state(user_id, "instagram")
    assert state
    assert len(state.split(":")) == 5

    # First verification passes
    verified_id = _verify_oauth_state(state, "instagram")
    assert verified_id == user_id

    # Replay verification fails
    assert _verify_oauth_state(state, "instagram") is None

    # Tampered signature fails
    tampered = state[:-4] + "dead"
    assert _verify_oauth_state(tampered, "instagram") is None

    # Provider mismatch fails
    another_state = _sign_oauth_state(user_id, "instagram")
    assert _verify_oauth_state(another_state, "youtube") is None


def test_instagram_oauth_callback_success(client, authed, monkeypatch):
    """GET /api/integrations/instagram/callback exchanges code for 60-day token and stores account."""
    from src import config_store, db
    from src.db.models import ConfigKey, ConfigMeta
    from sqlalchemy import delete

    key = config_store.generate_master_key()
    monkeypatch.setenv("CONFIG_MASTER_KEY", key)
    monkeypatch.setenv("INSTAGRAM_APP_ID", "123456789012345")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", "mock_meta_app_secret")
    config_store._dek_cache.clear()
    config_store.invalidate()

    try:
        # 1. Check initial status
        init_res = authed.get("/api/integrations").json()
        assert init_res["instagram"]["connected"] is False
        assert init_res["instagram"]["oauth_configured"] is True

        # 2. Generate a valid state
        link_data = authed.post("/api/integrations/instagram/link").json()
        import urllib.parse
        parsed_url = urllib.parse.urlparse(link_data["url"])
        qs = urllib.parse.parse_qs(parsed_url.query)
        state = qs["state"][0]

        # 3. Mock requests.post (short-lived code exchange) and requests.get (long-lived token & profile)
        def fake_post(url, *args, **kwargs):
            resp = MagicMock()
            if "api.instagram.com/oauth/access_token" in url:
                resp.status_code = 200
                resp.ok = True
                resp.json.return_value = {
                    "access_token": "IG_SHORT_LIVED_TOKEN_123",
                    "user_id": 17841400123456789,
                }
            else:
                resp.status_code = 404
                resp.ok = False
            return resp

        def fake_get(url, *args, **kwargs):
            resp = MagicMock()
            params = kwargs.get("params") or {}
            if "graph.instagram.com/access_token" in url and params.get("grant_type") == "ig_exchange_token":
                resp.status_code = 200
                resp.ok = True
                resp.json.return_value = {
                    "access_token": "IG_LONG_LIVED_60_DAY_TOKEN_ABC",
                    "token_type": "bearer",
                    "expires_in": 5184000,
                }
            elif "graph.instagram.com/v21.0/me" in url:
                resp.status_code = 200
                resp.ok = True
                resp.json.return_value = {
                    "user_id": "17841400123456789",
                    "username": "codexone_agency",
                    "name": "CodeXone Automation",
                    "profile_picture_url": "https://scontent.cdninstagram.com/pic.jpg",
                }
            else:
                resp.status_code = 404
                resp.ok = False
            return resp

        monkeypatch.setattr("api.app.routes.integrations.requests.post", fake_post)
        monkeypatch.setattr("api.app.routes.integrations.requests.get", fake_get)

        # 4. Trigger callback
        cb_resp = client.get(
            f"/api/integrations/instagram/callback?code=mock_auth_code_xyz&state={state}",
            follow_redirects=False,
        )
        assert cb_resp.status_code == 303
        assert "/config?connected=instagram" in cb_resp.headers["Location"]

        # 5. Check integrations status now shows connected with account info
        status_res = authed.get("/api/integrations").json()
        assert status_res["instagram"]["connected"] is True
        assert status_res["instagram"]["account_id"] == "17841400123456789"
        assert status_res["instagram"]["username"] == "codexone_agency"
        assert status_res["instagram"]["name"] == "CodeXone Automation"
        assert status_res["instagram"]["profile_picture"] == "https://scontent.cdninstagram.com/pic.jpg"

        # 6. Verify token stored in user_config_store
        assert user_config_store.lookup("IG_ACCESS_TOKEN", 1) == "IG_LONG_LIVED_60_DAY_TOKEN_ABC"
        assert user_config_store.lookup("IG_USER_ID", 1) == "17841400123456789"

        # 7. Unlink Instagram
        del_resp = authed.delete("/api/integrations/instagram")
        assert del_resp.status_code == 204

        # 8. Confirm unlinked
        after_res = authed.get("/api/integrations").json()
        assert after_res["instagram"]["connected"] is False
        assert after_res["instagram"]["username"] is None
        assert user_config_store.lookup("IG_ACCESS_TOKEN", 1) is None
    finally:
        with db.session() as s:
            s.execute(delete(ConfigKey))
            s.execute(delete(ConfigMeta))
        config_store._dek_cache.clear()
        config_store.invalidate()
