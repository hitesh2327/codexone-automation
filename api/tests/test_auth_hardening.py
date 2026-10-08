"""Area 3 of the QA report: account enumeration (M-04), real client IP + shared limits (M-05), allowlist revocation
(M-06), console mail in production (M-07), login timing (L-05), reset lock-out by others (L-06), typed names in the
log (L-08), concurrent username change (L-09). No network; the mailer is an in-memory mailbox."""
from __future__ import annotations

import dataclasses
import logging
import time
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from api.app import clientip, mailer, otp
from api.app import ratelimit as rl
from api.app.security import create_session_token, cookie_name, hash_password
from src import db
from src.db.models import OtpCode, RateLimitEvent, User

PW = "river-stone-lantern-42"


@pytest.fixture()
def mailbox(monkeypatch):
    box: list[mailer.Message] = []
    monkeypatch.setattr(mailer, "send", lambda m: box.append(m))
    return box


@pytest.fixture()
def user_factory():
    made: list[int] = []

    def make(**kw) -> User:
        tag = uuid.uuid4().hex[:8]
        kw.setdefault("username", f"u{tag}")
        kw.setdefault("email", f"{tag}@example.com")
        pw = kw.pop("password", PW)
        with db.session() as s:
            u = User(password_hash=hash_password(pw) if pw else None, name="Pat Example", **kw)
            s.add(u)
            s.flush()
            made.append(u.id)
            uid = u.id
        with db.session() as s:
            return s.get(User, uid)
    yield make
    with db.session() as s:
        s.execute(delete(OtpCode).where(OtpCode.user_id.in_(made)))
        s.execute(delete(User).where(User.id.in_(made)))


def _code(msg) -> str:
    import re
    return re.search(r"\b(\d \d \d \d \d \d)\b", msg.text).group(1).replace(" ", "")


# --------------------------------------------------------------------------- QA-M-04
def test_reset_never_says_weak_password_without_a_valid_code(client, user_factory, mailbox):
    u = user_factory()
    weak = {"code": "123456", "new_password": "a"}
    unknown = client.post("/api/auth/password/reset", json={"identifier": "nobody-here@example.com", **weak})
    known = client.post("/api/auth/password/reset", json={"identifier": u.username, **weak})
    assert unknown.status_code == known.status_code == 400 and unknown.json() == known.json()

    client.post("/api/auth/password/forgot", json={"identifier": u.email})
    code = _code(mailbox[-1])
    r = client.post("/api/auth/password/reset", json={"identifier": u.email, "code": code, "new_password": "a"})
    assert r.status_code == 422                                   # only the code holder learns about strength
    r = client.post("/api/auth/password/reset", json={"identifier": u.email, "code": code,
                                                      "new_password": "a-much-better-passphrase-9"})
    assert r.status_code == 200                                   # the weak try didn't burn the code


def test_unknown_names_do_no_extra_bcrypt_and_every_answer_waits_for_the_floor(client, user_factory, mailbox,
                                                                              monkeypatch):
    import bcrypt
    calls = []
    real = bcrypt.checkpw
    monkeypatch.setattr(bcrypt, "checkpw", lambda *a: calls.append(1) or real(*a))
    monkeypatch.setenv("RECOVERY_MIN_MS", "250")
    u = user_factory()
    timings = {}
    for label, ident in (("known", u.email), ("unknown", "ghost-person@example.com")):
        t0 = time.monotonic()
        assert client.post("/api/auth/password/forgot", json={"identifier": ident}).status_code == 200
        t1 = time.monotonic()
        assert client.post("/api/auth/password/reset", json={"identifier": ident, "code": "000000",
                                                             "new_password": "whatever-long-1"}).status_code == 400
        timings[label] = (t1 - t0, time.monotonic() - t1)
    assert calls == []                                            # no bcrypt-only branch any more
    assert all(t >= 0.25 for pair in timings.values() for t in pair), timings


# --------------------------------------------------------------------------- QA-M-05
class _Req:
    def __init__(self, headers: dict, peer="130.176.1.1"):
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.client = type("C", (), {"host": peer})()


@pytest.mark.parametrize("env,headers,expected", [
    ({}, {"CloudFront-Viewer-Address": "203.0.113.7:4431", "X-Forwarded-For": "1.2.3.4"}, "130.176.1.1"),
    ({"CLIENT_IP_SOURCE": "cloudfront", "ORIGIN_VERIFY": "x"}, {"CloudFront-Viewer-Address": "203.0.113.7:4431"}, "203.0.113.7"),
    ({"CLIENT_IP_SOURCE": "cloudfront", "ORIGIN_VERIFY": "x"}, {"CloudFront-Viewer-Address": "2001:db8::5:4431"}, "2001:db8::5"),
    ({"CLIENT_IP_SOURCE": "cloudfront", "ORIGIN_VERIFY": "x"}, {"CloudFront-Viewer-Address": "[2001:db8::5]:443"}, "2001:db8::5"),
    ({"CLIENT_IP_SOURCE": "cloudfront", "ORIGIN_VERIFY": "x"}, {"CloudFront-Viewer-Address": "evil"}, "130.176.1.1"),
    ({"CLIENT_IP_SOURCE": "cloudfront", "ORIGIN_VERIFY": "x"}, {"X-Forwarded-For": "198.51.100.66"}, "130.176.1.1"),
    ({"CLIENT_IP_SOURCE": "cloudfront"}, {"CloudFront-Viewer-Address": "203.0.113.7:1"}, "130.176.1.1"),  # not provably CloudFront
    ({"CLIENT_IP_SOURCE": "x-forwarded-for"}, {"X-Forwarded-For": "6.6.6.6, 203.0.113.8"}, "203.0.113.8"),
    ({"CLIENT_IP_SOURCE": "x-forwarded-for", "TRUSTED_PROXY_HOPS": "2"}, {"X-Forwarded-For": "6.6.6.6, 203.0.113.8, 10.0.0.1"}, "203.0.113.8"),
    ({"CLIENT_IP_SOURCE": "x-forwarded-for"}, {"X-Forwarded-For": "not-an-ip"}, "130.176.1.1"),
])
def test_client_ip_only_from_a_trusted_source(monkeypatch, env, headers, expected):
    for k in ("CLIENT_IP_SOURCE", "ORIGIN_VERIFY", "TRUSTED_PROXY_HOPS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert clientip.client_ip(_Req(headers)) == expected


def test_one_viewer_on_a_shared_edge_cannot_lock_out_another(client, monkeypatch):
    """The QA repro: 20 failed logins through one CloudFront edge, then the admin from another viewer."""
    monkeypatch.setenv("CLIENT_IP_SOURCE", "cloudfront")
    monkeypatch.setenv("ORIGIN_VERIFY", "sentinel-verify")
    attacker = {"CloudFront-Viewer-Address": "198.51.100.66:5000"}
    for i in range(rl.PER_IP):
        r = client.post("/api/auth/login", json={"username": f"spray{i}", "password": "nope-nope"},
                        headers={**attacker, "X-Forwarded-For": f"10.9.9.{i}"})   # spoofed XFF changes nothing
        assert r.status_code == 401
    assert client.post("/api/auth/login", json={"username": "spray99", "password": "x"},
                       headers=attacker).status_code == 429                        # the attacker IS limited
    ok = client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery"},
                     headers={"CloudFront-Viewer-Address": "203.0.113.200:6000"})
    assert ok.status_code == 200


def test_limits_are_shared_between_processes():
    a, b = rl.SharedRateLimiter("qa-shared"), rl.SharedRateLimiter("qa-shared")   # two Lambda containers
    try:
        for _ in range(3):
            a.hit("k")
        assert b.retry_after("k", 3, 60) > 0 and b.retry_after("k", 4, 60) == 0
        b.reset("k")
        assert a.retry_after("k", 3, 60) == 0
    finally:
        a.clear()
    with db.session() as s:
        assert not s.scalars(select(RateLimitEvent).where(RateLimitEvent.key.like("qa-shared|%"))).first()


# --------------------------------------------------------------------------- QA-M-06
def test_removing_a_google_user_from_the_allowlist_revokes_password_and_sessions(client, user_factory, monkeypatch):
    from api.app import deps
    u = user_factory(username=None, via_google=True)       # made by Google sign-in, then set a password
    real = deps.settings()
    allow = {"emails": frozenset({u.email})}
    monkeypatch.setattr(deps, "settings", lambda: dataclasses.replace(real, allowed_google_emails=allow["emails"]))
    token, _ = create_session_token(u.id, u.token_version)
    client.cookies.set(cookie_name(), token)
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/login", json={"username": u.email, "password": PW}).status_code == 200

    allow["emails"] = frozenset({"someone-else@example.com"})                      # removed from the allowlist
    client.cookies.set(cookie_name(), token)
    assert client.get("/api/auth/me").status_code == 401                          # live session ends
    assert client.post("/api/auth/login", json={"username": u.email, "password": PW}).status_code == 401
    pw_admin = client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery"})
    assert pw_admin.status_code == 200                                            # password accounts unaffected


# --------------------------------------------------------------------------- QA-M-07
@pytest.fixture()
def production(monkeypatch):
    from api.app import settings as settings_mod
    real = settings_mod.settings()
    monkeypatch.setattr("api.app.settings.settings", lambda: dataclasses.replace(real, cookie_secure=True))
    for n in ("SMTP_HOST", "SMTP_USER", "SMTP_USERNAME", "MAIL_DRIVER", "MAIL_ALLOW_CONSOLE"):
        monkeypatch.delenv(n, raising=False)


def test_console_mail_is_refused_in_production(production, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("MAIL_OUTBOX_DIR", str(tmp_path))
    assert mailer.configured_for_codes() is False
    with pytest.raises(mailer.MailNotConfigured):
        mailer.send(mailer.Message("a@example.com", "s", "123456"))
    errors = []
    monkeypatch.setattr(mailer.log, "error", lambda msg, *a: errors.append(msg % a if a else msg))
    mailer.startup_check()
    assert errors and "EMAIL NOT CONFIGURED" in errors[0]
    monkeypatch.setenv("MAIL_ALLOW_CONSOLE", "true")                              # explicit opt-in only
    assert mailer.configured_for_codes() is True


def test_forgot_in_production_without_smtp_issues_and_sends_nothing(client, user_factory, production, monkeypatch, tmp_path):
    monkeypatch.setenv("MAIL_OUTBOX_DIR", str(tmp_path))
    u = user_factory()
    r = client.post("/api/auth/password/forgot", json={"identifier": u.email})
    assert r.status_code == 200                                                   # same public answer
    with db.session() as s:
        assert s.scalars(select(OtpCode).where(OtpCode.user_id == u.id)).first() is None
    assert not list(tmp_path.iterdir())


def test_signed_in_user_is_told_email_is_not_configured(client, user_factory, production):
    u = user_factory()
    token, csrf = create_session_token(u.id, u.token_version)
    client.cookies.set(cookie_name(), token)
    r = client.post("/api/profile/email/otp", json={"email": "new-address@example.com"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 503 and "isn't configured" in r.json()["detail"]


def test_console_driver_never_logs_the_code(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("MAIL_OUTBOX_DIR", str(tmp_path))
    with caplog.at_level(logging.INFO, logger="codexone.api.mail"):
        mailer.ConsoleTransport().send(mailer.otp_email("a@example.com", "482913", "reset"))
    assert "4 8 2 9 1 3" not in caplog.text and "482913" not in caplog.text
    assert "4 8 2 9 1 3" in (tmp_path / "latest.txt").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- QA-L-05 / QA-L-08
def test_every_failed_login_costs_one_bcrypt_and_logs_no_typed_name(client, user_factory, monkeypatch, caplog):
    import bcrypt
    google_only = user_factory(password=None, via_google=True, username=None)
    disabled = user_factory(is_active=False)
    calls = []
    real = bcrypt.checkpw
    monkeypatch.setattr(bcrypt, "checkpw", lambda *a: calls.append(1) or real(*a))
    with caplog.at_level(logging.WARNING, logger="codexone.api.auth"):
        for name in ("no-such-person", google_only.email, disabled.username, "admin"):
            calls.clear()
            r = client.post("/api/auth/login", json={"username": name, "password": "My-Secret-Typed-In-Wrong-Box"})
            assert r.status_code == 401 and len(calls) == 1, name
    assert "no-such-person" not in caplog.text and "My-Secret" not in caplog.text


# --------------------------------------------------------------------------- QA-L-09
def test_username_race_is_a_409_not_a_500(client, user_factory, monkeypatch):
    from api.app.routes import profile
    u = user_factory()
    token, csrf = create_session_token(u.id, u.token_version)
    client.cookies.set(cookie_name(), token)

    def lost_race(*a, **k):
        raise IntegrityError("UPDATE users", {}, Exception("users_username_key"))
    monkeypatch.setattr(profile, "_update_profile", lost_race)
    r = client.patch("/api/profile", json={"username": "race1"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409 and "taken" in r.json()["detail"]
    monkeypatch.setattr(profile, "_change_email", lost_race)
    r = client.post("/api/profile/email", json={"email": "x@example.com", "code": "123456"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409


# --------------------------------------------------------------------------- QA-M-04 (Background email timing)
def test_forgot_queues_email_in_background_tasks(user_factory):
    """Forgot password delegates mail sending to BackgroundTasks so SMTP latency never blocks response."""
    from fastapi import BackgroundTasks
    from unittest.mock import MagicMock
    from api.app.routes.recovery import forgot, ForgotBody

    u = user_factory()
    bg = BackgroundTasks()
    req = MagicMock()
    req.headers = {}
    req.client.host = "127.0.0.1"

    res = forgot(ForgotBody(identifier=u.email), req, bg)
    assert res["ok"] is True
    assert len(bg.tasks) == 1
    # Unknown user gets generic answer and enqueues NO email
    bg_unknown = BackgroundTasks()
    res_unknown = forgot(ForgotBody(identifier="ghost@example.com"), req, bg_unknown)
    assert res_unknown["ok"] is True
    assert len(bg_unknown.tasks) == 0


# --------------------------------------------------------------------------- QA-L-06 (Multi-IP reset resilience)
def test_reset_valid_code_not_locked_out_by_multi_ip_attackers(client, user_factory, mailbox, monkeypatch):
    """An attacker across multiple IPs exhausting failed attempts cannot lock out a user with a valid code."""
    monkeypatch.setenv("CLIENT_IP_SOURCE", "x-forwarded-for")
    u = user_factory()

    # Attacker IP 1 makes wrong guesses until limited (6 tries)
    for _ in range(rl.OTP_TRY_PER_ACCOUNT_IP):
        r = client.post("/api/auth/password/reset",
                        json={"identifier": u.email, "code": "000000", "new_password": "new-strong-pass-1"},
                        headers={"X-Forwarded-For": "198.51.100.66"})
        assert r.status_code == 400
    r1 = client.post("/api/auth/password/reset",
                     json={"identifier": u.email, "code": "000000", "new_password": "new-strong-pass-1"},
                     headers={"X-Forwarded-For": "198.51.100.66"})
    assert r1.status_code == 429

    # Attacker IP 2 also makes wrong guesses until account cap is reached
    for _ in range(rl.OTP_TRY_PER_ACCOUNT_IP):
        client.post("/api/auth/password/reset",
                    json={"identifier": u.email, "code": "000000", "new_password": "new-strong-pass-1"},
                    headers={"X-Forwarded-For": "198.51.100.67"})
    # IP 2 now gets 429 for wrong guesses
    r2 = client.post("/api/auth/password/reset",
                     json={"identifier": u.email, "code": "000000", "new_password": "new-strong-pass-1"},
                     headers={"X-Forwarded-For": "198.51.100.67"})
    assert r2.status_code == 429

    # Legitimate user requests a code from their own IP and submits the valid code
    client.post("/api/auth/password/forgot", json={"identifier": u.email}, headers={"X-Forwarded-For": "203.0.113.10"})
    valid_code = _code(mailbox[-1])
    res = client.post("/api/auth/password/reset",
                      json={"identifier": u.email, "code": valid_code, "new_password": "a-stronger-passphrase-99"},
                      headers={"X-Forwarded-For": "203.0.113.10"})
    # The valid code succeeds (200), NOT locked out by previous attacker failed attempts
    assert res.status_code == 200
