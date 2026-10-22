"""Self-serve account deletion (POST /api/profile/delete, src/account_deletion.py)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from api.tests.test_profile import PW, code_from, fresh, mailbox, make_user, sign_in_cookie  # noqa: F401 (fixtures)
from src import activity, billing, db, upload
from src import queue_store as q
from src.db.models import ActivityLog, Post, User, UserConfigValue

CLOUD = "https://res.cloudinary.com/demo"


@pytest.fixture()
def gone_media(monkeypatch):
    """Cloudinary is never called: records what would be deleted."""
    seen: list[str] = []
    monkeypatch.setattr(upload, "delete_media", lambda urls: seen.extend(urls) or len(urls))
    return seen


@pytest.fixture()
def razorpay(monkeypatch):
    """A fake Razorpay with one active subscription per test; records cancellations."""
    state = {"subs": {}, "cancelled": [], "fail": False}

    def call(method, path, data=None):
        if state["fail"]:
            raise billing.BillingError("payment_error", "HTTP 500")
        sid = path.split("/")[2]
        if path.endswith("/cancel"):
            state["cancelled"].append((sid, data["cancel_at_cycle_end"]))
            state["subs"][sid]["status"] = "cancelled"
        return dict(state["subs"][sid])

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(billing, "_call", call)
    return state


def _with_data(uid: int, razorpay=None) -> None:
    """Give the account what a real one has: a post with media, a token, an activity entry, a subscription."""
    q.save([q.Item(id=f"del-{uid}-c", kind="carousel", date="2026-10-22", topic="T", category="AI", post_dir="o/d",
                   caption="c", user_id=uid, media={"carousel": [f"{CLOUD}/image/upload/v1/codexone/d/{uid}/s1.jpg",
                                                                  f"{CLOUD}/image/upload/v1/codexone/d/{uid}/s2.jpg"]}),
            q.Item(id=f"del-{uid}-r", kind="reel", date="2026-10-22", topic="T", category="AI", post_dir="o/d",
                   caption="c", user_id=uid, media={"reel": f"{CLOUD}/video/upload/v1/codexone/d/{uid}/reel.mp4"})])
    with db.session() as s:
        s.add(UserConfigValue(user_id=uid, key="TG_CHAT_ID", is_secret=False, value_plain="42",
                              updated_at=datetime.now(timezone.utc)))
        u = s.get(User, uid)
        if razorpay is not None:
            razorpay["subs"][f"sub_{uid}"] = {"id": f"sub_{uid}", "status": "active"}
            u.razorpay_subscription_id, u.subscription_tier, u.subscription_status = f"sub_{uid}", "creator", "active"
        name = u.username or u.email
    activity.record("post.approved", "Approved", source="dashboard", actor=name, detail={"email": "who@example.com"})


def _delete(client, **body):
    return client.post("/api/profile/delete", json={"confirm": "DELETE", **body})


def test_wrong_confirmation_or_password_deletes_nothing(client, make_user, gone_media):
    u = make_user(username="del-a", email="del-a@example.com", password=PW)
    sign_in_cookie(client, u)
    assert client.post("/api/profile/delete", json={"confirm": "delete", "current_password": PW}).status_code == 422
    assert _delete(client, current_password="wrong-password").status_code == 400
    assert fresh(u.id) is not None and gone_media == []


def test_deleting_erases_the_account_and_stops_billing(client, make_user, gone_media, razorpay):
    u = make_user(username="del-b", email="del-b@example.com", password=PW)
    _with_data(u.id, razorpay)
    sign_in_cookie(client, u)
    r = _delete(client, current_password=PW)
    assert r.status_code == 200, r.text
    assert r.json()["posts"] == 2
    assert razorpay["cancelled"] == [(f"sub_{u.id}", 0)]                 # billing stopped now, not at period end
    assert fresh(u.id) is None
    with db.session() as s:
        assert s.scalars(select(Post).where(Post.id.like(f"del-{u.id}-%"))).all() == []
        assert s.scalars(select(UserConfigValue).where(UserConfigValue.user_id == u.id)).all() == []   # tokens gone
        assert s.scalars(select(ActivityLog).where(ActivityLog.actor == "del-b")).all() == []          # anonymised
        trail = s.scalars(select(ActivityLog).where(ActivityLog.event == "account.deleted")
                          .order_by(ActivityLog.id.desc())).first()
        assert trail.actor == "deleted user" and "del-b" not in (trail.message or "")
    assert sorted(gone_media) == sorted([f"{CLOUD}/image/upload/v1/codexone/d/{u.id}/s1.jpg",
                                         f"{CLOUD}/image/upload/v1/codexone/d/{u.id}/s2.jpg",
                                         f"{CLOUD}/video/upload/v1/codexone/d/{u.id}/reel.mp4"])
    assert client.get("/api/profile").status_code == 401                 # signed out


def test_google_account_proves_it_with_an_emailed_code(client, make_user, mailbox, gone_media):
    u = make_user(username=False, email="del-c@example.com", verified=True)
    sign_in_cookie(client, u)
    assert _delete(client, code="000000").status_code == 400
    assert client.post("/api/profile/delete/otp").status_code == 200
    code = code_from(mailbox[-1])
    assert "Delete your account" in mailbox[-1].text or "delete" in mailbox[-1].subject.lower()
    assert _delete(client, code=code).status_code == 200
    assert fresh(u.id) is None


def test_if_billing_cant_be_stopped_nothing_is_deleted(client, make_user, gone_media, razorpay):
    u = make_user(username="del-d", email="del-d@example.com", password=PW)
    _with_data(u.id, razorpay)
    razorpay["fail"] = True
    sign_in_cookie(client, u)
    r = _delete(client, current_password=PW)
    assert r.status_code == 502 and r.json()["detail"]["code"] == "billing"
    assert fresh(u.id) is not None and gone_media == []
    with db.session() as s:
        assert len(s.scalars(select(Post).where(Post.id.like(f"del-{u.id}-%"))).all()) == 2


def test_the_owner_account_cant_be_deleted(client, make_user, gone_media):
    u = make_user(username="del-e", email="del-e@example.com", password=PW)
    with db.session() as s:
        s.get(User, u.id).role = "owner"
    sign_in_cookie(client, u)
    r = _delete(client, current_password=PW)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "owner"
    assert fresh(u.id) is not None


def test_media_cleanup_only_touches_our_own_folder():
    assert upload.public_id_of(f"{CLOUD}/image/upload/v1729/codexone/2026-10-21/x/carousel/slide_01.jpg") == \
        ("codexone/2026-10-21/x/carousel/slide_01", "image")
    assert upload.public_id_of(f"{CLOUD}/video/upload/v1/codexone/a/reel.mp4") == ("codexone/a/reel", "video")
    assert upload.public_id_of(f"{CLOUD}/image/upload/v1/someone-else/a.jpg") is None
    assert upload.public_id_of("https://evil.example/codexone/a.jpg") is None
