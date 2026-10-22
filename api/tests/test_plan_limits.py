"""Plan limits (src/plan_limits.py): quotas, schedule and platform caps, regenerations, publishing, the owner.

The signed-in test account is the install's owner (exempt); `customer` turns it into an ordinary customer on a
given plan for one test and puts it back afterwards (the test DB is shared).
"""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src import db, github_actions, plan_limits
from src import queue_store as q
from src.db.models import Post, User

_ids = itertools.count(1)
IST = plan_limits.IST


def _me(c) -> int:
    return c.get("/api/profile").json()["id"]


@pytest.fixture()
def customer(authed):
    """customer(tier, status="active") makes the signed-in account a non-owner on that plan; restored after."""
    uid = _me(authed)
    with db.session() as s:
        u = s.get(User, uid)
        saved = (u.role, u.subscription_tier, u.subscription_status, dict(u.cadence or {}), dict(u.taste or {}))

    def make(tier: str, status: str = "active") -> int:
        with db.session() as s:
            u = s.get(User, uid)
            u.role, u.subscription_tier, u.subscription_status = "admin", tier, status
        return uid

    yield make
    with db.session() as s:
        u = s.get(User, uid)
        u.role, u.subscription_tier, u.subscription_status, u.cadence, u.taste = saved
        s.execute(Post.__table__.delete().where(Post.id.like("pl-%")))


def _posts(uid: int, kind: str, n: int, version: int = 1, when: datetime | None = None) -> None:
    when = when or datetime.now(timezone.utc)
    items = []
    for _ in range(n):
        i = next(_ids)
        items.append(q.Item(id=f"pl-{kind[0]}{i}-v{version}", kind=kind, date=when.date().isoformat(), topic=f"Topic {i}",
                            category="AI", post_dir=f"output/x/{i}", caption="c", version=version, user_id=uid,
                            media={"carousel": ["https://x/1.jpg"]} if kind == "carousel" else {"reel": "https://x/r.mp4"},
                            created_at=when.isoformat()))
    q.save(items)


@pytest.fixture()
def gh(monkeypatch):
    sent = []
    monkeypatch.setattr(github_actions, "configured", lambda: True)
    monkeypatch.setattr(github_actions, "dispatch", lambda wf, inputs, ref="main": sent.append(inputs))
    return sent


def _generate(c):
    return c.post("/api/generate", json={"slot": "auto", "idempotency_key": f"pl-key-{next(_ids):06d}", "force": True})


def user(tier="starter", status="active", role="admin", uid=1):
    return SimpleNamespace(id=uid, role=role, subscription_tier=tier, subscription_status=status)


# --------------------------------------------------------------------------- #
# Rules, without the API
# --------------------------------------------------------------------------- #
def test_a_plan_counts_only_while_it_is_paid_for():
    assert plan_limits.plan_for(user("creator", "active"))["id"] == "creator"
    for status in ("past_due", "canceling", "changing"):          # still inside a paid period
        assert plan_limits.plan_for(user("creator", status))["id"] == "creator"
    for status in ("halted", "canceled", "paused"):
        assert plan_limits.plan_for(user("creator", status)) is plan_limits.NO_PLAN
    assert plan_limits.plan_for(user("free")) is plan_limits.NO_PLAN


def test_the_owner_is_never_limited():
    owner = user("free", role="owner")
    assert plan_limits.check_generation(owner) == {"reel": True}
    plan_limits.check_cadence(owner, {"slots": ["09:00", "12:00", "15:00", "18:00", "21:00"]})
    plan_limits.check_targets(owner, ["ig", "yt"])


def test_lite_makes_carousels_only():
    assert plan_limits.check_generation(user("lite", uid=10**9)) == {"reel": False}


def test_month_window_rolls_over_the_year():
    start, end = plan_limits.month_window(datetime(2026, 12, 15, 10, tzinfo=IST))
    assert (start.isoformat()[:10], end.isoformat()[:10]) == ("2026-12-01", "2027-01-01")


def test_slots_per_day_in_every_schedule_mode():
    assert plan_limits.slots_per_day({"slots": ["09:00", "18:00"]}) == 2
    assert plan_limits.slots_per_day({"schedule_mode": "weekly", "weekly_slots": {"mon": ["09:00"], "tue": ["09:00", "12:00", "18:00"]}}) == 3
    assert plan_limits.slots_per_day({"schedule_mode": "ai", "ai_schedule": {"ig": ["09:00", "18:00"], "yt": ["18:00"]}}) == 2
    assert plan_limits.slots_per_day({"posts_per_day": 3, "slots": ["09:00"]}) == 3


# --------------------------------------------------------------------------- #
# Usage and quotas
# --------------------------------------------------------------------------- #
def test_usage_counts_this_months_new_posts_only(authed, customer):
    uid = customer("starter")
    base = plan_limits.usage(uid)                       # other tests' posts may belong to this account too
    _posts(uid, "reel", 2)
    _posts(uid, "carousel", 3)
    _posts(uid, "reel", 4, version=2)                                   # regenerated versions: free
    _posts(uid, "carousel", 5, when=datetime.now(timezone.utc) - timedelta(days=40))   # last month
    expect = {"reels": base["reels"] + 2, "carousels": base["carousels"] + 3}
    assert plan_limits.usage(uid) == expect
    st = authed.get("/api/subscription/status").json()["usage"]
    assert st["plan"] == "starter" and st["used"] == expect and st["exempt"] is False
    assert st["left"] == {k: max(0, 30 - expect[k]) for k in expect}


def test_generate_without_a_plan_is_refused(authed, customer, gh):
    customer("free")
    r = _generate(authed)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "plan_required" and gh == []


def test_generate_after_the_monthly_quota_is_refused(authed, customer, gh):
    uid = customer("starter")
    _posts(uid, "carousel", 30)
    r = _generate(authed)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "quota_reached" and gh == []
    assert "reset" in r.json()["detail"]["message"]


def test_when_reels_run_out_the_run_makes_the_carousel_only(authed, customer):
    uid = customer("starter")
    _posts(uid, "reel", 30)
    _posts(uid, "carousel", 10)
    assert plan_limits.check_generation(plan_limits.load_user(uid)) == {"reel": False}


def test_generate_within_quota_runs_for_the_requester(authed, customer, gh):
    uid = customer("creator")
    r = _generate(authed)
    assert r.status_code == 201, r.text
    assert gh[-1]["user_id"] == str(uid)


def test_the_generation_job_checks_again(authed, customer):
    """A run dispatched some other way (or after the quota filled up meanwhile) stops before any work."""
    import main
    uid = customer("lite")
    _posts(uid, "carousel", 30)
    assert main.main(["generate", "--user-id", str(uid), "--dry-run"]) == 0   # skipped, nothing fetched


# --------------------------------------------------------------------------- #
# Schedule and platforms
# --------------------------------------------------------------------------- #
def test_schedule_is_capped_by_the_plan(authed, customer):
    customer("starter")                                                # 1 post a day
    r = authed.patch("/api/profile", json={"cadence": {"schedule_mode": "uniform", "posts_per_day": 2, "slots": ["09:00", "18:00"]}})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_many_slots"
    ok = authed.patch("/api/profile", json={"cadence": {"schedule_mode": "uniform", "posts_per_day": 1, "slots": ["09:00"]}})
    assert ok.status_code == 200


def test_platforms_are_capped_by_the_plan(authed, customer):
    customer("lite")                                                   # Instagram only
    r = authed.patch("/api/profile", json={"taste": {"default_targets": ["ig", "yt"]}})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "platform_not_in_plan"
    assert authed.patch("/api/profile", json={"taste": {"default_targets": ["ig"]}}).status_code == 200


def test_publishing_follows_the_owners_plan(authed, customer):
    from src import publish
    uid = customer("lite")
    assert plan_limits.allowed_platforms(uid) == ("ig",)
    customer("free")
    assert plan_limits.allowed_platforms(uid) == ()
    item = q.Item(id=f"pl-p{next(_ids)}", kind="reel", date="2026-10-22", topic="T", category="AI", post_dir="o/p",
                  caption="c", media={"reel": "https://x/r.mp4"}, status="approved", user_id=uid)
    out = publish.publish_item(item, dry_run=True)
    assert out.status == "failed" and "plan isn't active" in out.error


# --------------------------------------------------------------------------- #
# Regenerations
# --------------------------------------------------------------------------- #
def test_each_post_can_be_regenerated_three_times(authed, customer):
    uid = customer("creator")
    item = q.Item(id=f"pl-g{next(_ids)}-v4", kind="carousel", date="2026-10-22", topic="T", category="AI",
                  post_dir="o/g", caption="c", media={"carousel": ["https://x/1.jpg"]}, version=4, user_id=uid)
    q.save([item])
    r = authed.post("/api/posts/regenerate", json={"item_ids": [item.id]})
    assert r.status_code == 409 and "regenerated 3 times" in r.text
    assert q.get(item.id).status == "pending"
