"""Tests for subscription plans, GST quotes, Razorpay checkout/verify/webhook/cancel, taste, and cadence preferences.

Razorpay is never called: billing._call is replaced by a small in-memory fake (FakeRazorpay).
"""
from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src import billing, db
from src.db.models import User

KEY_SECRET, WEBHOOK_SECRET = "rzp_secret_test", "whsec_test"
SELLER = "27AAPFU0939F1ZV"                 # a well-formed GSTIN registered in Maharashtra (27)
DAY = 86400
_ids = itertools.count(1)


class FakeRazorpay:
    """Plans and subscriptions keyed by id (unique across tests); tests move subscriptions through their states."""

    def __init__(self):
        self.plans: dict[str, dict] = {}
        self.subs: dict[str, dict] = {}
        self.cancelled: list[tuple[str, int]] = []
        self.fail = False

    def __call__(self, method, path, data=None):
        if self.fail:
            raise billing.BillingError("payment_error", "HTTP 500")
        parts = path.strip("/").split("/")
        if method == "POST" and path == "/plans":
            pid = f"plan_{next(_ids)}"
            self.plans[pid] = {"id": pid, **data}
            return dict(self.plans[pid])
        if parts[0] == "plans":
            return dict(self.plans[parts[1]])
        if method == "POST" and path == "/subscriptions":
            sid = f"sub_{next(_ids)}"
            self.subs[sid] = {"id": sid, "status": "created", "plan_id": data["plan_id"], "notes": dict(data["notes"]),
                              "start_at": data.get("start_at"), "addons": data.get("addons"),
                              "total_count": data["total_count"], "current_start": None, "current_end": None,
                              "created_at": int(time.time()),
                              "charge_at": None}
            return dict(self.subs[sid])
        sub = self.subs[parts[1]]
        if path.endswith("/cancel"):
            self.cancelled.append((sub["id"], data["cancel_at_cycle_end"]))
            if not data["cancel_at_cycle_end"]:
                sub["status"] = "cancelled"
        return dict(sub)

    def authorise(self, sid: str) -> dict:
        """The customer completes Razorpay Checkout."""
        s = self.subs[sid]
        if s["start_at"]:                                  # future start: authenticated until then
            s.update(status="authenticated", charge_at=s["start_at"])
        else:
            now = int(time.time())
            end = billing.add_period(now, s["notes"]["interval"])
            s.update(status="active", current_start=now, current_end=end, charge_at=end)
        return dict(s)

    def set(self, sid: str, **changes) -> dict:
        self.subs[sid].update(changes)
        return dict(self.subs[sid])

    def amount(self, sid: str) -> int:
        return self.plans[self.subs[sid]["plan_id"]]["item"]["amount"]


@pytest.fixture(autouse=True)
def fresh_billing():
    """Every test starts from a free user with no subscription and no billing details (the test DB is shared)."""
    with db.session() as s:
        for u in s.scalars(select(User)):
            u.subscription_tier, u.subscription_status = "free", "active"
            u.razorpay_subscription_id = u.razorpay_pending_subscription_id = u.subscription_renews_at = None
            u.billing_name, u.billing_country, u.billing_state, u.billing_gstin = "", None, None, None
    db.set_setting("razorpay_plans", {})


@pytest.fixture()
def rzp(monkeypatch):
    for k, v in {"RAZORPAY_KEY_ID": "rzp_test_key", "RAZORPAY_KEY_SECRET": KEY_SECRET,
                 "RAZORPAY_WEBHOOK_SECRET": WEBHOOK_SECRET, "SELLER_GSTIN": SELLER}.items():
        monkeypatch.setenv(k, v)
    fake = FakeRazorpay()
    monkeypatch.setattr(billing, "_call", fake)
    return fake


def _tier(c) -> tuple[str, str]:
    s = c.get("/api/subscription/status").json()
    return s["tier"], s["status"]


def _details(c, country="IN", state="27", gstin=None):
    r = c.put("/api/subscription/billing-details", json={"name": "Test User", "country": country, "state": state,
                                                         "gstin": gstin})
    assert r.status_code == 200, r.text
    return r.json()


def _quote(c, plan, interval="month") -> dict:
    r = c.post("/api/subscription/quote", json={"plan_id": plan, "interval": interval})
    assert r.status_code == 200, r.text
    return r.json()


def _checkout(c, q) -> dict:
    r = c.post("/api/subscription/checkout", json={"plan_id": q["plan"], "interval": q["interval"],
                                                   "quote_at": q["quote_at"], "expected_total": q["total_now"]})
    assert r.status_code == 200, r.text
    return r.json()


def _sig(payment_id, sub_id) -> str:
    return hmac.new(KEY_SECRET.encode(), f"{payment_id}|{sub_id}".encode(), hashlib.sha256).hexdigest()


def _verify(c, sid):
    return c.post("/api/subscription/verify", json={"razorpay_payment_id": "pay_1", "razorpay_subscription_id": sid,
                                                    "razorpay_signature": _sig("pay_1", sid)})


def _webhook(client, event, sub, secret=WEBHOOK_SECRET):
    raw = json.dumps({"event": event, "payload": {"subscription": {"entity": sub}}}).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/subscription/razorpay/webhook", content=raw,
                       headers={"x-razorpay-signature": sig, "content-type": "application/json"})


def _subscribe(c, rzp, plan="creator", interval="month", elapsed: float = 0.5) -> str:
    """New subscription, paid; then pretend `elapsed` of its first period has passed."""
    sid = _checkout(c, _quote(c, plan, interval))["subscription_id"]
    rzp.authorise(sid)
    assert _verify(c, sid).json()["outcome"] == "activated"
    now = int(time.time())
    length = billing.add_period(now, interval) - now
    start = now - int(length * elapsed)
    rzp.set(sid, current_start=start, current_end=start + length, charge_at=start + length)
    return sid


# --------------------------------------------------------------------------- #
# GST arithmetic
# --------------------------------------------------------------------------- #
def test_gst_within_state_is_cgst_plus_sgst(monkeypatch):
    monkeypatch.setenv("SELLER_GSTIN", SELLER)
    t = billing.taxes(399900, "IN", "27")                       # Creator ₹3,999 to a Maharashtra customer
    assert [(x["name"], x["rate"], x["amount"]) for x in t] == [("CGST", 9, 35991), ("SGST", 9, 35991)]


def test_gst_across_states_is_igst(monkeypatch):
    monkeypatch.setenv("SELLER_GSTIN", SELLER)
    assert [(x["name"], x["amount"]) for x in billing.taxes(399900, "IN", "29")] == [("IGST", 71982)]


def test_gst_in_a_union_territory_is_utgst(monkeypatch):
    monkeypatch.setenv("SELLER_GSTIN", "04AAPFU0939F1ZV")       # seller in Chandigarh
    assert [x["name"] for x in billing.taxes(100000, "IN", "04")] == ["CGST", "UTGST"]


def test_no_gst_abroad_or_without_a_registration(monkeypatch):
    monkeypatch.setenv("SELLER_GSTIN", SELLER)
    assert billing.taxes(399900, "US", None) == []              # export of services
    monkeypatch.delenv("SELLER_GSTIN")
    assert billing.taxes(399900, "IN", "27") == []              # not registered: no GST may be charged


def test_gst_rounds_half_up_and_splits_odd_paise(monkeypatch):
    monkeypatch.setenv("SELLER_GSTIN", SELLER)
    t = billing.taxes(25, "IN", "27")                           # 18% of 25 paise = 4.5 -> 5
    assert sum(x["amount"] for x in t) == 5 and {x["amount"] for x in t} == {2, 3}


def test_gstin_validation():
    assert billing.valid_gstin("27AAPFU0939F1ZV", "27")
    assert not billing.valid_gstin("27AAPFU0939F1ZV", "29")      # registered in another state
    assert not billing.valid_gstin("27AAPFU0939F1Z")             # too short


def test_add_period_keeps_the_day_where_it_exists():
    jan31 = int(datetime(2027, 1, 31, 10, tzinfo=timezone.utc).timestamp())
    assert datetime.fromtimestamp(billing.add_period(jan31, "month"), timezone.utc).date().isoformat() == "2027-02-28"
    assert datetime.fromtimestamp(billing.add_period(jan31, "year"), timezone.utc).date().isoformat() == "2028-01-31"


# --------------------------------------------------------------------------- #
# Catalogue and billing details
# --------------------------------------------------------------------------- #
def test_public_subscription_plans(client, monkeypatch):
    monkeypatch.setenv("SELLER_GSTIN", SELLER)
    data = client.get("/api/subscription/plans").json()
    assert [p["id"] for p in data["plans"]] == ["lite", "starter", "creator", "pro"]
    by = {p["id"]: p for p in data["plans"]}
    assert [by[i]["price_inr_monthly"] for i in by] == [699, 1499, 2999, 5999]
    assert all(p["price_inr_yearly"] == 10 * p["price_inr_monthly"] for p in data["plans"])
    assert by["lite"]["quota"] == {"reels": 0, "carousels": 30} and by["lite"]["platforms"] == ["ig"]
    assert "yt" in by["starter"]["platforms"] and by["starter"]["quota"] == {"reels": 30, "carousels": 30}
    assert by["creator"]["popular"] is True
    assert data["currency"] == "INR" and data["gst"] == {"enabled": True, "rate": 18}
    assert len(client.get("/api/subscription/states").json()["states"]) == len(billing.STATES)


def test_billing_details_are_validated(authed):
    bad = lambda **b: authed.put("/api/subscription/billing-details", json={"country": "IN", **b}).json()["detail"]["code"]
    assert bad(state="99") == "bad_state"
    assert bad(state="29", gstin="27AAPFU0939F1ZV") == "bad_gstin"     # GSTIN from another state
    d = _details(authed, country="US", state="27", gstin="27AAPFU0939F1ZV")
    assert (d["country"], d["state"], d["gstin"]) == ("US", None, None)   # abroad: no state or GSTIN kept


def test_quote_needs_billing_details(authed, rzp):
    r = authed.post("/api/subscription/quote", json={"plan_id": "creator", "interval": "month"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "billing_details_required"


# --------------------------------------------------------------------------- #
# No gateway / gateway errors never change a plan
# --------------------------------------------------------------------------- #
def test_checkout_without_a_gateway_never_upgrades(authed, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("BILLING_DEV_INSTANT", raising=False)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "payments_unavailable"
    assert _tier(authed) == ("free", "active")


def test_dev_instant_is_ignored_on_a_deployment(authed, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")
    monkeypatch.setenv("SSM_PREFIX", "/codexone/")           # what every deployment sets
    assert authed.post("/api/subscription/checkout", json={"plan_id": "pro"}).status_code == 503
    assert _tier(authed) == ("free", "active")


def test_user_checkout_instant_activation_in_local_dev(authed, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")
    r = authed.post("/api/subscription/checkout", json={"plan_id": "creator", "interval": "month"})
    assert r.status_code == 200 and r.json()["mode"] == "instant" and _tier(authed) == ("creator", "active")


def test_gateway_error_never_upgrades(authed, rzp):
    _details(authed)
    q = _quote(authed, "pro")
    rzp.fail = True
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month",
                                                       "quote_at": q["quote_at"], "expected_total": q["total_now"]})
    assert r.status_code == 502 and _tier(authed) == ("free", "active")


# --------------------------------------------------------------------------- #
# New subscription: quote -> checkout -> verify
# --------------------------------------------------------------------------- #
def test_new_subscription_in_the_sellers_state_shows_cgst_and_sgst(authed, rzp):
    _details(authed, state="27")
    q = _quote(authed, "creator")
    assert q["kind"] == "new" and q["taxable"] == 299900
    assert [(t["name"], t["amount"]) for t in q["taxes"]] == [("CGST", 26991), ("SGST", 26991)]
    assert q["total_now"] == 353882 and q["renewal_total"] == 353882          # ₹3,538.82 incl. 18% GST
    assert _tier(authed) == ("free", "active") and not rzp.subs              # a quote charges nothing


def test_new_subscription_in_another_state_shows_igst(authed, rzp):
    _details(authed, state="29")
    assert [(t["name"], t["amount"]) for t in _quote(authed, "creator")["taxes"]] == [("IGST", 53982)]


def test_customer_abroad_pays_no_gst(authed, rzp):
    _details(authed, country="US")
    q = _quote(authed, "creator")
    assert q["taxes"] == [] and q["total_now"] == 299900 and q["gst_rate"] == 0


def test_checkout_charges_exactly_the_quote_and_the_plan_includes_gst(authed, rzp):
    _details(authed)
    q = _quote(authed, "creator")
    co = _checkout(authed, q)
    sub = rzp.subs[co["subscription_id"]]
    assert rzp.amount(co["subscription_id"]) == q["total_now"] == 353882     # Razorpay plan amount incl. GST
    assert sub["start_at"] is None and not sub["addons"] and sub["notes"]["change"] == "new"
    assert _tier(authed) == ("free", "active")                                # not paid yet
    rzp.authorise(co["subscription_id"])
    r = _verify(authed, co["subscription_id"]).json()
    assert (r["outcome"], r["tier"], r["status"]) == ("activated", "creator", "active") and r["renews_at"]


def test_a_changed_or_stale_quote_is_refused(authed, rzp):
    _details(authed)
    q = _quote(authed, "creator")
    body = {"plan_id": "creator", "interval": "month", "quote_at": q["quote_at"]}
    assert authed.post("/api/subscription/checkout", json={**body, "expected_total": 1}).json()["detail"]["code"] == "quote_changed"
    old = {**body, "quote_at": q["quote_at"] - 3600, "expected_total": q["total_now"]}
    assert authed.post("/api/subscription/checkout", json=old).json()["detail"]["code"] == "quote_expired"
    assert not rzp.subs


def test_verify_rejects_a_forged_signature_or_someone_elses_subscription(authed, rzp):
    _details(authed)
    sid = _checkout(authed, _quote(authed, "pro"))["subscription_id"]
    rzp.authorise(sid)
    r = authed.post("/api/subscription/verify", json={"razorpay_payment_id": "pay_1", "razorpay_subscription_id": sid,
                                                     "razorpay_signature": "0" * 64})
    assert r.status_code == 400
    other = rzp("POST", "/subscriptions", {"plan_id": rzp.subs[sid]["plan_id"], "total_count": 1,
                                            "notes": {"plan": "pro", "interval": "month", "change": "new"}})["id"]
    rzp.authorise(other)
    assert _verify(authed, other).status_code == 400 and _tier(authed) == ("free", "active")


def test_same_plan_is_refused(authed, rzp):
    _details(authed)
    _subscribe(authed, rzp, "creator")
    r = authed.post("/api/subscription/quote", json={"plan_id": "creator", "interval": "month"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "same_plan"


# --------------------------------------------------------------------------- #
# Prorated changes
# --------------------------------------------------------------------------- #
def test_upgrade_credits_the_unused_time_and_charges_the_difference_with_gst(authed, rzp):
    _details(authed, state="27")
    old = _subscribe(authed, rzp, "starter", elapsed=0.5)
    q = _quote(authed, "creator")
    assert q["kind"] == "upgrade"
    full, unused = q["lines"]
    assert full["amount"] == 299900 and -unused["amount"] == pytest.approx(149900 * 0.5, rel=0.02)
    assert q["taxable"] == full["amount"] + unused["amount"]
    assert q["total_now"] == q["taxable"] + sum(t["amount"] for t in q["taxes"])
    co = _checkout(authed, q)
    sub = rzp.subs[co["subscription_id"]]
    assert sub["addons"][0]["item"]["amount"] == q["total_now"]       # the prorated difference, charged upfront
    assert sub["start_at"] == q["renews_at"] and sub["notes"]["change"] == "upgrade"
    assert _tier(authed) == ("starter", "active") and rzp.cancelled == []   # nothing changes before payment
    r = _webhook(authed, "subscription.authenticated", rzp.authorise(co["subscription_id"])).json()
    assert r["outcome"] == "activated" and _tier(authed) == ("creator", "active")
    assert rzp.cancelled == [(old, 0)]                                # the old plan stops billing now
    # Razorpay's own event for the old subscription, and a repeat of the new one, change nothing more
    assert _webhook(authed, "subscription.cancelled", rzp.subs[old]).json()["outcome"] == "ignored"
    assert _webhook(authed, "subscription.authenticated", rzp.subs[co["subscription_id"]]).json()["outcome"] == "ignored"
    assert _tier(authed) == ("creator", "active")


def test_downgrade_waits_for_the_paid_period_and_charges_nothing_now(authed, rzp):
    _details(authed)
    old = _subscribe(authed, rzp, "pro", elapsed=0.1)
    q = _quote(authed, "starter")
    assert q["kind"] == "downgrade" and q["total_now"] == 0 and q["lines"] == []
    assert q["effective_at"] == rzp.subs[old]["current_end"]
    co = _checkout(authed, q)
    sub = rzp.subs[co["subscription_id"]]
    assert sub["start_at"] == q["effective_at"] and not sub["addons"]
    assert _webhook(authed, "subscription.authenticated", rzp.authorise(co["subscription_id"])).json()["outcome"] == "scheduled"
    assert _tier(authed) == ("pro", "changing") and rzp.cancelled == [(old, 1)]   # old ends at its cycle end
    blocked = authed.post("/api/subscription/quote", json={"plan_id": "creator", "interval": "month"})
    assert blocked.json()["detail"]["code"] == "change_scheduled"
    # the paid period ends: Razorpay ends the old subscription, then starts the new one
    assert _webhook(authed, "subscription.cancelled", rzp.set(old, status="cancelled")).json()["outcome"] == "activated"
    assert _tier(authed) == ("starter", "active")
    end = rzp.subs[old]["current_end"]
    new = rzp.set(co["subscription_id"], status="active", current_start=end, current_end=end + 30 * DAY)
    assert _webhook(authed, "subscription.activated", new).json()["outcome"] == "ignored"
    assert _tier(authed) == ("starter", "active")


def test_downgrade_also_works_when_the_new_subscription_starts_first(authed, rzp):
    _details(authed)
    old = _subscribe(authed, rzp, "pro", elapsed=0.1)
    co = _checkout(authed, _quote(authed, "starter"))
    _webhook(authed, "subscription.authenticated", rzp.authorise(co["subscription_id"]))
    assert _webhook(authed, "subscription.activated", rzp.set(co["subscription_id"], status="active")).json()["outcome"] == "activated"
    assert _webhook(authed, "subscription.cancelled", rzp.set(old, status="cancelled")).json()["outcome"] == "ignored"
    assert _tier(authed) == ("starter", "active")


def test_abandoned_checkout_leaves_the_plan_alone(authed, rzp):
    _details(authed)
    _subscribe(authed, rzp, "creator")
    co = _checkout(authed, _quote(authed, "pro"))
    _webhook(authed, "subscription.expired", rzp.set(co["subscription_id"], status="expired"))
    assert _tier(authed) == ("creator", "active")


# --------------------------------------------------------------------------- #
# Webhook lifecycle
# --------------------------------------------------------------------------- #
def test_webhook_rejects_a_bad_signature(authed, rzp):
    _details(authed)
    sid = _checkout(authed, _quote(authed, "pro"))["subscription_id"]
    assert _webhook(authed, "subscription.activated", rzp.authorise(sid), secret="wrong").status_code == 400
    assert _tier(authed) == ("free", "active")


def test_webhook_needs_no_session(authed, client, rzp):
    _details(authed)
    sid = _checkout(authed, _quote(authed, "pro"))["subscription_id"]
    client.headers.pop("X-CSRF-Token", None)
    client.cookies.clear()
    assert _webhook(client, "subscription.activated", rzp.authorise(sid)).json()["outcome"] == "activated"


def test_failed_renewals_then_halt_downgrade(authed, rzp):
    _details(authed)
    sid = _subscribe(authed, rzp, "creator")
    _webhook(authed, "subscription.pending", rzp.set(sid, status="pending"))
    assert _tier(authed) == ("creator", "past_due")            # Razorpay is retrying: access continues
    _webhook(authed, "subscription.charged", rzp.set(sid, status="active"))
    assert _tier(authed) == ("creator", "active")
    _webhook(authed, "subscription.halted", rzp.set(sid, status="halted"))
    assert _tier(authed) == ("free", "halted")


def test_cancel_runs_to_the_end_of_the_paid_period(authed, rzp):
    _details(authed)
    sid = _subscribe(authed, rzp, "creator")
    r = authed.post("/api/subscription/cancel").json()
    assert (r["tier"], r["status"]) == ("creator", "canceling") and rzp.cancelled == [(sid, 1)]
    _webhook(authed, "subscription.charged", rzp.subs[sid])    # a late event doesn't undo the scheduled end
    assert _tier(authed) == ("creator", "canceling")
    _webhook(authed, "subscription.cancelled", rzp.set(sid, status="cancelled"))
    st = authed.get("/api/subscription/status").json()
    assert (st["tier"], st["status"], st["has_subscription"]) == ("free", "canceled", False)
    assert authed.post("/api/subscription/cancel").status_code == 400


def test_webhook_for_an_unknown_subscription_is_ignored(authed, rzp):
    stray = rzp("POST", "/subscriptions", {"plan_id": "plan_x", "total_count": 1,
                                           "notes": {"plan": "pro", "interval": "month", "change": "new"}})
    assert _webhook(authed, "subscription.activated", rzp.authorise(stray["id"])).json()["outcome"] == "ignored"
    assert _tier(authed) == ("free", "active")


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
