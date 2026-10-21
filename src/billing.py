"""Razorpay subscriptions with Indian GST and prorated plan changes.

    from src import billing
    q = billing.quote(user, plan, "month", now)        # what changing to `plan` costs: lines, GST, total now
    sub = billing.start(user, plan, "month", q)         # a Razorpay subscription the browser then authorises
    billing.apply(user, billing.fetch_subscription(id)) # a confirmed subscription sets the user's plan

Server settings (environment; on AWS they come from SSM /codexone/, see infra/put_secrets.py):
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET   API keys (rzp_test_... while testing)
    RAZORPAY_WEBHOOK_SECRET                secret typed when creating the webhook in the Razorpay dashboard
    SELLER_GSTIN                           your 15-character GSTIN; until it is set no GST is charged at all

Money is in paise (integers) everywhere. Prices in PLANS are before GST. With SELLER_GSTIN set, Indian customers
pay 18% GST on top: CGST 9% + SGST 9% (UTGST in union territories without a legislature) when their state is the
seller's, IGST 18% otherwise. Customers outside India pay no GST (an export of services).

A plan changes only from a subscription Razorpay itself reports: fetched with our key after the signed checkout
callback, or delivered by a webhook whose signature checks out. Razorpay can't change the plan of a UPI or
e-mandate subscription in place, so every change is a new subscription:
- new:       starts now; the first charge is the plan's price.
- upgrade:   the new plan starts now. The unused time on the current plan is credited against it and the
             difference is charged once, upfront, when the customer authorises the new subscription; its regular
             charges begin one full period later. The old subscription is cancelled once that payment succeeds.
- downgrade: the unused time is worth more than the new plan's period, so the change waits for the end of the
             period already paid for: nothing is charged now, the new subscription starts on that date and the
             old one is cancelled at the end of its cycle. Nothing paid is lost and nothing needs refunding.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import logging
import os
import re
from datetime import datetime, timezone

import requests

log = logging.getLogger("codexone.billing")

API = "https://api.razorpay.com/v1"
CURRENCY = "INR"
GST_RATE = 18
TOTAL_COUNT = {"month": 120, "year": 10}       # Razorpay needs a finite number of cycles: about 10 years
PERIOD = {"month": "monthly", "year": "yearly"}

# GST state codes (the first two digits of a GSTIN)
STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}
UNION_TERRITORIES = {"04", "26", "31", "35", "38"}   # no legislature: UTGST instead of SGST
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

# Razorpay subscription status -> (our status, keeps the paid plan?)
_STATUS = {
    "active": ("active", True),
    "pending": ("past_due", True),        # a renewal failed; Razorpay retries, access continues meanwhile
    "halted": ("halted", False),          # every retry failed
    "paused": ("paused", False),
    "cancelled": ("canceled", False),
    "completed": ("canceled", False),
    "expired": ("canceled", False),
}
_ENDED = ("cancelled", "completed", "expired")


class BillingError(Exception):
    """`code`: payments_unavailable | payment_error."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def key_id() -> str:
    return _env("RAZORPAY_KEY_ID")


def configured() -> bool:
    return bool(key_id() and _env("RAZORPAY_KEY_SECRET"))


# --------------------------------------------------------------------------- #
# GST
# --------------------------------------------------------------------------- #
def seller_gstin() -> str | None:
    g = _env("SELLER_GSTIN").upper()
    return g if GSTIN_RE.match(g) and g[:2] in STATES else None


def gst_enabled() -> bool:
    return seller_gstin() is not None


def valid_gstin(gstin: str, state: str | None = None) -> bool:
    g = (gstin or "").strip().upper()
    return bool(GSTIN_RE.match(g)) and g[:2] in STATES and (state is None or g[:2] == state)


def gst_rate(country: str | None) -> int:
    """GST % an order is charged: 18 for an Indian customer when the seller is registered, else 0."""
    return GST_RATE if gst_enabled() and (country or "").upper() == "IN" else 0


def taxes(taxable: int, country: str | None, state: str | None) -> list[dict]:
    """The GST lines on `taxable` paise: CGST + SGST/UTGST within the seller's state, IGST across states."""
    rate = gst_rate(country)
    if not rate or taxable <= 0:
        return []
    total = (taxable * rate + 50) // 100                     # rounded half up to the paisa
    seller_state = seller_gstin()[:2]
    if state == seller_state:
        half = total // 2
        local = "UTGST" if seller_state in UNION_TERRITORIES else "SGST"
        return [{"name": "CGST", "rate": rate / 2, "amount": half},
                {"name": local, "rate": rate / 2, "amount": total - half}]
    return [{"name": "IGST", "rate": rate, "amount": total}]


def with_gst(taxable: int, country: str | None) -> int:
    return taxable + (taxable * gst_rate(country) + 50) // 100


# --------------------------------------------------------------------------- #
# Razorpay API
# --------------------------------------------------------------------------- #
def _call(method: str, path: str, data: dict | None = None) -> dict:
    if not configured():
        raise BillingError("payments_unavailable")
    try:
        r = requests.request(method, f"{API}{path}", auth=(key_id(), _env("RAZORPAY_KEY_SECRET")), timeout=20,
                             params=data if method == "GET" else None, json=None if method == "GET" else data)
    except requests.RequestException as e:
        raise BillingError("payment_error", type(e).__name__) from None
    if r.status_code >= 300:
        # Razorpay's error names the problem (never a secret); keep it in the log, not in responses
        try:
            msg = (r.json().get("error") or {}).get("description", "")
        except ValueError:
            msg = r.text[:200]
        log.error("Razorpay %s %s -> HTTP %s: %s", method, path, r.status_code, msg)
        raise BillingError("payment_error", f"HTTP {r.status_code}")
    return r.json()


def base_price(plan: dict, interval: str) -> int:
    """The plan's price before GST, in paise."""
    return int(plan["price_inr_yearly" if interval == "year" else "price_inr_monthly"]) * 100


def plan_id_for(plan: dict, interval: str, rate: int) -> str:
    """The Razorpay plan for `plan` billed every `interval` with `rate`% GST included, created once and
    remembered in the settings table (the key carries the amount, so a price change makes a new plan)."""
    from src import db
    base = base_price(plan, interval)
    amount = base + (base * rate + 50) // 100
    key = f"{plan['id']}_{interval}_{amount}"
    known = db.get_setting("razorpay_plans", {}) or {}
    if key in known:
        return known[key]
    created = _call("POST", "/plans", {
        "period": PERIOD[interval], "interval": 1,
        "item": {"name": f"Mintly {plan['name']} ({'yearly' if interval == 'year' else 'monthly'})",
                 "amount": amount, "currency": CURRENCY,
                 "description": f"{plan['posts_per_day']} posts/day" + (f", incl. {rate}% GST" if rate else "")},
        "notes": {"plan": plan["id"], "interval": interval, "base": str(base), "gst_rate": str(rate)},
    })
    known = dict(db.get_setting("razorpay_plans", {}) or {})
    known[key] = created["id"]
    db.set_setting("razorpay_plans", known)
    return created["id"]


def fetch_subscription(sub_id: str) -> dict:
    return _call("GET", f"/subscriptions/{sub_id}")


def fetch_plan(plan_id: str) -> dict:
    return _call("GET", f"/plans/{plan_id}")


def cancel_subscription(sub_id: str, *, at_cycle_end: bool) -> dict:
    return _call("POST", f"/subscriptions/{sub_id}/cancel", {"cancel_at_cycle_end": 1 if at_cycle_end else 0})


def payment_signature_ok(payment_id: str, subscription_id: str, signature: str) -> bool:
    """Checkout's success handler: HMAC-SHA256(payment_id|subscription_id) under the key secret."""
    secret = _env("RAZORPAY_KEY_SECRET")
    if not (secret and payment_id and subscription_id and signature):
        return False
    expected = hmac.new(secret.encode(), f"{payment_id}|{subscription_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def webhook_signature_ok(body: bytes, signature: str) -> bool:
    """X-Razorpay-Signature: HMAC-SHA256 of the raw request body under the webhook secret."""
    secret = _env("RAZORPAY_WEBHOOK_SECRET")
    if not (secret and signature):
        return False
    return hmac.compare_digest(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), signature)


# --------------------------------------------------------------------------- #
# Quotes and plan changes
# --------------------------------------------------------------------------- #
def add_period(ts: int, interval: str) -> int:
    """`ts` plus one month or one year, on the same day where it exists (31 Jan + 1 month = 28/29 Feb)."""
    d = datetime.fromtimestamp(ts, timezone.utc)
    year, month = (d.year + 1, d.month) if interval == "year" else (d.year + d.month // 12, d.month % 12 + 1)
    day = min(d.day, calendar.monthrange(year, month)[1])
    return int(d.replace(year=year, month=month, day=day).timestamp())


def live_subscription(user) -> dict | None:
    """The user's current Razorpay subscription when it still runs (renews or ends at its period end)."""
    if not user.razorpay_subscription_id:
        return None
    sub = fetch_subscription(user.razorpay_subscription_id)
    return sub if sub.get("status") in ("active", "authenticated", "pending") else None


def quote(user, plan: dict, interval: str, now: int) -> dict:
    """What moving `user` to `plan`/`interval` costs at `now` (unix seconds), itemised, with GST.

    Raises ValueError("same_plan") when that is already their plan."""
    country, state = user.billing_country, user.billing_state
    new_base = base_price(plan, interval)
    current = live_subscription(user)
    old = None
    if current:
        notes = current.get("notes") or {}
        if notes.get("plan") == plan["id"] and notes.get("interval") == interval:
            raise ValueError("same_plan")
        old_plan = (fetch_plan(current["plan_id"]).get("notes") or {}) if current.get("plan_id") else {}
        start, end = int(current.get("current_start") or 0), int(current.get("current_end") or 0)
        old_base = int(old_plan.get("base") or 0)
        left = max(0.0, min(1.0, (end - now) / (end - start))) if end > start else 0.0
        old = {"sub": current, "plan": notes.get("plan"), "end": end, "credit": int(old_base * left)}

    renew_total = with_gst(new_base, country)
    if old and old["credit"] >= new_base:                # downgrade: waits for the paid period to end
        return {"kind": "downgrade", "currency": CURRENCY, "lines": [], "taxable": 0, "taxes": [], "total_now": 0,
                "effective_at": old["end"], "renews_at": old["end"], "renewal_total": renew_total,
                "renewal_taxes": taxes(new_base, country, state), "gst_rate": gst_rate(country),
                "replaces": old["sub"]["id"]}

    starts, renews = now, add_period(now, interval)
    lines = [{"label": f"{plan['name']} ({'yearly' if interval == 'year' else 'monthly'})", "from": starts,
              "to": renews, "amount": new_base}]
    if old:
        lines.append({"label": f"Unused time on {(old['plan'] or 'current plan').capitalize()}", "from": now,
                      "to": old["end"], "amount": -old["credit"]})
    taxable = sum(line["amount"] for line in lines)
    tax = taxes(taxable, country, state)
    return {"kind": "upgrade" if old else "new", "currency": CURRENCY, "lines": lines, "taxable": taxable,
            "taxes": tax, "total_now": taxable + sum(t["amount"] for t in tax), "effective_at": starts,
            "renews_at": renews, "renewal_total": renew_total, "renewal_taxes": taxes(new_base, country, state),
            "gst_rate": gst_rate(country), "replaces": old["sub"]["id"] if old else None}


def start(user, plan: dict, interval: str, q: dict) -> dict:
    """Create the Razorpay subscription for quote `q`; the customer authorises it in Razorpay Checkout."""
    rate = q["gst_rate"]
    data = {
        "plan_id": plan_id_for(plan, interval, rate), "total_count": TOTAL_COUNT[interval], "customer_notify": 1,
        "notes": {"user_id": str(user.id), "plan": plan["id"], "interval": interval, "change": q["kind"],
                  "replaces": q["replaces"] or "", "gst_rate": str(rate)},
    }
    if q["kind"] == "upgrade":
        data["start_at"] = q["renews_at"]                 # regular charges begin after the period paid now
        data["addons"] = [{"item": {"name": f"Upgrade to {plan['name']} (prorated" + (", incl. GST)" if rate else ")"),
                                    "amount": q["total_now"], "currency": CURRENCY}}]
    elif q["kind"] == "downgrade":
        data["start_at"] = q["effective_at"]
    return _call("POST", "/subscriptions", data)


def _ts(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def _set(user, tier: str, status: str, renews) -> None:
    user.subscription_tier, user.subscription_status = tier, status
    user.subscription_renews_at = _ts(renews) if status in ("active", "past_due", "canceling", "changing") else None


def _promote(user, sub: dict, cancel_old: bool) -> str:
    notes = sub.get("notes") or {}
    old = user.razorpay_subscription_id
    user.razorpay_subscription_id, user.razorpay_pending_subscription_id = sub["id"], None
    if cancel_old and old and old != sub["id"]:
        try:
            cancel_subscription(old, at_cycle_end=False)   # credited in the upgrade: stop billing it now
        except BillingError as e:
            log.error("could not cancel replaced subscription %s for user %s: %s", old, user.id, e.code)
    _set(user, notes.get("plan") or "free", "active", sub.get("charge_at") or sub.get("current_end"))
    return "activated"


def apply(user, sub: dict) -> str:
    """Bring `user`'s plan in line with Razorpay subscription `sub` (as Razorpay reports it).

    Only the user's current or pending subscription can change anything; events for an older one are ignored.
    Returns ignored | activated | scheduled | updated | downgraded."""
    sub_id, status = sub.get("id") or "", sub.get("status") or ""
    notes = sub.get("notes") or {}
    if not sub_id or sub_id not in (user.razorpay_subscription_id, user.razorpay_pending_subscription_id):
        return "ignored"

    if sub_id == user.razorpay_pending_subscription_id:
        change = notes.get("change")
        if status in _ENDED:                               # abandoned or failed checkout: nothing changes
            user.razorpay_pending_subscription_id = None
            if user.subscription_status == "changing":
                user.subscription_status = "active"
            return "ignored"
        if change == "downgrade":
            if status == "active":                         # the new period began
                return _promote(user, sub, cancel_old=False)
            if status == "authenticated" and user.subscription_status != "changing":
                try:
                    cancel_subscription(user.razorpay_subscription_id, at_cycle_end=True)
                except BillingError as e:
                    log.error("could not schedule the end of %s for user %s: %s",
                              user.razorpay_subscription_id, user.id, e.code)
                    return "ignored"                       # retried on the next event
                user.subscription_status = "changing"
                return "scheduled"
            return "ignored"
        # new: paid with the first charge (active). upgrade: the prorated amount is paid when the customer
        # authorises, so authenticated already means paid.
        if status == "active" or (change == "upgrade" and status == "authenticated"):
            return _promote(user, sub, cancel_old=change == "upgrade")
        return "ignored"

    # the current subscription
    ours, keeps_plan = _STATUS.get(status, (None, False))
    if ours is None:
        return "ignored"
    if keeps_plan:
        if user.subscription_status in ("canceling", "changing") and ours == "active":
            ours = user.subscription_status                # a renewal doesn't undo a scheduled end
        changed = (user.subscription_tier, user.subscription_status) != (notes.get("plan"), ours)
        _set(user, notes.get("plan") or user.subscription_tier, ours, sub.get("charge_at") or sub.get("current_end"))
        return "updated" if changed else "ignored"
    if status in _ENDED and user.razorpay_pending_subscription_id:
        # the paid period ended and a downgrade is waiting: switch to it instead of falling to Free
        try:
            pending = fetch_subscription(user.razorpay_pending_subscription_id)
        except BillingError:
            pending = None
        if pending and pending.get("status") in ("authenticated", "active"):
            user.razorpay_subscription_id = None
            return _promote(user, pending, cancel_old=False)
    _set(user, "free", ours, None)
    if status in _ENDED:
        user.razorpay_subscription_id = None
    return "downgraded"
