"""Tests for Telegram bot name inspection and rename operations (MNT-801, MNT-802, MNT-803, MNT-804).

Covers:
- `src.verify.telegram.get_bot_info`
- `src.verify.telegram.get_bot_name`
- `src.verify.telegram.set_bot_name`
- Input validation (token format, name length, empty names)
- Network unreachable handling
- API route `GET /api/integrations` (bot_name, bot_username metadata)
- API route `PUT /api/integrations/telegram/name` (validation, success, errors)
"""
from __future__ import annotations

import pytest
import requests
from fastapi import HTTPException

from api.app.deps import CurrentUser
from api.app.routes import integrations
from fake_http import FakeHTTP, FakeResponse
from src.verify import base, telegram

VALID_TOKEN = "123456789:AA_SENTINELtelegramtokenABCDEFGHIJ_klmn"
INVALID_TOKEN = "invalid-token"


@pytest.fixture()
def fake_http(monkeypatch):
    fake = FakeHTTP()
    monkeypatch.setattr(base, "requests", fake)
    return fake


# =========================================================================== #
# 1. get_bot_info
# =========================================================================== #
def test_get_bot_info_success(fake_http):
    fake_http.add("POST", r"/getMe$", FakeResponse(200, {
        "ok": True,
        "result": {
            "id": 123456789,
            "is_bot": True,
            "first_name": "codeXoneByHitesh",
            "username": "codeXoneByHiteshBot",
        },
    }))
    info, err = telegram.get_bot_info(VALID_TOKEN)
    assert err is None
    assert isinstance(info, dict)
    assert info["username"] == "codeXoneByHiteshBot"
    assert info["first_name"] == "codeXoneByHitesh"


def test_get_bot_info_invalid_token_format(fake_http):
    info, err = telegram.get_bot_info(INVALID_TOKEN)
    assert info is None
    assert err == "telegram.token_format"
    assert len(fake_http.calls) == 0


def test_get_bot_info_rejected_token(fake_http):
    fake_http.add("POST", r"/getMe$", FakeResponse(401, {
        "ok": False,
        "error_code": 401,
        "description": "Unauthorized",
    }))
    info, err = telegram.get_bot_info(VALID_TOKEN)
    assert info is None
    assert err == "telegram.token_rejected"


def test_get_bot_info_unreachable(fake_http):
    fake_http.add("POST", r"/getMe$", requests.ConnectionError("Connection refused"))
    info, err = telegram.get_bot_info(VALID_TOKEN)
    assert info is None
    assert err == "telegram.unreachable"


# =========================================================================== #
# 2. get_bot_name
# =========================================================================== #
def test_get_bot_name_via_get_my_name(fake_http):
    fake_http.add("POST", r"/getMyName$", FakeResponse(200, {
        "ok": True,
        "result": {"name": "codeXone Brand Bot"},
    }))
    name, err = telegram.get_bot_name(VALID_TOKEN)
    assert err is None
    assert name == "codeXone Brand Bot"


def test_get_bot_name_fallback_to_get_me(fake_http):
    # getMyName returns empty name or 400
    fake_http.add("POST", r"/getMyName$", FakeResponse(200, {
        "ok": True,
        "result": {"name": ""},
    }))
    fake_http.add("POST", r"/getMe$", FakeResponse(200, {
        "ok": True,
        "result": {
            "id": 123456789,
            "first_name": "DefaultBotName",
            "username": "default_bot",
        },
    }))
    name, err = telegram.get_bot_name(VALID_TOKEN)
    assert err is None
    assert name == "DefaultBotName"


def test_get_bot_name_invalid_token(fake_http):
    name, err = telegram.get_bot_name(INVALID_TOKEN)
    assert name is None
    assert err == "telegram.token_format"
    assert len(fake_http.calls) == 0


def test_get_bot_name_unreachable(fake_http):
    fake_http.add("POST", r"/getMyName$", requests.ConnectionError("Network timeout"))
    name, err = telegram.get_bot_name(VALID_TOKEN)
    assert name is None
    assert err == "telegram.unreachable"


# =========================================================================== #
# 3. set_bot_name
# =========================================================================== #
def test_set_bot_name_success(fake_http):
    fake_http.add("POST", r"/setMyName$", FakeResponse(200, {
        "ok": True,
        "result": True,
    }))
    ok, err = telegram.set_bot_name(VALID_TOKEN, "Mintly Content Bot")
    assert ok is True
    assert err is None
    call = next(c for c in fake_http.calls if "setMyName" in c["url"])
    assert call["json"] == {"name": "Mintly Content Bot"}


def test_set_bot_name_strips_whitespace(fake_http):
    fake_http.add("POST", r"/setMyName$", FakeResponse(200, {
        "ok": True,
        "result": True,
    }))
    ok, err = telegram.set_bot_name(VALID_TOKEN, "   Padded Name   ")
    assert ok is True
    assert err is None
    call = next(c for c in fake_http.calls if "setMyName" in c["url"])
    assert call["json"] == {"name": "Padded Name"}


@pytest.mark.parametrize("bad_name", [
    "",
    "   ",
    "A" * 65,  # > 64 chars
])
def test_set_bot_name_invalid_name(fake_http, bad_name):
    ok, err = telegram.set_bot_name(VALID_TOKEN, bad_name)
    assert ok is False
    assert err == "telegram.invalid_name"
    assert len(fake_http.calls) == 0


def test_set_bot_name_invalid_token(fake_http):
    ok, err = telegram.set_bot_name(INVALID_TOKEN, "Valid Name")
    assert ok is False
    assert err == "telegram.token_format"
    assert len(fake_http.calls) == 0


def test_set_bot_name_telegram_error(fake_http):
    fake_http.add("POST", r"/setMyName$", FakeResponse(400, {
        "ok": False,
        "error_code": 400,
        "description": "Bad Request: name is invalid",
    }))
    ok, err = telegram.set_bot_name(VALID_TOKEN, "Broken Name")
    assert ok is False
    assert err == "telegram.unavailable"


def test_set_bot_name_unreachable(fake_http):
    fake_http.add("POST", r"/setMyName$", requests.ConnectionError("DNS failure"))
    ok, err = telegram.set_bot_name(VALID_TOKEN, "My Bot")
    assert ok is False
    assert err == "telegram.unreachable"


# =========================================================================== #
# 4. API routes: GET /api/integrations & PUT /api/integrations/telegram/name
# =========================================================================== #
@pytest.fixture()
def mock_cu():
    return CurrentUser(id=1, username="admin", email="admin@example.com", name="Admin", csrf="test-csrf", role="admin")


def test_list_integrations_with_bot_info(fake_http, monkeypatch, mock_cu):
    # Mock effective bot token to return a valid token
    monkeypatch.setattr(integrations, "_effective_tg_token", lambda uid: (VALID_TOKEN, False))

    fake_http.add("POST", r"/getMe$", FakeResponse(200, {
        "ok": True,
        "result": {
            "id": 123456789,
            "first_name": "codeXoneByHitesh",
            "username": "codeXoneByHiteshBot",
        },
    }))
    fake_http.add("POST", r"/getMyName$", FakeResponse(200, {
        "ok": True,
        "result": {"name": "codeXone Custom Name"},
    }))

    res = integrations.list_integrations(cu=mock_cu)
    assert "telegram" in res
    assert res["telegram"]["bot_name"] == "codeXone Custom Name"
    assert res["telegram"]["bot_username"] == "@codeXoneByHiteshBot"


def test_list_integrations_without_bot_token(monkeypatch, mock_cu):
    monkeypatch.setattr(integrations, "_effective_tg_token", lambda uid: (None, False))

    res = integrations.list_integrations(cu=mock_cu)
    assert "telegram" in res
    assert res["telegram"]["bot_name"] is None
    assert res["telegram"]["bot_username"] is None


def test_update_telegram_bot_name_success(fake_http, monkeypatch, mock_cu):
    monkeypatch.setattr(integrations, "_effective_tg_token", lambda uid: (VALID_TOKEN, False))
    fake_http.add("POST", r"/setMyName$", FakeResponse(200, {
        "ok": True,
        "result": True,
    }))

    req = integrations.TelegramNameRequest(name="Brand New Bot Name")
    out = integrations.update_telegram_bot_name(body=req, cu=mock_cu)
    assert out["ok"] is True
    assert out["bot_name"] == "Brand New Bot Name"
    assert "Brand New Bot Name" in out["message"]


def test_update_telegram_bot_name_empty(monkeypatch, mock_cu):
    monkeypatch.setattr(integrations, "_effective_tg_token", lambda uid: (VALID_TOKEN, False))
    req = integrations.TelegramNameRequest(name="    ")
    with pytest.raises(HTTPException) as exc:
        integrations.update_telegram_bot_name(body=req, cu=mock_cu)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "telegram.invalid_name"


def test_update_telegram_bot_name_too_long(monkeypatch, mock_cu):
    monkeypatch.setattr(integrations, "_effective_tg_token", lambda uid: (VALID_TOKEN, False))
    # Pydantic validates max_length=64 if validated via model, but testing internal logic as well
    req = integrations.TelegramNameRequest.model_construct(name="X" * 65)
    with pytest.raises(HTTPException) as exc:
        integrations.update_telegram_bot_name(body=req, cu=mock_cu)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "telegram.invalid_name"


def test_update_telegram_bot_name_no_token_configured(monkeypatch, mock_cu):
    monkeypatch.setattr(integrations, "_effective_tg_token", lambda uid: (None, False))
    req = integrations.TelegramNameRequest(name="New Bot Name")
    with pytest.raises(HTTPException) as exc:
        integrations.update_telegram_bot_name(body=req, cu=mock_cu)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "telegram.not_configured"


def test_update_telegram_bot_name_unreachable(fake_http, monkeypatch, mock_cu):
    monkeypatch.setattr(integrations, "_effective_tg_token", lambda uid: (VALID_TOKEN, False))
    fake_http.add("POST", r"/setMyName$", requests.ConnectionError("Telegram unreachable"))

    req = integrations.TelegramNameRequest(name="New Bot Name")
    with pytest.raises(HTTPException) as exc:
        integrations.update_telegram_bot_name(body=req, cu=mock_cu)
    assert exc.value.status_code == 502
    assert exc.value.detail["code"] == "telegram.unreachable"
