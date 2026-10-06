"""Verifier tests with mocked HTTP built from the providers' documented response shapes.

No test reaches a real provider: src.verify.base.requests is replaced by a recording fake, and the guard
fixture fails any request that wasn't explicitly faked. Values below are made-up sentinels, never real keys.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest
import requests

from fake_http import FakeHTTP, FakeResponse
from src.verify import base, cloudinary, gemini, github, telegram

GEMINI_KEY = "SENTINEL-gemini-key-0123456789abcdef"
TG_TOKEN = "123456789:SENTINELtelegramtokenABCDEFGHIJ_klmn"
CLD = "cloudinary://987654321:SENTINELcloudsecretXYZ@demo-cloud"
GH_TOKEN = "github_pat_SENTINELgithubtoken0123456789"


@pytest.fixture()
def http(monkeypatch):
    fake = FakeHTTP()
    monkeypatch.setattr(base, "requests", fake)
    return fake


def no_secret_in_result(result, *secrets):
    """Neither the secret nor any credential part of it (token halves, URL user/password) is in the result."""
    text = repr(result.to_dict())
    for s in secrets:
        assert s not in text
        body = s.split("://", 1)[-1].rsplit("@", 1)[0] if "://" in s else s  # drop scheme and cloud name
        for part in re.split(r"[:@/]", body):
            if len(part) >= 6:
                assert part not in text, part


# --------------------------------------------------------------------------- #
# Paste cleaner
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw,name,want,note", [
    ('  "abc123"\n', "X", "abc123", "removed the quotes"),
    ("GEMINI_API_KEY=abc123", "GEMINI_API_KEY", "abc123", "removed the leading GEMINI_API_KEY="),
    ("export TG_BOT_TOKEN='1:a'", "TG_BOT_TOKEN", "1:a", "removed the quotes"),
    ("ab​c﻿", "X", "abc", "removed invisible characters"),
    ("COUDNARY_API_ENV_VAR=cloudinary://a:b@c", "CLOUDINARY_URL", "cloudinary://a:b@c", "removed the leading COUDNARY_API_ENV_VAR="),
])
def test_clean_value(raw, name, want, note):
    v, notes = base.clean_value(raw, name)
    assert v == want
    assert note in notes
    assert want not in " ".join(notes) or len(want) < 4  # notes never echo the value


# --------------------------------------------------------------------------- #
# Gemini (ai.google.dev/api/models, /api/tokens; google.rpc error shape)
# --------------------------------------------------------------------------- #
def gemini_ok(http, model="gemini-flash-latest"):
    http.add("GET", r"/v1beta/models$", FakeResponse(200, {"models": [{"name": f"models/{model}"}, {"name": "models/x"}]}))
    http.add("POST", rf"/v1beta/models/{re.escape(model)}:countTokens$", FakeResponse(200, {"totalTokens": 1}))


def test_gemini_valid_key_in_header_only(http):
    gemini_ok(http)
    r = gemini.verify({"GEMINI_API_KEY": GEMINI_KEY})
    assert r.status == "valid", r
    assert [c.name for c in r.checks if c.ok] == ["key_format", "model_format", "key_accepted", "model_available"]
    assert all(c["headers"]["x-goog-api-key"] == GEMINI_KEY for c in http.calls)
    assert GEMINI_KEY not in http.everything_sent()          # never in a URL or body
    assert not any("generateContent" in u for u in http.urls())  # no quota spent without consent
    no_secret_in_result(r, GEMINI_KEY)


def test_gemini_format_failures_make_no_request(http):
    r = gemini.verify({"GEMINI_API_KEY": "abc def"})
    assert r.status == "invalid" and r.code == "gemini.format"
    r = gemini.verify({"GEMINI_API_KEY": GEMINI_KEY, "GEMINI_MODEL": "../../evil"})
    assert r.code == "gemini.model_format"
    assert http.calls == []
    assert gemini.verify({}).status == "not_set"


@pytest.mark.parametrize("status,payload,code,want_status", [
    (400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT",
                     "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}]}},
     "gemini.key_rejected", "invalid"),
    (403, {"error": {"code": 403, "message": "Your API key was reported as leaked. Please use another API key.",
                     "status": "PERMISSION_DENIED"}}, "gemini.key_blocked", "invalid"),
    (403, {"error": {"code": 403, "message": "Method doesn't allow unregistered callers", "status": "PERMISSION_DENIED"}},
     "gemini.forbidden", "invalid"),
    (429, {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED",
                     "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}},
     "gemini.quota", "warning"),
    (429, {"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}}, "gemini.rate_limited", "unknown"),
    (503, {"error": {"code": 503, "message": "The model is overloaded", "status": "UNAVAILABLE"}}, "gemini.unavailable", "unknown"),
    (500, None, "gemini.unavailable", "unknown"),
])
def test_gemini_error_classes(http, status, payload, code, want_status):
    http.add("GET", r"/v1beta/models$", FakeResponse(status, payload, text="<html>oops</html>" if payload is None else None))
    r = gemini.verify({"GEMINI_API_KEY": GEMINI_KEY})
    assert (r.code, r.status) == (code, want_status)
    assert r.message and r.hint and r.docs.startswith("/config/guide/errors#")
    no_secret_in_result(r, GEMINI_KEY)


def test_gemini_unknown_model(http):
    http.add("GET", r"/v1beta/models$", FakeResponse(200, {"models": []}))
    http.add("POST", r":countTokens$", FakeResponse(404, {"error": {"code": 404, "message": "models/nope is not found",
                                                                     "status": "NOT_FOUND"}}))
    r = gemini.verify({"GEMINI_API_KEY": GEMINI_KEY, "GEMINI_MODEL": "models/nope"})
    assert (r.status, r.code) == ("invalid", "gemini.model_not_found")
    assert http.calls[1]["url"].endswith("/models/nope:countTokens")  # "models/" prefix tolerated


def test_gemini_unreachable_is_unknown_not_invalid(http):
    http.add("GET", r"/v1beta/models$", requests.ConnectionError(f"failed https://x/?key={GEMINI_KEY}"))
    r = gemini.verify({"GEMINI_API_KEY": GEMINI_KEY})
    assert (r.status, r.code, r.error_class) == ("unknown", "gemini.unreachable", "unreachable")
    no_secret_in_result(r, GEMINI_KEY)


def test_gemini_deep_runs_one_generation(http):
    gemini_ok(http)
    http.add("POST", r":generateContent$", FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}))
    r = gemini.verify({"GEMINI_API_KEY": GEMINI_KEY}, depth="deep")
    assert r.status == "valid"
    assert sum("generateContent" in u for u in http.urls()) == 1
    gen = next(c for c in http.calls if "generateContent" in c["url"])
    assert gen["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_deep_empty_answer_is_a_warning(http):
    gemini_ok(http)
    http.add("POST", r":generateContent$", FakeResponse(200, {"candidates": [{"finishReason": "MAX_TOKENS"}]}))
    r = gemini.verify({"GEMINI_API_KEY": GEMINI_KEY}, depth="deep")
    assert (r.status, r.code) == ("warning", "gemini.generation_empty")


# --------------------------------------------------------------------------- #
# Telegram (core.telegram.org/bots/api)
# --------------------------------------------------------------------------- #
def tg_ok(http, webhook=""):
    http.add("POST", r"/getMe$", FakeResponse(200, {"ok": True, "result": {"id": 123456789, "is_bot": True, "first_name": "B",
                                                                           "username": "demo_bot"}}))
    http.add("POST", r"/getWebhookInfo$", FakeResponse(200, {"ok": True, "result": {"url": webhook, "has_custom_certificate": False,
                                                                                    "pending_update_count": 0}}))
    http.add("POST", r"/getChat$", FakeResponse(200, {"ok": True, "result": {"id": -1001, "type": "supergroup", "title": "Approvals"}}))


def test_telegram_valid(http):
    tg_ok(http)
    r = telegram.verify({"TG_BOT_TOKEN": TG_TOKEN, "TG_CHAT_ID": "-1001"})
    assert r.status == "valid"
    assert r.evidence["bot"] == "@demo_bot"
    assert not any(u.endswith(("/sendMessage", "/getUpdates", "/setWebhook", "/deleteWebhook")) for u in http.urls())
    no_secret_in_result(r, TG_TOKEN)


def test_telegram_webhook_trap(http):
    tg_ok(http, webhook="https://hooks.example.com/secret-path-SENTINELhook")
    r = telegram.verify({"TG_BOT_TOKEN": TG_TOKEN, "TG_CHAT_ID": "-1001"})
    assert (r.status, r.code) == ("invalid", "telegram.webhook_set")
    assert r.evidence["webhook_host"] == "hooks.example.com"
    assert "SENTINELhook" not in repr(r.to_dict())  # the webhook path may itself be a secret


@pytest.mark.parametrize("method,status,payload,code", [
    ("getMe", 401, {"ok": False, "error_code": 401, "description": "Unauthorized"}, "telegram.token_rejected"),
    ("getChat", 400, {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}, "telegram.chat_not_found"),
    ("getChat", 403, {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}, "telegram.blocked"),
    ("getMe", 429, {"ok": False, "error_code": 429, "description": "Too Many Requests: retry after 5",
                    "parameters": {"retry_after": 5}}, "telegram.rate_limited"),
])
def test_telegram_errors(http, method, status, payload, code):
    http.add("POST", rf"/{method}$", FakeResponse(status, payload))
    tg_ok(http)
    r = telegram.verify({"TG_BOT_TOKEN": TG_TOKEN, "TG_CHAT_ID": "-1001"})
    assert r.code == code


def test_telegram_format_blocks_path_injection(http):
    r = telegram.verify({"TG_BOT_TOKEN": "123:abc/../../getUpdates?offset=9", "TG_CHAT_ID": "1"})
    assert (r.status, r.code) == ("invalid", "telegram.token_format")
    r = telegram.verify({"TG_BOT_TOKEN": TG_TOKEN, "TG_CHAT_ID": "@channel"})
    assert r.code == "telegram.chat_format"
    assert http.calls == []
    assert telegram.verify({"TG_BOT_TOKEN": TG_TOKEN}).code == "verify.not_set"


def test_telegram_deep_sends_plain_message_without_buttons(http):
    tg_ok(http)
    http.add("POST", r"/sendMessage$", FakeResponse(200, {"ok": True, "result": {"message_id": 5}}))
    r = telegram.verify({"TG_BOT_TOKEN": TG_TOKEN, "TG_CHAT_ID": "-1001"}, depth="deep")
    assert r.status == "valid"
    sent = [c for c in http.calls if c["url"].endswith("/sendMessage")]
    assert len(sent) == 1 and "reply_markup" not in sent[0]["json"]


def test_detect_chat_never_confirms_updates(http):
    http.add("POST", r"/getWebhookInfo$", FakeResponse(200, {"ok": True, "result": {"url": ""}}))
    http.add("POST", r"/getUpdates$", FakeResponse(200, {"ok": True, "result": [
        {"update_id": 10, "callback_query": {"id": "q", "data": "approve:x"}},          # a pending button press
        {"update_id": 11, "message": {"message_id": 1, "chat": {"id": 42, "type": "private", "first_name": "Ana"},
                                      "text": "/start"}},
        {"update_id": 12, "message": {"message_id": 2, "chat": {"id": -100, "type": "group", "title": "Team"}, "text": "/start"}},
        {"update_id": 13, "message": {"message_id": 3, "chat": {"id": 42, "type": "private", "first_name": "Ana"}, "text": "hi"}},
    ]}))
    chats, code = telegram.detect_chats(TG_TOKEN)
    assert code is None
    assert [c["id"] for c in chats] == ["42", "-100"]  # newest first, de-duplicated
    upd = next(c for c in http.calls if c["url"].endswith("/getUpdates"))["json"]
    assert "offset" not in upd and "allowed_updates" not in upd and upd["timeout"] == 0


def test_detect_chat_refuses_when_webhook_set_and_reports_nothing_found(http):
    http.add("POST", r"/getWebhookInfo$", FakeResponse(200, {"ok": True, "result": {"url": "https://x.example/h"}}))
    assert telegram.detect_chats(TG_TOKEN) == ([], "telegram.webhook_set")
    assert not any(u.endswith("/getUpdates") for u in http.urls())
    http.routes.clear()
    http.add("POST", r"/getWebhookInfo$", FakeResponse(200, {"ok": True, "result": {"url": ""}}))
    http.add("POST", r"/getUpdates$", FakeResponse(200, {"ok": True, "result": []}))
    assert telegram.detect_chats(TG_TOKEN) == ([], "telegram.no_chat_found")


def test_detect_chat_conflict(http):
    http.add("POST", r"/getWebhookInfo$", FakeResponse(200, {"ok": True, "result": {"url": ""}}))
    http.add("POST", r"/getUpdates$", FakeResponse(409, {"ok": False, "error_code": 409,
                                                       "description": "Conflict: terminated by other getUpdates request"}))
    assert telegram.detect_chats(TG_TOKEN) == ([], "telegram.poll_conflict")


# --------------------------------------------------------------------------- #
# Cloudinary (cloudinary.com/documentation/admin_api, image_upload_api_reference)
# --------------------------------------------------------------------------- #
def cld_ok(http, secure_url="https://res.cloudinary.com/demo-cloud/image/upload/v1/codexone/_selftest/abc.jpg",
           head=None, destroy=None):
    http.add("GET", r"/v1_1/demo-cloud/ping$", FakeResponse(200, {"status": "ok"}))
    http.add("POST", r"/v1_1/demo-cloud/image/upload$",
             lambda call: FakeResponse(200, {"public_id": call["data"]["public_id"], "secure_url": secure_url}))
    http.add("HEAD", r"^https://res\.cloudinary\.com/", head or FakeResponse(200, None, {"Content-Type": "image/jpeg"}))
    http.add("POST", r"/v1_1/demo-cloud/image/destroy$", destroy or FakeResponse(200, {"result": "ok"}))


def test_cloudinary_full_cycle_and_cleanup(http):
    cld_ok(http)
    r = cloudinary.verify({"CLOUDINARY_URL": CLD})
    assert r.status == "valid", r
    assert [c.name for c in r.checks] == ["format", "credentials", "upload", "public_link", "cleanup"]
    up = next(c for c in http.calls if c["url"].endswith("/upload"))
    assert up["data"]["public_id"].startswith("codexone/_selftest/")
    destroyed = next(c for c in http.calls if c["url"].endswith("/destroy"))
    assert destroyed["data"]["public_id"] == up["data"]["public_id"]
    assert all(c.get("auth") == ("987654321", "SENTINELcloudsecretXYZ") for c in http.calls if "api.cloudinary.com" in c["url"])
    assert "SENTINELcloudsecretXYZ" not in http.everything_sent()  # credentials only in the Authorization header
    no_secret_in_result(r, CLD)


def test_cloudinary_cleanup_runs_even_when_delivery_fails(http):
    cld_ok(http, head=FakeResponse(404, None, {"Content-Type": "text/html"}))
    r = cloudinary.verify({"CLOUDINARY_URL": CLD})
    assert (r.status, r.code) == ("invalid", "cloudinary.delivery_failed")
    assert any(u.endswith("/destroy") for u in http.urls())


def test_cloudinary_cleanup_failure_is_a_warning(http):
    cld_ok(http, destroy=FakeResponse(500, {"error": {"message": "x"}}))
    r = cloudinary.verify({"CLOUDINARY_URL": CLD})
    assert (r.status, r.code) == ("warning", "cloudinary.cleanup_failed")


def test_cloudinary_never_fetches_foreign_hosts(http):
    cld_ok(http, secure_url="https://169.254.169.254/latest/meta-data")
    r = cloudinary.verify({"CLOUDINARY_URL": CLD})
    assert not any("169.254" in u for u in http.urls())
    assert next(c for c in r.checks if c.name == "public_link").ok is None


@pytest.mark.parametrize("status,payload,code", [
    (401, {"error": {"message": "Invalid api_key 987654321"}}, "cloudinary.rejected"),
    (200, None, "cloudinary.rejected"),          # HTML instead of JSON: "typically ... an authentication issue"
    (420, {"error": {"message": "Rate Limit Exceeded"}}, "cloudinary.rate_limited"),
    (404, {"error": {"message": "cloud not found"}}, "cloudinary.not_found"),
])
def test_cloudinary_errors(http, status, payload, code):
    http.add("GET", r"/ping$", FakeResponse(status, payload, text="<html>login</html>" if payload is None else None))
    r = cloudinary.verify({"CLOUDINARY_URL": CLD})
    assert r.code == code
    assert not any(u.endswith("/upload") for u in http.urls())


def test_cloudinary_template_placeholders(http):
    r = cloudinary.verify({"CLOUDINARY_URL": "cloudinary://<your_api_key>:<your_api_secret>@demo"})
    assert (r.status, r.code) == ("invalid", "cloudinary.placeholder")
    assert http.calls == []


@pytest.mark.parametrize("bad", ["https://demo", "cloudinary://key@cloud", "cloudinary://k:s@bad host", "cloudinary://k:s@../x"])
def test_cloudinary_format(http, bad):
    assert cloudinary.verify({"CLOUDINARY_URL": bad}).code == "cloudinary.format"
    assert http.calls == []


# --------------------------------------------------------------------------- #
# GitHub (docs.github.com/en/rest/actions/workflows, rest-api-description state enum)
# --------------------------------------------------------------------------- #
def gh_ok(http, state="active", expiry=None, repo_extra=None):
    hdr = {"GitHub-Authentication-Token-Expiration": expiry} if expiry else {}
    http.add("GET", r"/repos/acme/automation$", FakeResponse(200, {"full_name": "acme/automation", "private": True,
                                                                   "default_branch": "main", "archived": False,
                                                                   **(repo_extra or {})}, hdr))
    http.add("GET", r"/actions/workflows/[\w.-]+\.yml$", FakeResponse(200, {"id": 1, "path": ".github/workflows/x.yml",
                                                                           "state": state}))


GH = {"GITHUB_REPOSITORY": "acme/automation", "GITHUB_DISPATCH_TOKEN": GH_TOKEN}


def test_github_valid_never_dispatches(http):
    gh_ok(http, expiry=(datetime.now(timezone.utc) + timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S UTC"))
    r = github.verify(GH)
    assert r.status == "valid", r
    assert all(c["method"] == "GET" for c in http.calls)
    assert not any("dispatches" in u for u in http.urls())
    write = next(c for c in r.checks if c.name == "actions_write")
    assert write.ok is None and write.code == "github.write_unconfirmed"
    assert r.expires_at
    assert all(c["headers"]["Authorization"] == f"Bearer {GH_TOKEN}" for c in http.calls)
    assert GH_TOKEN not in http.everything_sent()
    no_secret_in_result(r, GH_TOKEN)


def test_github_expiring_token_warns(http):
    gh_ok(http, expiry=(datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S UTC"))
    r = github.verify(GH)
    assert (r.status, r.code) == ("warning", "github.token_expiring")


@pytest.mark.parametrize("state", ["disabled_inactivity", "disabled_fork", "disabled_manually", "deleted"])
def test_github_disabled_workflow(http, state):
    gh_ok(http, state=state)
    r = github.verify(GH)
    assert (r.status, r.code) == ("invalid", "github.workflow_disabled")
    assert state in " ".join(c.evidence for c in r.checks)


@pytest.mark.parametrize("status,headers,code", [
    (401, {}, "github.token_rejected"),
    (404, {}, "github.not_found"),
    (403, {}, "github.forbidden"),
    (403, {"x-ratelimit-remaining": "0"}, "github.rate_limited"),
])
def test_github_errors(http, status, headers, code):
    http.add("GET", r"/repos/acme/automation$", FakeResponse(status, {"message": "x"}, headers))
    r = github.verify(GH)
    assert r.code == code


def test_github_missing_workflow_and_archived(http):
    http.add("GET", r"/actions/workflows/poll-approvals\.yml$", FakeResponse(404, {"message": "Not Found"}))
    gh_ok(http, repo_extra={"archived": True})
    r = github.verify(GH)
    assert {c.code for c in r.checks if c.ok is False} == {"github.workflow_missing"}
    assert {c.code for c in r.checks if c.soft} == {"github.archived"}


def test_github_format(http):
    assert github.verify({**GH, "GITHUB_REPOSITORY": "acme/../etc"}).code == "github.repo_format"
    assert github.verify({**GH, "GITHUB_REPOSITORY": "https://github.com/acme/automation"}).code == "github.repo_format"
    assert github.verify({"GITHUB_REPOSITORY": "acme/automation"}).code == "verify.not_set"
    assert http.calls == []


# --------------------------------------------------------------------------- #
# Result invariants
# --------------------------------------------------------------------------- #
def test_every_code_used_by_a_verifier_is_catalogued():
    from pathlib import Path
    src = Path(base.__file__).parent
    used = set()
    for f in src.glob("*.py"):
        used |= set(re.findall(r"\"((?:gemini|telegram|cloudinary|github|database|verify)\.[a-z_]+)\"", f.read_text(encoding="utf-8")))
    missing = used - set(base.CODES)
    assert not missing, missing
    for code, info in base.CODES.items():
        assert info.error_class in base.ERROR_CLASSES, code
        assert info.message and info.hint, code


def test_provider_outage_never_reads_as_invalid():
    run = base.Run("x", "live")
    run.fail("a", "A", "gemini.unreachable")
    run.fail("b", "B", "gemini.rate_limited")
    assert run.finish().status == "unknown"
    run = base.Run("x", "live")
    run.fail("a", "A", "gemini.unreachable")
    run.fail("b", "B", "gemini.key_rejected")
    res = run.finish()
    assert (res.status, res.code) == ("invalid", "gemini.key_rejected")  # leads with the real problem
