"""Secrets never reach logs, exception text or Telegram (R-05 / spec S3). Sentinel values only."""
from __future__ import annotations

import logging

import pytest
import requests

from src import redact as R

IG = "IGQWRSENTINELinstagramtoken0123456789abcdefABCDEFghijklmnop"
TG = "123456789:SENTINELtelegramtokenABCDEFGHIJ_klmn"


@pytest.mark.parametrize("text,secret", [
    (f"GET https://graph.instagram.com/v21.0/me?fields=user_id&access_token={IG}", IG),
    (f"POST https://api.telegram.org/bot{TG}/getMe failed", TG.split(":")[1]),
    ("POST https://api.telegram.org/bot123456789%3ASENTINELtelegramtokenABCDEFGHIJ_klmn/getMe", "SENTINELtelegramtoken"),
    ("CLOUDINARY_URL=cloudinary://987654321:SENTINELcloudsecret@demo", "SENTINELcloudsecret"),
    ("postgresql://user:SENTINELdbpassword@ep-x.neon.tech/db", "SENTINELdbpassword"),
    ("https://generativelanguage.googleapis.com/v1beta/models?key=SENTINELgoogle123", "SENTINELgoogle123"),
    ("headers={'Authorization': 'Bearer github_pat_SENTINEL0123456789abcdefgh'}", "github_pat_SENTINEL"),
    ("{'x-goog-api-key': 'SENTINELheaderkey99'}", "SENTINELheaderkey99"),
    ("client_secret=GOCSPX-SENTINELclientsecret", "SENTINELclientsecret"),
    ("refresh 1//0gSENTINELrefreshtoken123456789", "SENTINELrefreshtoken"),
])
def test_patterns(text, secret):
    out = R.redact(text)
    assert secret not in out
    assert R.MASK in out


def test_prose_is_left_alone():
    for s in ("Password: hashing 101 explained", "Authorization required", "token refreshed; valid for 59 days",
              "The model key insight is caching"):
        assert R.redact(s) == s


def test_known_values_including_url_encoded(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "plainSENTINELvalue/with+chars")
    assert "SENTINEL" not in R.redact("boom plainSENTINELvalue/with+chars")
    assert "SENTINEL" not in R.redact("boom plainSENTINELvalue%2Fwith%2Bchars")
    R.register("runtimeSENTINEL42")
    assert "runtimeSENTINEL42" not in R.redact("x runtimeSENTINEL42 y")


def test_logging_filter_scrubs_message_args_and_traceback(caplog):
    logger = logging.getLogger("codexone.test_redact")
    handler = logging.Handler()
    seen: list[str] = []
    handler.emit = lambda rec: seen.append(logging.Formatter().format(rec))
    handler.addFilter(R.RedactingFilter())
    logger.addHandler(handler)
    try:
        logger.warning("failed: %s", f"https://x/?access_token={IG}")
        try:
            raise requests.ConnectionError(f"Max retries exceeded with url: /me?access_token={IG}")
        except requests.ConnectionError:
            logger.exception("publish crashed")
    finally:
        logger.removeHandler(handler)
    assert seen and all(IG not in line for line in seen)
    assert "Traceback" in seen[1]


def test_get_logger_handlers_have_the_filter():
    from src.logger import get_logger
    get_logger("x")
    handlers = logging.getLogger("codexone").handlers
    assert handlers and all(any(isinstance(f, R.RedactingFilter) for f in h.filters) for h in handlers)


def test_instagram_network_error_never_carries_the_token(monkeypatch):
    from src import publish
    monkeypatch.setenv("IG_ACCESS_TOKEN", IG)

    def boom(method, url, params=None, **kw):
        raise requests.ConnectionError(f"HTTPSConnectionPool: Max retries exceeded with url: {url}?access_token={params['access_token']}")
    monkeypatch.setattr(publish.requests, "request", boom)
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    with pytest.raises(publish.IGError) as e:
        publish._call("GET", "me", retries=1, fields="user_id")
    assert IG not in str(e.value) and "network error" in str(e.value)


def test_refresh_network_error_never_carries_the_token(monkeypatch):
    from src import refresh_token
    monkeypatch.setenv("IG_ACCESS_TOKEN", IG)

    def boom(url, params=None, **kw):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}?access_token={params['access_token']}")
    monkeypatch.setattr(refresh_token.requests, "get", boom)
    with pytest.raises(RuntimeError) as e:
        refresh_token.refresh()
    assert IG not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__


def test_notify_scrubs_before_sending(monkeypatch):
    from src import approve_bot
    sent = []
    monkeypatch.setattr(approve_bot, "sync_enabled", lambda: True)

    async def fake_notify(text, reply_to=None):
        sent.append(text)
    monkeypatch.setattr(approve_bot, "_notify", fake_notify)
    approve_bot.notify(f"publish failed: ConnectionError: url /me?access_token={IG}")
    assert sent and IG not in sent[0]
