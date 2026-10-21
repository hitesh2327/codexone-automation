"""Tests for subscription plans, Razorpay checkout/verify/webhook/cancel, taste, and cadence preferences.

Razorpay is never called: billing._call is replaced by a small in-memory fake (FakeRazorpay).
"""
from __future__ import annotations

import hashlib
import hmac
import itertools
import json

import pytest
from sqlalchemy import select

from src import billing, db
from src.db.models import User

KEY_SECRET, WEBHOOK_SECRET = "rzp_secret_test", "whsec_test"
RZP_PLANS = {"STARTER": "plan_S", "CREATOR": "plan_C", "PRO": "plan_P"}


_ids = itertools.count(1)


class FakeRazorpay:
    """Subscriptions keyed by id (unique across tests); tests move them through Razorpay's states."""

    def __init__(self):
        self.subs: dict[str, dict] = {}
        self.cancelled: list[tuple[str, int]] = []
        self.fail = False

    def __call__(self, method, path, **kw):
        if self.fail:
            raise billing.BillingError("payment_error", "HTTP 500")
        if method == "POST" and path == "/subscriptions":
            sid = f"sub_{next(_ids)}"
            self.subs[sid] = {"id": sid, "status": "created", "plan_id": kw["json"]["plan_id"], "current_end": None}
            return dict(self.subs[sid])
        sid = path.split("/")[2]
        if path.endswith("/cancel"):
            self.cancelled.append((sid, kw["json"]["cancel_at_cycle_end"]))
            return dict(self.subs[sid])
        return dict(self.subs[sid])

    def set(self, sid, status, **extra):
        self.subs[sid].update(status=status, current_end=1893456000 if status == "active" else None, **extra)
        return dict(self.subs[sid])


@pytest.fixture(autouse=True)
def fresh_billing():
    """Every test starts from a free user with no Razorpay subscription (the test DB is shared)."""
    with db.session() as s:
        for u in s.scalars(select(User)):
            u.subscription_tier, u.subscription_status = "free", "active"
            u.razorpay_subscription_id = u.razorpay_pending_subscription_id = u.subscription_renews_at = None


@pytest.fixture()
def rzp(monkeypatch):
    for k, v in {"RAZORPAY_KEY_ID": "rzp_test_key", "RAZORPAY_KEY_SECRET": KEY_SECRET,
                 "RAZORPAY_WEBHOOK_SECRET": WEBHOOK_SECRET}.items():
        monkeypatch.setenv(k, v)
    for plan, pid in RZP_PLANS.items():
        monkeypatch.setenv(f"RAZORPAY_PLAN_{plan}_MONTH", pid)
    fake = FakeRazorpay()
    monkeypatch.setattr(billing, "_call", fake)
    return fake


def _tier(c) -> tuple[str, str]:
    s = c.get("/api/subscription/status").json()
    return s["tier"], s["status"]


def _pay_sig(payment_id, sub_id) -> str:
    return hmac.new(KEY_SECRET.encode(), f"{payment_id}|{sub_id}".encode(), hashlib.sha256).hexdigest()


def _webhook(client, event, sub, secret=WEBHOOK_SECRET):
    raw = json.dumps({"event": event, "payload": {"subscription": {"entity": sub}}}).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/subscription/razorpay/webhook", content=raw,
                       headers={"x-razorpay-signature": sig, "content-type": "application/json"})


def _subscribe(authed, rzp, plan="creator") -> str:
    """Checkout + activation webhook: the user ends up on `plan` with a current subscription."""
    sid = authed.post("/api/subscription/checkout", json={"plan_id": plan, "interval": "month"}).json()["subscription_id"]
    assert _webhook(authed, "subscription.activated", rzp.set(sid, "active")).json()["outcome"] == "activated"
    return sid


# --------------------------------------------------------------------------- #
# Catalogue and status
# --------------------------------------------------------------------------- #
def test_public_subscription_plans(client):
    r = client.get("/api/subscription/plans")
    assert r.status_code == 200
    data = r.json()
    assert len(data["plans"]) >= 3
    starter = next(p for p in data["plans"] if p["id"] == "starter")
    creator = next(p for p in data["plans"] if p["id"] == "creator")
    pro = next(p for p in data["plans"] if p["id"] == "pro")
    assert starter["price_monthly"] == 19
    assert creator["popular"] is True
    assert pro["posts_per_day"] == 4
    assert "payments_enabled" in data and "stripe_publishable_key" not in data


def test_user_subscription_status(authed):
    data = authed.get("/api/subscription/status").json()
    assert {"tier", "status", "renews_at", "has_subscription", "payments_enabled"} <= set(data)


# --------------------------------------------------------------------------- #
# No gateway / gateway errors never change a plan
# --------------------------------------------------------------------------- #
def test_checkout_without_a_gateway_never_upgrades(authed, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("BILLING_DEV_INSTANT", raising=False)
    before = _tier(authed)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "payments_unavailable"
    assert _tier(authed) == before


def test_dev_instant_is_ignored_on_a_deployment(authed, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")
    monkeypatch.setenv("SSM_PREFIX", "/codexone/")           # what every deployment sets
    before = _tier(authed)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"})
    assert r.status_code == 503
    assert _tier(authed) == before


def test_gateway_error_never_upgrades(authed, rzp, monkeypatch):
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")         # even with dev activation allowed
    rzp.fail = True
    before = _tier(authed)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "payment_error"
    assert _tier(authed) == before


def test_plan_without_a_razorpay_plan_id_cant_be_bought(authed, rzp, monkeypatch):
    monkeypatch.delenv("RAZORPAY_PLAN_PRO_MONTH")
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"})
    assert r.status_code == 503 and not rzp.subs


def test_user_checkout_instant_activation_in_local_dev(authed, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")
    r = authed.post("/api/subscription/checkout", json={"plan_id": "creator", "interval": "month"})
    assert r.status_code == 200 and r.json()["mode"] == "instant"
    assert _tier(authed) == ("creator", "active")


# --------------------------------------------------------------------------- #
# Razorpay checkout and the signed callback
# --------------------------------------------------------------------------- #
def test_checkout_starts_a_subscription_without_changing_the_plan(authed, rzp):
    before = _tier(authed)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "creator", "interval": "month"}).json()
    assert r["mode"] == "razorpay" and r["key_id"] == "rzp_test_key" and r["subscription_id"] in rzp.subs
    assert rzp.subs[r["subscription_id"]]["plan_id"] == "plan_C"
    assert _tier(authed) == before                          # nothing changes until Razorpay confirms payment


def test_verify_rejects_a_forged_signature(authed, rzp):
    sid = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"}).json()["subscription_id"]
    rzp.set(sid, "active")
    before = _tier(authed)
    r = authed.post("/api/subscription/verify", json={"razorpay_payment_id": "pay_1", "razorpay_subscription_id": sid,
                                                     "razorpay_signature": "0" * 64})
    assert r.status_code == 400 and _tier(authed) == before


def test_verify_activates_from_what_razorpay_reports(authed, rzp):
    sid = authed.post("/api/subscription/checkout", json={"plan_id": "creator", "interval": "month"}).json()["subscription_id"]
    rzp.set(sid, "active")
    r = authed.post("/api/subscription/verify", json={"razorpay_payment_id": "pay_1", "razorpay_subscription_id": sid,
                                                     "razorpay_signature": _pay_sig("pay_1", sid)})
    assert r.status_code == 200 and r.json()["outcome"] == "activated"
    st = authed.get("/api/subscription/status").json()
    assert (st["tier"], st["status"], st["has_subscription"]) == ("creator", "active", True) and st["renews_at"]


def test_verify_only_for_this_accounts_subscription(authed, rzp):
    other = rzp(  # a subscription some other checkout created
        "POST", "/subscriptions", json={"plan_id": "plan_P"})["id"]
    rzp.set(other, "active")
    r = authed.post("/api/subscription/verify", json={"razorpay_payment_id": "pay_9", "razorpay_subscription_id": other,
                                                     "razorpay_signature": _pay_sig("pay_9", other)})
    assert r.status_code == 400 and _tier(authed)[0] != "pro"


def test_verify_before_the_first_charge_settles_changes_nothing(authed, rzp):
    sid = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"}).json()["subscription_id"]
    before = _tier(authed)
    rzp.set(sid, "authenticated")
    r = authed.post("/api/subscription/verify", json={"razorpay_payment_id": "pay_1", "razorpay_subscription_id": sid,
                                                     "razorpay_signature": _pay_sig("pay_1", sid)})
    assert r.json()["outcome"] == "ignored" and _tier(authed) == before
    assert _webhook(authed, "subscription.activated", rzp.set(sid, "active")).json()["outcome"] == "activated"
    assert _tier(authed) == ("pro", "active")


# --------------------------------------------------------------------------- #
# Webhook: the lifecycle after checkout
# --------------------------------------------------------------------------- #
def test_webhook_rejects_a_bad_signature(authed, rzp):
    sid = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"}).json()["subscription_id"]
    before = _tier(authed)
    r = _webhook(authed, "subscription.activated", rzp.set(sid, "active"), secret="wrong")
    assert r.status_code == 400 and _tier(authed) == before


def test_webhook_needs_no_session(authed, client, rzp):
    sid = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"}).json()["subscription_id"]
    client.headers.pop("X-CSRF-Token", None)
    client.cookies.clear()
    assert _webhook(client, "subscription.activated", rzp.set(sid, "active")).status_code == 200


def test_failed_renewals_then_halt_downgrade(authed, rzp):
    sid = _subscribe(authed, rzp, "creator")
    _webhook(authed, "subscription.pending", rzp.set(sid, "pending"))
    assert _tier(authed) == ("creator", "past_due")          # Razorpay is retrying: access continues
    _webhook(authed, "subscription.charged", rzp.set(sid, "active"))
    assert _tier(authed) == ("creator", "active")
    _webhook(authed, "subscription.halted", rzp.set(sid, "halted"))
    assert _tier(authed) == ("free", "halted")


def test_cancel_runs_to_the_end_of_the_paid_period(authed, rzp):
    sid = _subscribe(authed, rzp, "creator")
    r = authed.post("/api/subscription/cancel").json()
    assert r["status"] == "canceling" and r["tier"] == "creator" and rzp.cancelled == [(sid, 1)]
    _webhook(authed, "subscription.cancelled", rzp.set(sid, "cancelled"))
    st = authed.get("/api/subscription/status").json()
    assert (st["tier"], st["status"], st["has_subscription"]) == ("free", "canceled", False)
    assert authed.post("/api/subscription/cancel").status_code == 400   # nothing left to cancel


def test_switching_plans_cancels_the_old_subscription_only_once_the_new_one_is_paid(authed, rzp):
    old = _subscribe(authed, rzp, "creator")
    new = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"}).json()["subscription_id"]
    assert _tier(authed) == ("creator", "active") and rzp.cancelled == []   # unpaid switch: old plan untouched
    _webhook(authed, "subscription.activated", rzp.set(new, "active"))
    assert _tier(authed) == ("pro", "active") and rzp.cancelled == [(old, 0)]
    # the old subscription's own cancellation event must not downgrade the new plan
    assert _webhook(authed, "subscription.cancelled", rzp.set(old, "cancelled")).json()["outcome"] == "ignored"
    assert _tier(authed) == ("pro", "active")


def test_abandoned_switch_leaves_the_plan_alone(authed, rzp):
    _subscribe(authed, rzp, "creator")
    new = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"}).json()["subscription_id"]
    _webhook(authed, "subscription.cancelled", rzp.set(new, "cancelled"))
    assert _tier(authed) == ("creator", "active")


def test_webhook_for_an_unknown_subscription_is_ignored(authed, rzp):
    stray = rzp("POST", "/subscriptions", json={"plan_id": "plan_P"})["id"]
    before = _tier(authed)
    assert _webhook(authed, "subscription.activated", rzp.set(stray, "active")).json()["outcome"] == "ignored"
    assert _tier(authed) == before


# --------------------------------------------------------------------------- #
# Taste and cadence
# --------------------------------------------------------------------------- #
def test_user_taste_and_cadence_patch(authed):
    taste_payload = {
        "niche": "AI Tools & Automation",
        "tone": "Punchy & High Energy",
        "aesthetic": "Dark Minimalist Luxury",
        "target_audience": "Tech Founders & Engineers",
        "prompt_instructions": "Focus on ROI and automation pipelines.",
        "default_targets": ["ig", "yt"],
    }
    cadence_payload = {
        "posts_per_day": 3,
        "slots": ["09:00", "15:00", "21:00"],
    }

    r = authed.patch(
        "/api/profile",
        json={
            "taste": taste_payload,
            "cadence": cadence_payload,
            "config_completed": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["taste"]["niche"] == "AI Tools & Automation"
    assert data["taste"]["default_targets"] == ["ig", "yt"]
    assert data["cadence"]["posts_per_day"] == 3
    assert data["cadence"]["slots"] == ["09:00", "15:00", "21:00"]
    assert data["config_completed"] is True
