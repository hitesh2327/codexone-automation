"""Razorpay Subscriptions: the only way a user's plan changes (besides local-dev instant activation).

    from src import billing
    billing.configured()                          # keys present?
    sub = billing.create_subscription("creator", "month", user_id=7, email="a@b.c")
    billing.apply(session, user, billing.fetch_subscription(sub_id))   # after a verified payment or webhook

Server settings (environment; on AWS they come from SSM /codexone/, see infra/put_secrets.py):
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET      API keys (rzp_test_... while testing)
    RAZORPAY_WEBHOOK_SECRET                   the secret typed when creating the webhook in the Razorpay dashboard
    RAZORPAY_PLAN_<PLAN>_<INTERVAL>           Razorpay plan ids, e.g. RAZORPAY_PLAN_CREATOR_MONTH=plan_Nx...

A plan changes only from a subscription Razorpay itself reports (fetched with our key, or delivered by a webhook
whose signature checks out), never from what a browser claims. Switching plans keeps the new subscription as
"pending" until it is paid; then the old one is cancelled so nobody pays twice.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone

import requests

log = logging.getLogger("codexone.billing")

API = "https://api.razorpay.com/v1"
PLANS = ("starter", "creator", "pro")
INTERVALS = ("month", "year")
# Number of billing cycles a subscription runs before Razorpay ends it (it must be finite): ~10 years.
TOTAL_COUNT = {"month": 120, "year": 10}

# Razorpay subscription status -> (our status, keeps the paid plan?)
_STATUS = {
    "active": ("active", True),
    "authenticated": ("pending", False),   # mandate set up, first charge not taken yet
    "pending": ("past_due", True),         # a renewal failed; Razorpay retries, access continues meanwhile
    "halted": ("halted", False),           # every retry failed
    "paused": ("paused", False),
    "cancelled": ("canceled", False),
    "completed": ("canceled", False),
    "expired": ("canceled", False),
}


class BillingError(Exception):
    """`code`: payments_unavailable | payment_error | unknown_plan."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def key_id() -> str:
    return _env("RAZORPAY_KEY_ID")


def configured() -> bool:
    return bool(key_id() and _env("RAZORPAY_KEY_SECRET"))


def plan_id_for(plan: str, interval: str) -> str:
    return _env(f"RAZORPAY_PLAN_{plan.upper()}_{interval.upper()}")


def plan_of(razorpay_plan_id: str) -> tuple[str, str] | None:
    """(our plan, interval) for a Razorpay plan id, from the configured mapping only."""
    for plan in PLANS:
        for interval in INTERVALS:
            if razorpay_plan_id and plan_id_for(plan, interval) == razorpay_plan_id:
                return plan, interval
    return None


def _call(method: str, path: str, **kw) -> dict:
    if not configured():
        raise BillingError("payments_unavailable")
    try:
        r = requests.request(method, f"{API}{path}", auth=(key_id(), _env("RAZORPAY_KEY_SECRET")), timeout=20, **kw)
    except requests.RequestException as e:
        raise BillingError("payment_error", type(e).__name__) from None
    if r.status_code >= 300:
        # the body names the problem (never a secret); keep it in the log, not in responses
        log.error("Razorpay %s %s -> HTTP %s: %s", method, path, r.status_code, r.text[:300])
        raise BillingError("payment_error", f"HTTP {r.status_code}")
    return r.json()


def create_subscription(plan: str, interval: str, *, user_id: int, email: str | None) -> dict:
    rzp_plan = plan_id_for(plan, interval)
    if not rzp_plan:
        raise BillingError("unknown_plan", f"No Razorpay plan configured for {plan}/{interval}")
    return _call("POST", "/subscriptions", json={
        "plan_id": rzp_plan, "total_count": TOTAL_COUNT[interval], "customer_notify": 1,
        "notes": {"user_id": str(user_id), "plan": plan, "interval": interval, "email": email or ""},
    })


def fetch_subscription(sub_id: str) -> dict:
    return _call("GET", f"/subscriptions/{sub_id}")


def cancel_subscription(sub_id: str, *, at_cycle_end: bool) -> dict:
    return _call("POST", f"/subscriptions/{sub_id}/cancel", json={"cancel_at_cycle_end": 1 if at_cycle_end else 0})


def _hmac(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def payment_signature_ok(payment_id: str, subscription_id: str, signature: str) -> bool:
    """Checkout's success handler: HMAC-SHA256(payment_id|subscription_id) under the key secret."""
    secret = _env("RAZORPAY_KEY_SECRET")
    if not (secret and payment_id and subscription_id and signature):
        return False
    return hmac.compare_digest(_hmac(secret, f"{payment_id}|{subscription_id}".encode()), signature)


def webhook_signature_ok(body: bytes, signature: str) -> bool:
    """X-Razorpay-Signature: HMAC-SHA256 of the raw request body under the webhook secret."""
    secret = _env("RAZORPAY_WEBHOOK_SECRET")
    if not (secret and signature):
        return False
    return hmac.compare_digest(_hmac(secret, body), signature)


def _ts(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def apply(user, sub: dict) -> str:
    """Bring `user`'s plan in line with Razorpay subscription `sub` (as Razorpay reports it).

    Only the user's current or pending subscription can change anything; events for an older subscription are
    ignored. Returns what happened: ignored | activated | updated | downgraded.
    """
    sub_id = sub.get("id") or ""
    current, pending = user.razorpay_subscription_id, user.razorpay_pending_subscription_id
    if not sub_id or sub_id not in (current, pending):
        return "ignored"
    status, keeps_plan = _STATUS.get(sub.get("status") or "", (None, False))
    if status is None:
        return "ignored"
    mapped = plan_of(sub.get("plan_id") or "")

    if sub_id == pending:
        if status != "active" or not mapped:
            if status == "canceled":
                user.razorpay_pending_subscription_id = None   # abandoned or failed checkout: nothing changes
            return "ignored"
        old = current
        user.razorpay_subscription_id, user.razorpay_pending_subscription_id = sub_id, None
        if old and old != sub_id:
            try:
                cancel_subscription(old, at_cycle_end=False)   # the new plan replaces it now: stop billing the old
            except BillingError as e:
                log.error("could not cancel replaced subscription %s for user %s: %s", old, user.id, e.code)
        _set(user, mapped[0], "active", sub)
        return "activated"

    # the current subscription
    if keeps_plan and mapped:
        changed = user.subscription_tier != mapped[0] or user.subscription_status != status
        _set(user, mapped[0], status, sub)
        return "updated" if changed else "ignored"
    if not keeps_plan and status in ("halted", "paused", "canceled"):
        _set(user, "free", status, sub)
        if status == "canceled":
            user.razorpay_subscription_id = None
        return "downgraded"
    return "ignored"


def _set(user, tier: str, status: str, sub: dict) -> None:
    user.subscription_tier, user.subscription_status = tier, status
    user.subscription_renews_at = _ts(sub.get("current_end")) if status in ("active", "past_due") else None
