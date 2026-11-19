"""Unit tests for YouTube 1-Click OAuth flow and channel integration."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from api.app.routes.integrations import _sign_oauth_state, _verify_oauth_state
from src import publish_youtube, user_config_store


def test_youtube_oauth_link_generation(authed):
    """POST /api/integrations/youtube/link generates a valid Google OAuth URL with PKCE/state."""
    resp = authed.post("/api/integrations/youtube/link")
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "accounts.google.com/o/oauth2/v2/auth" in data["url"]
    assert "scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fyoutube.upload" in data["url"]
    assert "response_type=code" in data["url"]
    assert "access_type=offline" in data["url"]
    assert "prompt=consent" in data["url"]
    assert "state=" in data["url"]
    assert data["expires_in"] == 900


def test_youtube_oauth_state_signature_and_replay():
    """State tokens are cryptographically signed, single-use, and expire."""
    user_id = 42
    state = _sign_oauth_state(user_id, "youtube")
    assert state
    assert len(state.split(":")) == 5

    # First verification passes
    verified_id = _verify_oauth_state(state, "youtube")
    assert verified_id == user_id

    # Replay verification fails
    assert _verify_oauth_state(state, "youtube") is None

    # Tampered signature fails
    tampered = state[:-4] + "ffff"
    assert _verify_oauth_state(tampered, "youtube") is None

    # Wrong provider fails
    another_state = _sign_oauth_state(user_id, "youtube")
    assert _verify_oauth_state(another_state, "instagram") is None


def test_youtube_oauth_callback_success(client, authed, monkeypatch):
    """GET /api/integrations/youtube/callback exchanges code, fetches channel, and stores refresh token."""
    from src import config_store, db
    from src.db.models import ConfigKey, ConfigMeta
    from sqlalchemy import delete

    key = config_store.generate_master_key()
    monkeypatch.setenv("CONFIG_MASTER_KEY", key)
    config_store._dek_cache.clear()
    config_store.invalidate()

    try:
        # 1. Get initial integrations status (YouTube not connected)
        init_res = authed.get("/api/integrations").json()
        assert init_res["youtube"]["connected"] is False
        assert init_res["youtube"]["oauth_configured"] is True

        # 2. Generate a valid state for user 1 (the seeded admin in authed)
        link_data = authed.post("/api/integrations/youtube/link").json()
        # Extract state param from link url
        import urllib.parse
        parsed_url = urllib.parse.urlparse(link_data["url"])
        qs = urllib.parse.parse_qs(parsed_url.query)
        state = qs["state"][0]

        # 3. Mock requests.post (token exchange) and requests.get (channel snippet)
        def fake_post(url, *args, **kwargs):
            resp = MagicMock()
            if "oauth2.googleapis.com/token" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "access_token": "ya29.fake_access_token",
                    "refresh_token": "1//fake_refresh_token_xyz",
                    "expires_in": 3600,
                }
            elif "oauth2.googleapis.com/revoke" in url:
                resp.status_code = 200
            else:
                resp.status_code = 404
            return resp

        def fake_get(url, *args, **kwargs):
            resp = MagicMock()
            if "googleapis.com/youtube/v3/channels" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "items": [
                        {
                            "id": "UC_TEST_CHANNEL_123",
                            "snippet": {
                                "title": "CodeXone Engineering",
                                "customUrl": "@codexone",
                                "thumbnails": {
                                    "default": {"url": "https://yt3.ggpht.com/avatar.jpg"}
                                },
                            },
                        }
                    ]
                }
            else:
                resp.status_code = 404
            return resp

        monkeypatch.setattr("api.app.routes.integrations.requests.post", fake_post)
        monkeypatch.setattr("api.app.routes.integrations.requests.get", fake_get)

        # 4. Trigger callback
        cb_resp = client.get(
            f"/api/integrations/youtube/callback?code=mock_code&state={state}",
            follow_redirects=False,
        )
        assert cb_resp.status_code == 303
        assert "/config?connected=youtube" in cb_resp.headers["Location"]

        # 5. Check integrations status now shows connected with channel info
        status_res = authed.get("/api/integrations").json()
        assert status_res["youtube"]["connected"] is True
        assert status_res["youtube"]["channel_id"] == "UC_TEST_CHANNEL_123"
        assert status_res["youtube"]["channel_title"] == "CodeXone Engineering"
        assert status_res["youtube"]["channel_handle"] == "@codexone"
        assert status_res["youtube"]["channel_thumb"] == "https://yt3.ggpht.com/avatar.jpg"

        # 6. Check publish_youtube.configured() evaluates to True for this user
        from src.credentials import active_user_id
        token = active_user_id.set(1)
        try:
            assert publish_youtube.configured() is True
        finally:
            active_user_id.reset(token)

        # 7. Unlink YouTube
        del_resp = authed.delete("/api/integrations/youtube")
        assert del_resp.status_code == 204

        # 8. Confirm unlinked
        after_res = authed.get("/api/integrations").json()
        assert after_res["youtube"]["connected"] is False
        assert after_res["youtube"]["channel_id"] is None
    finally:
        with db.session() as s:
            s.execute(delete(ConfigKey))
            s.execute(delete(ConfigMeta))
        config_store._dek_cache.clear()
        config_store.invalidate()
