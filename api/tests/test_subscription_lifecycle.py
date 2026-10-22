"""Subscription lifecycle: every way a plan can change, end to end against the fake Razorpay.

Policy under test (src/billing.py): upgrades start now, prorated; downgrades, interval downgrades and resuming a
cancelled plan start when the paid period ends; cancelling runs to the period end; a failed renewal keeps access
while Razorpay retries and ends it when every retry fails. Quotas (src/plan_limits.py) follow the plan in force.
"""
from __future__ import annotations

import pytest

from src import plan_limits
from api.tests.test_plan_limits import _posts, customer  # noqa: F401  (fixture)
from api.tests.test_subscription import (  # noqa: F401  (fixtures)
    _checkout, _details, _quote, _subscribe, _tier, _verify, _webhook, fresh_billing, rzp,
)


def _change(c, rzp, plan, interval="month"):
    """Quote, checkout and authorise a change; returns (quote, new subscription id, webhook outcome)."""
    q = _quote(c, plan, interval)
    sid = _checkout(c, q)["subscription_id"]
    out = _webhook(c, "subscription.authenticated", rzp.authorise(sid)).json()["outcome"]
    return q, sid, out


def _period_ends(c, rzp, old, new):
    """The paid period ends: Razorpay ends the old subscription and starts the scheduled one."""
    end = rzp.subs[old]["current_end"] or rzp.subs[old]["start_at"]   # an upgraded one ends where it was due to start
    _webhook(c, "subscription.cancelled", rzp.set(old, status="cancelled"))
    _webhook(c, "subscription.activated", rzp.set(new, status="active", current_start=end, current_end=end + 30 * 86400))


# --------------------------------------------------------------------------- #
# Changing plan
# --------------------------------------------------------------------------- #
def test_upgrade_then_change_your_mind_and_downgrade(authed, rzp):
    _details(authed)
    _subscribe(authed, rzp, "starter")
    q, up, out = _change(authed, rzp, "creator")
    assert (q["kind"], out) == ("upgrade", "activated") and _tier(authed) == ("creator", "active")
    q, down, out = _change(authed, rzp, "starter")                  # just paid for Creator: worth more than Starter
    assert (q["kind"], q["total_now"], out) == ("downgrade", 0, "scheduled")
    assert _tier(authed) == ("creator", "changing")                 # keeps what was paid for until the period ends
    _period_ends(authed, rzp, up, down)
    assert _tier(authed) == ("starter", "active")


def test_monthly_to_yearly_is_an_upgrade_now(authed, rzp):
    _details(authed)
    old = _subscribe(authed, rzp, "creator", "month", elapsed=0.5)
    q, new, out = _change(authed, rzp, "creator", "year")
    assert q["kind"] == "upgrade" and out == "activated"
    assert q["lines"][0]["amount"] == 2999000 and q["lines"][1]["amount"] < 0     # a year, minus the unused month
    assert rzp.cancelled[-1] == (old, 0) and _tier(authed) == ("creator", "active")


def test_yearly_to_monthly_waits_for_the_paid_year(authed, rzp):
    _details(authed)
    old = _subscribe(authed, rzp, "creator", "year", elapsed=0.1)
    q, new, out = _change(authed, rzp, "creator", "month")
    assert (q["kind"], q["total_now"], out) == ("downgrade", 0, "scheduled")
    assert q["effective_at"] == rzp.subs[old]["current_end"]


def test_lite_to_starter_unlocks_reels(authed, rzp, customer):
    customer("free")
    _details(authed)
    _subscribe(authed, rzp, "lite")
    uid = authed.get("/api/profile").json()["id"]
    assert plan_limits.check_generation(plan_limits.load_user(uid)) == {"reel": False}
    _change(authed, rzp, "starter")
    assert plan_limits.check_generation(plan_limits.load_user(uid)) == {"reel": True}


# --------------------------------------------------------------------------- #
# Cancelling, resuming, coming back
# --------------------------------------------------------------------------- #
def test_cancel_then_downgrade_before_the_period_ends(authed, rzp):
    _details(authed)
    old = _subscribe(authed, rzp, "pro", elapsed=0.1)
    authed.post("/api/subscription/cancel")
    q, new, out = _change(authed, rzp, "starter")
    assert (q["kind"], out) == ("downgrade", "scheduled")
    assert rzp.cancelled == [(old, 1)]                               # not cancelled a second time
    _period_ends(authed, rzp, old, new)
    assert _tier(authed) == ("starter", "active")


def test_cancel_then_keep_the_plan_after_all(authed, rzp):
    _details(authed)
    old = _subscribe(authed, rzp, "creator")
    authed.post("/api/subscription/cancel")
    assert _tier(authed) == ("creator", "canceling")
    q, new, out = _change(authed, rzp, "creator")                    # same plan again = resume
    assert (q["kind"], q["total_now"], out) == ("resume", 0, "scheduled")
    assert rzp.subs[new]["start_at"] == rzp.subs[old]["current_end"] and not rzp.subs[new]["addons"]
    _period_ends(authed, rzp, old, new)
    assert _tier(authed) == ("creator", "active")


def test_cancel_then_upgrade_starts_now(authed, rzp):
    _details(authed)
    old = _subscribe(authed, rzp, "starter", elapsed=0.5)
    authed.post("/api/subscription/cancel")
    q, new, out = _change(authed, rzp, "pro")
    assert (q["kind"], out) == ("upgrade", "activated") and _tier(authed) == ("pro", "active")
    assert rzp.cancelled[-1] == (old, 0)


def test_cancelling_twice_says_so(authed, rzp):
    _details(authed)
    _subscribe(authed, rzp, "creator")
    authed.post("/api/subscription/cancel")
    r = authed.post("/api/subscription/cancel")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "already_canceling"


def test_coming_back_after_the_plan_ended(authed, rzp):
    _details(authed)
    old = _subscribe(authed, rzp, "creator")
    authed.post("/api/subscription/cancel")
    _webhook(authed, "subscription.cancelled", rzp.set(old, status="cancelled"))
    assert _tier(authed) == ("free", "canceled")
    q, new, out = _change(authed, rzp, "starter")
    assert q["kind"] == "new"
    _webhook(authed, "subscription.activated", rzp.set(new, status="active"))
    assert _tier(authed) == ("starter", "active")


def test_coming_back_after_payments_failed_stops_the_old_subscription(authed, rzp):
    _details(authed)
    old = _subscribe(authed, rzp, "creator")
    _webhook(authed, "subscription.halted", rzp.set(old, status="halted"))
    assert _tier(authed) == ("free", "halted")
    q = _quote(authed, "creator")
    assert q["kind"] == "new"                                        # a halted plan has nothing left to credit
    sid = _checkout(authed, q)["subscription_id"]
    rzp.authorise(sid)
    assert _verify(authed, sid).json()["outcome"] == "activated"
    assert (old, 0) in rzp.cancelled                                 # a fixed card can't revive the old one


# --------------------------------------------------------------------------- #
# Checkout edge cases
# --------------------------------------------------------------------------- #
def test_a_second_checkout_closes_the_first(authed, rzp):
    _details(authed)
    first = _checkout(authed, _quote(authed, "creator"))["subscription_id"]
    second = _checkout(authed, _quote(authed, "pro"))["subscription_id"]
    assert (first, 0) in rzp.cancelled                               # the other tab can't be paid any more
    assert _webhook(authed, "subscription.activated", rzp.subs[first]).json()["outcome"] == "ignored"
    _webhook(authed, "subscription.activated", rzp.authorise(second))
    assert _tier(authed) == ("pro", "active")


def test_no_new_checkout_while_a_payment_is_being_confirmed(authed, rzp):
    _details(authed)
    _subscribe(authed, rzp, "starter")
    q = _quote(authed, "creator")
    sid = _checkout(authed, q)["subscription_id"]
    rzp.authorise(sid)                                               # paid, but our webhook hasn't arrived yet
    q2 = _quote(authed, "pro")
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month",
                                                       "quote_at": q2["quote_at"], "expected_total": q2["total_now"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "payment_in_progress"


def test_events_out_of_order_still_land_on_the_right_plan(authed, rzp):
    _details(authed)
    _subscribe(authed, rzp, "starter", elapsed=0.5)
    q = _quote(authed, "creator")
    sid = _checkout(authed, q)["subscription_id"]
    rzp.authorise(sid)
    end = rzp.subs[sid]["start_at"]
    # Razorpay can deliver "activated" (when the regular charges start) before "authenticated"
    _webhook(authed, "subscription.activated", rzp.set(sid, status="active", current_start=end, current_end=end + 86400 * 30))
    assert _tier(authed) == ("creator", "active")
    assert _webhook(authed, "subscription.authenticated", rzp.subs[sid]).json()["outcome"] == "ignored"


def test_nothing_can_change_while_a_downgrade_is_scheduled(authed, rzp):
    _details(authed)
    _subscribe(authed, rzp, "pro", elapsed=0.1)
    _change(authed, rzp, "starter")
    assert authed.post("/api/subscription/quote", json={"plan_id": "creator"}).json()["detail"]["code"] == "change_scheduled"
    assert authed.post("/api/subscription/cancel").json()["detail"]["code"] == "change_scheduled"


# --------------------------------------------------------------------------- #
# Quotas across plan changes
# --------------------------------------------------------------------------- #
def test_upgrading_mid_month_raises_the_quota_at_once(authed, rzp, customer):
    uid = customer("free")
    _details(authed)
    _subscribe(authed, rzp, "starter")
    _posts(uid, "carousel", 30)
    with pytest.raises(plan_limits.PlanLimit) as e:
        plan_limits.check_generation(plan_limits.load_user(uid))
    assert e.value.code == "quota_reached"
    _change(authed, rzp, "creator")
    assert plan_limits.check_generation(plan_limits.load_user(uid))["reel"] is True


def test_after_a_downgrade_this_months_usage_still_counts(authed, rzp, customer):
    uid = customer("free")
    _details(authed)
    old = _subscribe(authed, rzp, "pro", elapsed=0.1)
    _posts(uid, "carousel", 40)                                       # fine on Pro (120)
    q, new, _ = _change(authed, rzp, "lite")
    assert plan_limits.check_generation(plan_limits.load_user(uid)) == {"reel": True}   # still Pro until the end
    _period_ends(authed, rzp, old, new)
    with pytest.raises(plan_limits.PlanLimit) as e:                  # Lite allows 30 a month: wait for the 1st
        plan_limits.check_generation(plan_limits.load_user(uid))
    assert e.value.code == "quota_reached"


def test_access_follows_the_payment_state(authed, rzp, customer):
    uid = customer("free")
    _details(authed)
    sid = _subscribe(authed, rzp, "creator")
    me = lambda: plan_limits.load_user(uid)                           # noqa: E731
    _webhook(authed, "subscription.pending", rzp.set(sid, status="pending"))
    assert plan_limits.check_generation(me())["reel"] is True         # retrying: still works
    _webhook(authed, "subscription.charged", rzp.set(sid, status="active"))
    authed.post("/api/subscription/cancel")
    assert plan_limits.check_generation(me())["reel"] is True         # cancelled, paid period still running
    _webhook(authed, "subscription.cancelled", rzp.set(sid, status="cancelled"))
    with pytest.raises(plan_limits.PlanLimit) as e:
        plan_limits.check_generation(me())
    assert e.value.code == "plan_required"
