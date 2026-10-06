"""Profile, picture, email change, password change / first password, and emailed-code reset.

Every test makes its own throwaway users (the SQLite file is shared), and the mailer is replaced by
an in-memory mailbox so the codes can be read back.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from api.app import mailer, otp, ratelimit
from api.app.security import cookie_name, create_session_token, hash_password, verify_password
from src import db
from src.db.models import OtpCode, User

PW = "river-stone-lantern-42"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _clean():
    ratelimit.otp_limiter._hits.clear()
    yield


@pytest.fixture()
def mailbox(monkeypatch):
    box: list[mailer.Message] = []
    monkeypatch.setattr(mailer, "send", lambda m: box.append(m))
    return box


def code_from(msg: mailer.Message) -> str:
    return re.search(r"\b(\d \d \d \d \d \d)\b", msg.text).group(1).replace(" ", "")


@pytest.fixture()
def make_user():
    made: list[int] = []

    def make(*, username=None, email=None, password=None, name="Pat Example", verified=False) -> User:
        tag = uuid.uuid4().hex[:8]
        with db.session() as s:
            u = User(username=username if username is not False else None, email=email, name=name,
                     password_hash=hash_password(password) if password else None,
                     email_verified_at=datetime.now(timezone.utc) if verified else None)
            s.add(u)
            s.flush()
            made.append(u.id)
            uid = u.id
        with db.session() as s:
            return s.get(User, uid)

    yield make
    with db.session() as s:
        for uid in made:
            s.execute(delete(OtpCode).where(OtpCode.user_id == uid))
            s.execute(delete(User).where(User.id == uid))


def sign_in_cookie(client, user: User) -> None:
    """Sign in without a password (what a Google sign-in leaves behind)."""
    token, csrf = create_session_token(user.id, user.token_version)
    client.cookies.set(cookie_name(), token)
    client.headers["X-CSRF-Token"] = csrf


def fresh(uid: int) -> User:
    with db.session() as s:
        return s.get(User, uid)


# --------------------------------------------------------------------------- details
def test_profile_requires_sign_in(client):
    assert client.get("/api/profile").status_code == 401


def test_get_and_update_profile(authed):
    p = authed.get("/api/profile").json()
    assert p["username"] == "admin" and p["has_password"] is True and p["role"] == "Administrator"
    r = authed.patch("/api/profile", json={"name": "  Hitesh   Lalwani ", "job_title": "Founder", "bio": "Builds things.",
                                           "phone": "+91 98765 43210", "timezone": "Asia/Kolkata"})
    assert r.status_code == 200
    out = r.json()
    assert out["name"] == "Hitesh Lalwani" and out["job_title"] == "Founder" and out["phone"] == "+91 98765 43210"
    assert authed.get("/api/auth/me").json()["name"] == "Hitesh Lalwani"


@pytest.mark.parametrize("body", [
    {"name": "   "}, {"phone": "call me maybe"}, {"timezone": "Mars/Olympus"}, {"username": "a b"}, {"username": "ab"},
])
def test_profile_validation(authed, body):
    assert authed.patch("/api/profile", json=body).status_code == 422


def test_username_must_be_unique(authed, make_user):
    make_user(username="taken.name", password=PW)
    assert authed.patch("/api/profile", json={"username": "Taken.Name"}).status_code == 409


# --------------------------------------------------------------------------- picture
def test_avatar_upload_serve_delete(authed):
    r = authed.post("/api/profile/avatar", content=PNG, headers={"Content-Type": "image/png"})
    assert r.status_code == 200 and r.json()["has_avatar"] and r.json()["avatar_v"]
    got = authed.get("/api/profile/avatar")
    assert got.status_code == 200 and got.headers["content-type"] == "image/png" and got.content == PNG
    assert authed.get("/api/auth/me").json()["avatar_v"] == r.json()["avatar_v"]
    assert authed.delete("/api/profile/avatar").json()["has_avatar"] is False
    assert authed.get("/api/profile/avatar").status_code == 404


def test_avatar_rejects_wrong_or_oversized(authed):
    assert authed.post("/api/profile/avatar", content=b"GIF89a....", headers={"Content-Type": "image/png"}).status_code == 415
    assert authed.post("/api/profile/avatar", content=b"<svg onload=alert(1)>", headers={"Content-Type": "image/jpeg"}).status_code == 415
    assert authed.post("/api/profile/avatar", content=JPEG + b"\x00" * (400 * 1024), headers={"Content-Type": "image/jpeg"}).status_code == 413
    assert authed.post("/api/profile/avatar", content=b"", headers={"Content-Type": "image/png"}).status_code == 422
    assert authed.post("/api/profile/avatar", content=JPEG, headers={"Content-Type": "image/png"}).status_code == 200  # bytes decide


# --------------------------------------------------------------------------- change password (has one)
def test_change_password_needs_current_and_keeps_this_session(client, make_user):
    u = make_user(username="chg.user", email="chg@example.com", password=PW)
    assert client.post("/api/auth/login", json={"username": "chg.user", "password": PW}).status_code == 200
    client.headers["X-CSRF-Token"] = client.post("/api/auth/login", json={"username": "chg.user", "password": PW}).json()["csrf"]

    bad = client.post("/api/profile/password", json={"new_password": "another-long-pass-9", "current_password": "nope"})
    assert bad.status_code == 400
    weak = client.post("/api/profile/password", json={"new_password": "short", "current_password": PW})
    assert weak.status_code == 422
    same = client.post("/api/profile/password", json={"new_password": PW, "current_password": PW})
    assert same.status_code == 422

    ok = client.post("/api/profile/password", json={"new_password": "another-long-pass-9", "current_password": PW})
    assert ok.status_code == 200 and ok.json()["csrf"]
    client.headers["X-CSRF-Token"] = ok.json()["csrf"]
    assert client.get("/api/profile").status_code == 200                 # this device stays signed in
    assert verify_password("another-long-pass-9", fresh(u.id).password_hash)
    assert fresh(u.id).password_changed_at is not None


def test_other_devices_are_signed_out_after_password_change(client, make_user):
    from fastapi.testclient import TestClient
    from api.app.main import create_app
    u = make_user(username="dev.user", password=PW)
    other = TestClient(create_app())
    other.post("/api/auth/login", json={"username": "dev.user", "password": PW})
    assert other.get("/api/profile").status_code == 200
    r = client.post("/api/auth/login", json={"username": "dev.user", "password": PW})
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert client.post("/api/profile/password", json={"new_password": "brand-new-long-pass-7", "current_password": PW}).status_code == 200
    assert other.get("/api/profile").status_code == 401


# --------------------------------------------------------------------------- Google-only: first password by code
def test_google_only_user_sets_first_password_with_emailed_code(client, make_user, mailbox):
    u = make_user(email="gonly@example.com", password=None, name="Gee Only")
    sign_in_cookie(client, u)
    assert client.get("/api/profile").json()["has_password"] is False

    assert client.post("/api/profile/password", json={"new_password": PW}).status_code == 400   # no code yet
    assert client.post("/api/profile/password/otp").status_code == 200
    assert len(mailbox) == 1 and mailbox[0].to == "gonly@example.com"
    code = code_from(mailbox[0])

    assert client.post("/api/profile/password", json={"new_password": PW, "code": "000000"}).status_code == 400
    ok = client.post("/api/profile/password", json={"new_password": PW, "code": code})
    assert ok.status_code == 200 and ok.json()["profile"]["has_password"] is True
    assert fresh(u.id).email_verified_at is not None                                            # they proved the address

    # now they can sign in with email + password (no username needed)
    other = type(client)(client.app)
    r = other.post("/api/auth/login", json={"username": "gonly@example.com", "password": PW})
    assert r.status_code == 200


def test_set_password_code_refused_when_password_exists_or_no_email(client, make_user, mailbox):
    has = make_user(username="has.pw", email="has@example.com", password=PW)
    sign_in_cookie(client, has)
    assert client.post("/api/profile/password/otp").status_code == 409
    bare = make_user(password=None, email=None)
    sign_in_cookie(client, bare)
    assert client.post("/api/profile/password/otp").status_code == 409 and not mailbox


# --------------------------------------------------------------------------- forgot / reset (public)
def test_forgot_is_generic_for_unknown_accounts(client, make_user, mailbox):
    a = client.post("/api/auth/password/forgot", json={"identifier": "nobody@example.com"})
    b = make_user(username="real.one", email="realone@example.com", password=PW)
    c = client.post("/api/auth/password/forgot", json={"identifier": "real.one"})
    assert a.status_code == c.status_code == 200 and a.json()["message"] == c.json()["message"]
    assert len(mailbox) == 1 and mailbox[0].to == "realone@example.com"          # only the real one got mail


def test_account_without_email_gets_no_mail_but_same_answer(client, make_user, mailbox):
    make_user(username="no.mail", password=PW, email=None)
    assert client.post("/api/auth/password/forgot", json={"identifier": "no.mail"}).status_code == 200
    assert mailbox == []


def test_full_reset_flow_signs_everyone_out_and_code_works_once(client, make_user, mailbox):
    u = make_user(username="reset.me", email="resetme@example.com", password=PW, name="Reset Me")
    client.post("/api/auth/password/forgot", json={"identifier": "resetme@example.com"})
    code = code_from(mailbox[0])
    assert "Reset Me".split()[0] in mailbox[0].text and mailbox[0].html and code in mailbox[0].html

    body = {"identifier": "resetme@example.com", "code": code, "new_password": "fresh-new-secret-55"}
    assert client.post("/api/auth/password/reset", json={**body, "new_password": "weak"}).status_code == 422  # doesn't burn the code
    ok = client.post("/api/auth/password/reset", json=body)
    assert ok.status_code == 200
    assert client.post("/api/auth/password/reset", json=body).status_code == 400                              # single use
    assert client.post("/api/auth/login", json={"username": "reset.me", "password": "fresh-new-secret-55"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "reset.me", "password": PW}).status_code == 401
    assert fresh(u.id).token_version == u.token_version + 1


def test_wrong_codes_lock_the_code_after_five_tries(client, make_user, mailbox):
    make_user(username="lock.me", email="lockme@example.com", password=PW)
    client.post("/api/auth/password/forgot", json={"identifier": "lock.me"})
    code = code_from(mailbox[0])
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post("/api/auth/password/reset", json={"identifier": "lock.me", "code": wrong,
                                                             "new_password": "fresh-new-secret-55"}).status_code == 400
    # even the right code is dead now
    assert client.post("/api/auth/password/reset", json={"identifier": "lock.me", "code": code,
                                                         "new_password": "fresh-new-secret-55"}).status_code == 400


def test_expired_code_is_rejected(client, make_user, mailbox):
    u = make_user(username="old.code", email="oldcode@example.com", password=PW)
    client.post("/api/auth/password/forgot", json={"identifier": "old.code"})
    code = code_from(mailbox[0])
    with db.session() as s:
        row = s.scalars(select(OtpCode).where(OtpCode.user_id == u.id)).first()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.post("/api/auth/password/reset", json={"identifier": "old.code", "code": code,
                                                         "new_password": "fresh-new-secret-55"}).status_code == 400


def test_resend_has_a_cooldown_and_replaces_the_old_code(client, make_user, mailbox):
    make_user(username="resend.me", email="resendme@example.com", password=PW)
    client.post("/api/auth/password/forgot", json={"identifier": "resend.me"})
    client.post("/api/auth/password/forgot", json={"identifier": "resend.me"})      # inside the cooldown
    assert len(mailbox) == 1
    with db.session() as s:                                                          # pretend a minute passed
        for row in s.scalars(select(OtpCode)).all():
            row.created_at = datetime.now(timezone.utc) - timedelta(seconds=otp.RESEND_COOLDOWN + 1)
    client.post("/api/auth/password/forgot", json={"identifier": "resend.me"})
    assert len(mailbox) == 2
    old, new = code_from(mailbox[0]), code_from(mailbox[1])
    if old != new:
        assert client.post("/api/auth/password/reset", json={"identifier": "resend.me", "code": old,
                                                             "new_password": "fresh-new-secret-55"}).status_code == 400


def test_forgot_is_rate_limited(client, make_user, mailbox):
    for _ in range(ratelimit.OTP_SEND_PER_ADDRESS):
        assert client.post("/api/auth/password/forgot", json={"identifier": "spam@example.com"}).status_code == 200
    assert client.post("/api/auth/password/forgot", json={"identifier": "spam@example.com"}).status_code == 429


# --------------------------------------------------------------------------- email change
def test_change_email_needs_code_sent_to_new_address(client, make_user, mailbox):
    u = make_user(username="mail.chg", email="old@example.com", password=PW, verified=True)
    sign_in_cookie(client, u)
    other = make_user(username="mail.other", email="inuse@example.com", password=PW)
    assert client.post("/api/profile/email/otp", json={"email": "inuse@example.com"}).status_code == 409
    assert client.post("/api/profile/email/otp", json={"email": "not-an-email"}).status_code == 422

    assert client.post("/api/profile/email/otp", json={"email": "New@Example.com"}).status_code == 200
    assert mailbox[-1].to == "new@example.com"
    code = code_from(mailbox[-1])
    assert client.post("/api/profile/email", json={"email": "new@example.com", "code": "123456" if code != "123456" else "654321"}).status_code == 400
    ok = client.post("/api/profile/email", json={"email": "new@example.com", "code": code})
    assert ok.status_code == 200 and ok.json()["email"] == "new@example.com" and ok.json()["email_verified"] is True


def test_code_is_bound_to_the_address_it_was_sent_to(client, make_user, mailbox):
    u = make_user(username="bound", email="b@example.com", password=PW)
    sign_in_cookie(client, u)
    client.post("/api/profile/email/otp", json={"email": "first@example.com"})
    code = code_from(mailbox[-1])
    assert client.post("/api/profile/email", json={"email": "attacker@example.com", "code": code}).status_code == 400


# --------------------------------------------------------------------------- revoke other sessions
def test_revoke_other_sessions_keeps_this_one(client, make_user):
    from fastapi.testclient import TestClient
    from api.app.main import create_app
    make_user(username="revoker", password=PW)
    other = TestClient(create_app())
    other.post("/api/auth/login", json={"username": "revoker", "password": PW})
    r = client.post("/api/auth/login", json={"username": "revoker", "password": PW})
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    out = client.post("/api/profile/sessions/revoke")
    assert out.status_code == 200
    client.headers["X-CSRF-Token"] = out.json()["csrf"]
    assert client.get("/api/profile").status_code == 200 and other.get("/api/profile").status_code == 401


# --------------------------------------------------------------------------- admin seed no longer overwrites
def test_restart_does_not_overwrite_a_password_the_admin_changed(make_user):
    from api.app.main import sync_admin
    with db.session() as s:
        admin = s.scalars(select(User).where(User.username == "admin")).one()
        original = admin.password_hash
        admin.password_hash = hash_password("changed-in-the-profile-page")
    try:
        sync_admin()
        with db.session() as s:
            assert verify_password("changed-in-the-profile-page", s.scalars(select(User).where(User.username == "admin")).one().password_hash)
    finally:
        with db.session() as s:
            s.scalars(select(User).where(User.username == "admin")).one().password_hash = original
