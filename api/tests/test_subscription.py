"""Tests for subscription plans, Stripe checkout/verify/webhook/cancel, taste, and cadence preferences.

Stripe is never called: billing._call is replaced by a small in-memory fake (FakeStripe).
"""
from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import time

import pytest
from sqlalchemy import select

from src import billing, db
from src.db.models import User

WEBHOOK_SECRET = "whsec_test"
_ids = itertools.count(1)


class FakeStripe:
    """Checkout sessions and subscriptions keyed by id (unique across tests)."""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.subs: dict[str, dict] = {}
        self.prices: dict[str, dict] = {}       # id -> {"id", "unit_amount", "lookup_key", "recurring"}
        self.calls: list[tuple[str, str, dict | None]] = []
        self.fail = False
        self.decline = False

    def __call__(self, method, path, data=None):
        self.calls.append((method, path, data))
        if self.fail:
            raise billing.BillingError("payment_error", "HTTP 500")
        parts = path.strip("/").split("/")
        if path == "/prices":
            if method == "GET":
                return {"data": [p for p in self.prices.values() if p["lookup_key"] in data["lookup_keys"]]}
            pid = f"price_{next(_ids)}"
            self.prices[pid] = {"id": pid, "unit_amount": data["unit_amount"], "lookup_key": data["lookup_key"],
                                "recurring": data["recurring"]}
            return dict(self.prices[pid])
        if path == "/invoices/create_preview":
            sub = self.subs[data["subscription"]]
            new = self.prices[data["subscription_details"]["items"][0]["price"]]["unit_amount"]
            total = new - sub["items"]["data"][0]["price"]["unit_amount"]   # "unused time" = the whole old price
            return {"amount_due": max(0, total), "total": total, "currency": "usd"}
        if method == "POST" and path == "/checkout/sessions":
            sid = f"cs_test_{next(_ids)}"
            self.sessions[sid] = {"id": sid, "url": f"https://checkout.stripe.com/c/{sid}", "mode": "subscription",
                                  "status": "open", "subscription": None, "data": data,
                                  "client_reference_id": data["client_reference_id"]}
            return dict(self.sessions[sid])
        if parts[0] == "checkout":
            if parts[2] not in self.sessions:
                raise billing.BillingError("payment_error", "HTTP 404")
            return dict(self.sessions[parts[2]])
        sub = self.subs[parts[1]]
        if method == "DELETE":
            sub["status"] = "canceled"
        elif method == "POST" and "items" in (data or {}):       # in-place switch
            if self.decline:
                raise billing.BillingError("card_declined", "HTTP 402")
            assert data["proration_behavior"] == "always_invoice" and data["payment_behavior"] == "error_if_incomplete"
            sub["items"]["data"][0]["price"] = dict(self.prices[data["items"][0]["price"]])
            sub["metadata"].update(data["metadata"])
            sub["cancel_at_period_end"] = False
        elif method == "POST":
            sub["cancel_at_period_end"] = True
        return dict(sub)

    def pay(self, session_id: str, status: str = "active") -> dict:
        """The customer completes Checkout: Stripe creates the subscription with our metadata."""
        s = self.sessions[session_id]
        meta = s["data"]["metadata"]
        sub_id = f"sub_{next(_ids)}"
        price = dict(self.prices[s["data"]["line_items"][0]["price"]])
        self.subs[sub_id] = {"id": sub_id, "status": status, "metadata": dict(meta), "customer": "cus_1",
                             "created": int(time.time()) + next(_ids), "cancel_at_period_end": False,
                             "items": {"data": [{"id": f"si_{next(_ids)}", "price": price,
                                                 "current_period_end": 1893456000}]}}
        s.update(status="complete", subscription=sub_id)
        return dict(self.subs[sub_id])

    def set(self, sub_id: str, **changes) -> dict:
        self.subs[sub_id].update(changes)
        return dict(self.subs[sub_id])


@pytest.fixture(autouse=True)
def fresh_billing():
    """Every test starts from a free user with no subscription (the test DB is shared)."""
    with db.session() as s:
        for u in s.scalars(select(User)):
            u.subscription_tier, u.subscription_status = "free", "active"
            u.stripe_subscription_id = u.stripe_customer_id = u.subscription_renews_at = None


@pytest.fixture()
def stripe(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    fake = FakeStripe()
    monkeypatch.setattr(billing, "_call", fake)
    return fake


def _tier(c) -> tuple[str, str]:
    s = c.get("/api/subscription/status").json()
    return s["tier"], s["status"]


def _signed(raw: bytes, secret: str = WEBHOOK_SECRET, t: int | None = None) -> str:
    t = int(time.time()) if t is None else t
    return f"t={t},v1=" + hmac.new(secret.encode(), f"{t}.".encode() + raw, hashlib.sha256).hexdigest()


def _webhook(client, kind, obj, secret=WEBHOOK_SECRET, t=None):
    raw = json.dumps({"id": f"evt_{next(_ids)}", "type": kind, "data": {"object": obj}}).encode()
    return client.post("/api/subscription/stripe/webhook", content=raw,
                       headers={"stripe-signature": _signed(raw, secret, t), "content-type": "application/json"})


def _checkout(authed, plan="creator", interval="month") -> str:
    r = authed.post("/api/subscription/checkout", json={"plan_id": plan, "interval": interval})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _subscribe(authed, stripe, plan="creator") -> str:
    """Checkout, pay, and come back: the user ends up on `plan`."""
    cs = _checkout(authed, plan)
    sub = stripe.pay(cs)
    assert authed.post("/api/subscription/verify", json={"session_id": cs}).json()["outcome"] == "activated"
    return sub["id"]


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
    assert "payments_enabled" in data


def test_user_subscription_status(authed):
    data = authed.get("/api/subscription/status").json()
    assert {"tier", "status", "renews_at", "has_subscription", "payments_enabled"} <= set(data)


# --------------------------------------------------------------------------- #
# No gateway / gateway errors never change a plan
# --------------------------------------------------------------------------- #
def test_checkout_without_a_gateway_never_upgrades(authed, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("BILLING_DEV_INSTANT", raising=False)
    before = _tier(authed)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "payments_unavailable"
    assert _tier(authed) == before


def test_dev_instant_is_ignored_on_a_deployment(authed, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")
    monkeypatch.setenv("SSM_PREFIX", "/codexone/")           # what every deployment sets
    before = _tier(authed)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"})
    assert r.status_code == 503
    assert _tier(authed) == before


def test_gateway_error_never_upgrades(authed, stripe, monkeypatch):
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")         # even with dev activation allowed
    stripe.fail = True
    before = _tier(authed)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "payment_error"
    assert _tier(authed) == before


def test_user_checkout_instant_activation_in_local_dev(authed, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")
    r = authed.post("/api/subscription/checkout", json={"plan_id": "creator", "interval": "month"})
    assert r.status_code == 200 and r.json()["mode"] == "instant"
    assert _tier(authed) == ("creator", "active")


# --------------------------------------------------------------------------- #
# Checkout and the return from Stripe
# --------------------------------------------------------------------------- #
def test_checkout_sends_the_browser_to_stripe_without_changing_the_plan(authed, stripe):
    before = _tier(authed)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "creator", "interval": "year"}).json()
    assert r["mode"] == "stripe" and r["url"].startswith("https://checkout.stripe.com/")
    sent = stripe.sessions[r["session_id"]]["data"]
    assert sent["mode"] == "subscription" and sent["metadata"]["plan"] == "creator"
    price = stripe.prices[sent["line_items"][0]["price"]]
    assert price["unit_amount"] == 49000 and price["recurring"] == {"interval": "year"}   # $490/yr in cents
    authed.post("/api/subscription/checkout", json={"plan_id": "creator", "interval": "year"})
    assert len(stripe.prices) == 1                            # the Stripe price is reused, not made per checkout
    assert "{CHECKOUT_SESSION_ID}" in sent["success_url"]
    assert _tier(authed) == before                          # nothing changes until Stripe confirms payment


def test_return_from_stripe_activates_from_what_stripe_reports(authed, stripe):
    _subscribe(authed, stripe, "creator")
    st = authed.get("/api/subscription/status").json()
    assert (st["tier"], st["status"], st["has_subscription"]) == ("creator", "active", True) and st["renews_at"]


def test_return_before_paying_changes_nothing(authed, stripe):
    cs = _checkout(authed, "pro")
    before = _tier(authed)
    r = authed.post("/api/subscription/verify", json={"session_id": cs}).json()
    assert r["outcome"] == "ignored" and r["pending"] is True and _tier(authed) == before


def test_another_accounts_checkout_cant_be_claimed(authed, stripe):
    cs = _checkout(authed, "pro")
    stripe.pay(cs)
    stripe.sessions[cs]["client_reference_id"] = "999999"      # as if it were someone else's
    before = _tier(authed)
    r = authed.post("/api/subscription/verify", json={"session_id": cs})
    assert r.status_code == 400 and _tier(authed) == before


def test_unknown_session_is_rejected(authed, stripe):
    r = authed.post("/api/subscription/verify", json={"session_id": "cs_test_nope"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_session"


def test_first_charge_still_processing_waits_for_the_webhook(authed, stripe):
    cs = _checkout(authed, "pro")
    sub = stripe.pay(cs, status="incomplete")
    before = _tier(authed)
    assert authed.post("/api/subscription/verify", json={"session_id": cs}).json()["pending"] is True
    assert _tier(authed) == before
    assert _webhook(authed, "customer.subscription.updated", stripe.set(sub["id"], status="active")).json()["outcome"] == "activated"
    assert _tier(authed) == ("pro", "active")


# --------------------------------------------------------------------------- #
# Webhook: signatures and the lifecycle after checkout
# --------------------------------------------------------------------------- #
def test_webhook_rejects_a_bad_signature(authed, stripe):
    cs = _checkout(authed, "pro")
    sub = stripe.pay(cs)
    before = _tier(authed)
    assert _webhook(authed, "customer.subscription.updated", sub, secret="whsec_wrong").status_code == 400
    assert _tier(authed) == before


def test_webhook_rejects_a_replayed_old_event(authed, stripe):
    cs = _checkout(authed, "pro")
    sub = stripe.pay(cs)
    before = _tier(authed)
    assert _webhook(authed, "customer.subscription.updated", sub, t=int(time.time()) - 3600).status_code == 400
    assert _tier(authed) == before


def test_checkout_completed_webhook_activates_without_the_browser(authed, client, stripe):
    cs = _checkout(authed, "creator")
    stripe.pay(cs)
    client.headers.pop("X-CSRF-Token", None)
    client.cookies.clear()                                    # Stripe calls without a session
    r = _webhook(client, "checkout.session.completed", stripe.sessions[cs])
    assert r.status_code == 200 and r.json()["outcome"] == "activated"


def test_failed_renewals_then_unpaid_downgrade(authed, stripe):
    sid = _subscribe(authed, stripe, "creator")
    _webhook(authed, "customer.subscription.updated", stripe.set(sid, status="past_due"))
    assert _tier(authed) == ("creator", "past_due")           # Stripe is retrying: access continues
    _webhook(authed, "customer.subscription.updated", stripe.set(sid, status="active"))
    assert _tier(authed) == ("creator", "active")
    _webhook(authed, "customer.subscription.updated", stripe.set(sid, status="unpaid"))
    assert _tier(authed) == ("free", "halted")


def test_cancel_runs_to_the_end_of_the_paid_period(authed, stripe):
    sid = _subscribe(authed, stripe, "creator")
    r = authed.post("/api/subscription/cancel").json()
    assert (r["tier"], r["status"]) == ("creator", "canceling") and r["renews_at"]
    assert ("POST", f"/subscriptions/{sid}", {"cancel_at_period_end": True}) in stripe.calls
    _webhook(authed, "customer.subscription.deleted", stripe.set(sid, status="canceled"))
    st = authed.get("/api/subscription/status").json()
    assert (st["tier"], st["status"], st["has_subscription"]) == ("free", "canceled", False)
    assert authed.post("/api/subscription/cancel").status_code == 400   # nothing left to cancel


def _quote(authed, plan, interval="month") -> dict:
    r = authed.post("/api/subscription/checkout", json={"plan_id": plan, "interval": interval})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["mode"] == "switch"
    return q


def _switch(authed, plan, q, interval="month"):
    return authed.post("/api/subscription/switch", json={"plan_id": plan, "interval": interval,
                                                         "proration_date": q["proration_date"]})


def test_upgrade_while_subscribed_is_quoted_first_and_charges_only_the_difference(authed, stripe):
    sid = _subscribe(authed, stripe, "starter")
    n_sessions = len(stripe.sessions)
    q = _quote(authed, "creator")
    assert (q["charge_now"], q["credit"]) == (3000, 0)          # $49 - $19: the difference, not the full price
    assert len(stripe.sessions) == n_sessions and _tier(authed) == ("starter", "active")   # a quote changes nothing
    r = _switch(authed, "creator", q).json()
    assert (r["tier"], r["status"]) == ("creator", "active")
    assert stripe.subs[sid]["metadata"]["plan"] == "creator"    # same subscription, changed in place
    assert len(stripe.subs) == 1 and not any(m == "DELETE" for m, _, _ in stripe.calls)
    # Stripe's customer.subscription.updated for the same change: nothing more to do, nothing logged twice
    assert _webhook(authed, "customer.subscription.updated", stripe.subs[sid]).json()["outcome"] == "ignored"


def test_downgrade_while_subscribed_credits_the_unused_time(authed, stripe):
    _subscribe(authed, stripe, "pro")
    q = _quote(authed, "starter")
    assert q["charge_now"] == 0 and q["credit"] == 8000         # $99 - $19 back as credit
    assert _switch(authed, "starter", q).json()["tier"] == "starter"


def test_switching_to_the_same_plan_is_refused(authed, stripe):
    _subscribe(authed, stripe, "creator")
    r = authed.post("/api/subscription/checkout", json={"plan_id": "creator", "interval": "month"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "same_plan"


def test_declined_card_on_switch_changes_nothing(authed, stripe):
    sid = _subscribe(authed, stripe, "starter")
    q = _quote(authed, "pro")
    stripe.decline = True
    r = _switch(authed, "pro", q)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "card_declined"
    assert _tier(authed) == ("starter", "active") and stripe.subs[sid]["metadata"]["plan"] == "starter"


def test_an_old_quote_cant_be_used(authed, stripe):
    _subscribe(authed, stripe, "starter")
    q = _quote(authed, "pro")
    q["proration_date"] -= 3600
    assert _switch(authed, "pro", q).status_code == 409 and _tier(authed)[0] == "starter"


def test_switch_without_a_subscription_is_refused(authed, stripe):
    r = authed.post("/api/subscription/switch", json={"plan_id": "pro", "interval": "month",
                                                       "proration_date": int(time.time())})
    assert r.status_code == 409 and _tier(authed) == ("free", "active")


def test_after_payment_failure_a_new_checkout_replaces_the_dead_subscription(authed, stripe):
    old = _subscribe(authed, stripe, "creator")
    _webhook(authed, "customer.subscription.updated", stripe.set(old, status="unpaid"))
    assert _tier(authed) == ("free", "halted")
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"}).json()
    assert r["mode"] == "stripe"                               # not switchable in place: a fresh Checkout
    stripe.pay(r["session_id"])
    assert authed.post("/api/subscription/verify", json={"session_id": r["session_id"]}).json()["outcome"] == "activated"
    assert _tier(authed) == ("pro", "active") and ("DELETE", f"/subscriptions/{old}", None) in stripe.calls
    # a late event from the replaced subscription can't take over or downgrade
    assert _webhook(authed, "customer.subscription.updated", stripe.set(old, status="active")).json()["outcome"] == "ignored"
    assert _webhook(authed, "customer.subscription.deleted", stripe.set(old, status="canceled")).json()["outcome"] == "ignored"
    assert _tier(authed) == ("pro", "active")


def test_webhook_for_someone_elses_subscription_is_ignored(authed, stripe):
    cs = _checkout(authed, "pro")
    sub = stripe.pay(cs)
    stripe.set(sub["id"], metadata={"user_id": "999999", "plan": "pro", "interval": "month"})
    before = _tier(authed)
    assert _webhook(authed, "customer.subscription.updated", stripe.subs[sub["id"]]).json()["outcome"] == "ignored"
    assert _tier(authed) == before


def test_signature_check_matches_stripes_scheme():
    import os
    os.environ["STRIPE_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    try:
        body, t = b'{"id":"evt_1"}', 1_700_000_000
        good = hmac.new(WEBHOOK_SECRET.encode(), b"1700000000." + body, hashlib.sha256).hexdigest()
        assert billing.webhook_event_ok(body, f"t={t},v1=deadbeef,v1={good}", now=t + 10)   # any v1 may match
        assert not billing.webhook_event_ok(body + b" ", f"t={t},v1={good}", now=t + 10)     # body tampered
        assert not billing.webhook_event_ok(body, f"t={t},v1={good}", now=t + 301)           # too old
        assert not billing.webhook_event_ok(body, "garbage", now=t)
    finally:
        del os.environ["STRIPE_WEBHOOK_SECRET"]


def test_stripe_form_encoding():
    assert billing._form({"a": {"b": 1}, "c": [{"d": True}], "e": None}) == {"a[b]": "1", "c[0][d]": "true"}


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
