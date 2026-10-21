"""Stripe subscriptions: the only way a user's plan changes (besides local-dev instant activation).

    from src import billing
    billing.configured()                                         # secret key present?
    session = billing.create_checkout(plan, interval, ...)      # -> {"id", "url"}: send the browser to url
    billing.adopt(user, billing.fetch_subscription(sub_id))      # a paid subscription becomes the user's plan
    billing.apply(user, sub)                                     # later changes to the user's current subscription

Server settings (environment; on AWS they come from SSM /codexone/):
    STRIPE_SECRET_KEY        sk_test_... while testing, sk_live_... in production
    STRIPE_WEBHOOK_SECRET    whsec_... of the webhook endpoint pointing at /api/subscription/stripe/webhook

Calls Stripe's REST API with requests (no SDK in the Lambda image). A plan changes only from a subscription
Stripe itself reports: fetched with our secret key, or delivered by a webhook whose signature checks out. The
plan a subscription grants comes from the metadata our server wrote when it created the checkout, which only
holders of the secret key can set.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger("codexone.billing")

API = "https://api.stripe.com/v1"
PLANS = ("starter", "creator", "pro")
SIGNATURE_TOLERANCE = 300        # seconds a webhook signature stays valid (Stripe's default)

# Stripe subscription status -> (our status, keeps the paid plan?)
_STATUS = {
    "active": ("active", True),
    "trialing": ("active", True),
    "past_due": ("past_due", True),       # a renewal failed; Stripe retries, access continues meanwhile
    "unpaid": ("halted", False),          # every retry failed
    "paused": ("paused", False),
    "canceled": ("canceled", False),
    "incomplete_expired": ("canceled", False),
    "incomplete": (None, False),          # first payment not done yet: nothing to change
}


class BillingError(Exception):
    """`code`: payments_unavailable | payment_error."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def configured() -> bool:
    return bool(_env("STRIPE_SECRET_KEY"))


def _form(data: dict, prefix: str = "") -> dict[str, str]:
    """Stripe's form encoding: {"a": {"b": 1}, "c": [{"d": 2}]} -> {"a[b]": "1", "c[0][d]": "2"}."""
    out: dict[str, str] = {}
    for key, value in data.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            out.update(_form(value, name))
        elif isinstance(value, list):
            out.update(_form({str(i): v for i, v in enumerate(value)}, name))
        elif isinstance(value, bool):
            out[name] = "true" if value else "false"
        elif value is not None:
            out[name] = str(value)
    return out


def _call(method: str, path: str, data: dict | None = None) -> dict:
    if not configured():
        raise BillingError("payments_unavailable")
    try:
        r = requests.request(method, f"{API}{path}", auth=(_env("STRIPE_SECRET_KEY"), ""),
                             data=_form(data) if data else None, timeout=20)
    except requests.RequestException as e:
        raise BillingError("payment_error", type(e).__name__) from None
    if r.status_code >= 300:
        # Stripe's error message names the problem (never a secret); keep it in the log, not in responses
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = r.text[:200]
        log.error("Stripe %s %s -> HTTP %s: %s", method, path, r.status_code, msg)
        raise BillingError("payment_error", f"HTTP {r.status_code}")
    return r.json()


def create_checkout(plan: dict, interval: str, *, user_id: int, customer: str | None, email: str | None,
                    success_url: str, cancel_url: str) -> dict:
    """A Stripe-hosted Checkout page for `plan` (an entry of the API's PLANS) billed every `interval`."""
    amount = plan["price_yearly"] if interval == "year" else plan["price_monthly"]
    meta = {"user_id": str(user_id), "plan": plan["id"], "interval": interval}
    data = {
        "mode": "subscription",
        "line_items": [{
            "quantity": 1,
            "price_data": {
                "currency": "usd", "unit_amount": int(amount) * 100, "recurring": {"interval": interval},
                "product_data": {"name": f"Mintly {plan['name']}",
                                 "description": f"{plan['posts_per_day']} posts/day automated publishing"},
            },
        }],
        "client_reference_id": str(user_id),
        "metadata": meta,
        "subscription_data": {"metadata": meta},
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if customer:
        data["customer"] = customer
    elif email:
        data["customer_email"] = email
    return _call("POST", "/checkout/sessions", data)


def fetch_session(session_id: str) -> dict:
    return _call("GET", f"/checkout/sessions/{session_id}")


def fetch_subscription(sub_id: str) -> dict:
    return _call("GET", f"/subscriptions/{sub_id}")


def cancel_at_period_end(sub_id: str) -> dict:
    return _call("POST", f"/subscriptions/{sub_id}", {"cancel_at_period_end": True})


def cancel_now(sub_id: str) -> dict:
    return _call("DELETE", f"/subscriptions/{sub_id}")


def webhook_event_ok(body: bytes, header: str, now: float | None = None) -> bool:
    """Stripe-Signature: "t=<unix time>,v1=<hex HMAC-SHA256 of '<t>.<body>' under the webhook secret>[,v1=...]".
    Rejects old timestamps so a captured request can't be replayed later."""
    secret = _env("STRIPE_WEBHOOK_SECRET")
    if not (secret and header):
        return False
    parts = [p.split("=", 1) for p in header.split(",") if "=" in p]
    stamps = [v for k, v in parts if k.strip() == "t"]
    sigs = [v.strip() for k, v in parts if k.strip() == "v1"]
    if not stamps or not sigs or not stamps[0].strip().isdigit():
        return False
    t = int(stamps[0])
    if abs((now if now is not None else time.time()) - t) > SIGNATURE_TOLERANCE:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in sigs)


def _ts(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def _period_end(sub: dict):
    # newer Stripe API versions keep the period on the subscription items
    if sub.get("current_period_end"):
        return sub["current_period_end"]
    items = ((sub.get("items") or {}).get("data") or [])
    return items[0].get("current_period_end") if items else None


def plan_of(sub: dict) -> str | None:
    plan = ((sub.get("metadata") or {}).get("plan") or "").strip()
    return plan if plan in PLANS else None


def owner_id(sub: dict) -> int | None:
    uid = ((sub.get("metadata") or {}).get("user_id") or "").strip()
    return int(uid) if uid.isdigit() else None


def adopt(user, sub: dict) -> str:
    """A paid subscription of this user's becomes their plan; the one it replaces is cancelled so nobody pays
    twice. Only for a subscription known to be the user's (their checkout, or our metadata on a signed event).
    Returns ignored | activated, or apply's result when it is already the current one."""
    if sub.get("id") == user.stripe_subscription_id:
        return apply(user, sub)
    status, keeps_plan = _STATUS.get(sub.get("status") or "", (None, False))
    plan = plan_of(sub)
    if status != "active" or not keeps_plan or not plan:
        return "ignored"                           # unpaid or abandoned checkout: nothing changes
    old = user.stripe_subscription_id
    if old:
        try:
            current = fetch_subscription(old)
        except BillingError:
            current = None
        if current and int(current.get("created") or 0) > int(sub.get("created") or 0):
            return "ignored"                       # an older subscription's late event: the newer one stays
        if current and current.get("status") not in ("canceled", "incomplete_expired"):
            try:
                cancel_now(old)                    # the new plan replaces it now: stop billing the old one
            except BillingError as e:
                log.error("could not cancel replaced subscription %s for user %s: %s", old, user.id, e.code)
    user.stripe_subscription_id = sub["id"]
    if sub.get("customer"):
        user.stripe_customer_id = sub["customer"]
    _set(user, plan, "canceling" if sub.get("cancel_at_period_end") else "active", sub)
    return "activated"


def apply(user, sub: dict) -> str:
    """Bring `user`'s plan in line with their current subscription as Stripe reports it. Events for any other
    subscription are ignored. Returns ignored | updated | downgraded."""
    if not sub.get("id") or sub.get("id") != user.stripe_subscription_id:
        return "ignored"
    status, keeps_plan = _STATUS.get(sub.get("status") or "", (None, False))
    if status is None:
        return "ignored"
    plan = plan_of(sub)
    if keeps_plan and plan:
        if status == "active" and sub.get("cancel_at_period_end"):
            status = "canceling"
        changed = (user.subscription_tier, user.subscription_status) != (plan, status)
        _set(user, plan, status, sub)
        return "updated" if changed else "ignored"
    if not keeps_plan:
        _set(user, "free", status, sub)
        if status == "canceled":
            user.stripe_subscription_id = None
        return "downgraded"
    return "ignored"


def _set(user, tier: str, status: str, sub: dict) -> None:
    user.subscription_tier, user.subscription_status = tier, status
    user.subscription_renews_at = _ts(_period_end(sub)) if status in ("active", "past_due", "canceling") else None
