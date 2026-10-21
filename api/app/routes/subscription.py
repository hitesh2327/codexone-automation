"""Subscription plans and Razorpay checkout (src/billing.py holds the gateway logic).

A plan changes only from a subscription Razorpay itself confirms: the signed checkout callback (/verify, which
re-fetches the subscription with our key) or the signed webhook. Both go through billing.apply. Without
Razorpay keys, checkout refuses (503); a gateway error returns 502; neither ever changes a plan.
BILLING_DEV_INSTANT=true allows instant activation for local development only: it is ignored on a real
deployment (SSM_PREFIX set or COOKIE_SECURE on), so it can't be switched on in production by mistake.
"""
from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from api.app.deps import CurrentUser, current_user, require_csrf
from api.app.settings import settings
from src import activity, billing, db
from src.db.models import User

log = logging.getLogger("codexone.api.subscription")
public_router = APIRouter(prefix="/subscription", tags=["subscription"])
router = APIRouter(prefix="/subscription", tags=["subscription"])

PLANS = [
    {
        "id": "starter",
        "name": "Starter",
        "badge": "For Solopreneurs",
        "price_monthly": 19,
        "price_yearly": 190,
        "posts_per_day": 1,
        "features": [
            "1 automated post per day",
            "Instagram Reels & Carousels",
            "AI topic discovery & script generation",
            "Telegram approval preview bot",
            "Standard queue processing",
        ],
        "popular": False,
    },
    {
        "id": "creator",
        "name": "Creator",
        "badge": "Most Popular",
        "price_monthly": 49,
        "price_yearly": 490,
        "posts_per_day": 2,
        "features": [
            "2 automated posts per day (10:00 & 18:00 IST)",
            "Instagram Reels + YouTube Shorts",
            "Custom brand aesthetic & tone of voice",
            "Voice selection (ElevenLabs & Edge-TTS)",
            "Automated SEO hashtags & descriptions",
            "Instant Regenerate & publish-now",
        ],
        "popular": True,
    },
    {
        "id": "pro",
        "name": "Pro / Agency",
        "badge": "Maximum Reach",
        "price_monthly": 99,
        "price_yearly": 990,
        "posts_per_day": 4,
        "features": [
            "Up to 4 posts per day",
            "Multi-platform auto-posting (IG + YT Shorts)",
            "Custom slot scheduling & cadence",
            "Unlimited post regeneration",
            "Priority GPU rendering pipeline",
            "Dedicated webhook & API integration",
        ],
        "popular": False,
    },
]

_UNAVAILABLE = "Payments aren't set up yet, so plans can't be changed right now."
_GATEWAY = ("Couldn't reach the payment provider. Nothing was charged and your plan didn't change. "
            "Try again in a few minutes.")


def _dev_instant() -> bool:
    """Instant plan activation without payment: local development only, never on a deployment."""
    deployed = settings().cookie_secure or bool((os.getenv("SSM_PREFIX") or "").strip())
    return (os.getenv("BILLING_DEV_INSTANT") or "").strip().lower() == "true" and not deployed


def _fail(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(code, detail={"code": error, "message": message})


def _billing_fail(e: billing.BillingError) -> HTTPException:
    if e.code == "payments_unavailable":
        return _fail(status.HTTP_503_SERVICE_UNAVAILABLE, e.code, _UNAVAILABLE)
    if e.code == "unknown_plan":
        return _fail(status.HTTP_503_SERVICE_UNAVAILABLE, "payments_unavailable", "That plan isn't available to buy yet.")
    return _fail(status.HTTP_502_BAD_GATEWAY, "payment_error", _GATEWAY)


def _user(s, cu: CurrentUser) -> User:
    user = s.get(User, cu.id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def _change(user: User, before: tuple[str, str], via: str) -> dict | None:
    """The activity entry for a plan change, built inside the session; _log writes it after the session closes
    (activity.record opens its own session, which must not wait on ours)."""
    if (user.subscription_tier, user.subscription_status) == before:
        return None
    return {"summary": f"Plan {before[0]} ({before[1]}) -> {user.subscription_tier} ({user.subscription_status})",
            "actor": user.username or user.email,
            "detail": {"user_id": user.id, "tier": user.subscription_tier, "status": user.subscription_status,
                       "via": via}}


def _log(change: dict | None) -> None:
    if change:
        activity.record("subscription.changed", change["summary"], source="billing", actor=change["actor"],
                        detail=change["detail"])


def _renews(user: User) -> str | None:
    return user.subscription_renews_at.isoformat() if user.subscription_renews_at else None


class CheckoutBody(BaseModel):
    plan_id: str = Field(min_length=1, max_length=32)
    interval: str = Field(default="month", pattern="^(month|year)$")


class VerifyBody(BaseModel):
    razorpay_payment_id: str = Field(min_length=1, max_length=64)
    razorpay_subscription_id: str = Field(min_length=1, max_length=64)
    razorpay_signature: str = Field(min_length=1, max_length=128)


@public_router.get("/plans")
@router.get("/plans")
def get_plans() -> dict:
    """Public subscription plans catalogue."""
    return {"plans": PLANS, "payments_enabled": billing.configured()}


@router.get("/status")
def get_subscription_status(cu: CurrentUser = Depends(current_user)) -> dict:
    """Current user's subscription status."""
    with db.session() as s:
        user = _user(s, cu)
        return {
            "tier": user.subscription_tier or "free",
            "status": user.subscription_status or "active",
            "renews_at": _renews(user),
            "has_subscription": bool(user.razorpay_subscription_id),
            "payments_enabled": billing.configured(),
        }


@router.post("/checkout")
def create_checkout_session(body: CheckoutBody, cu: CurrentUser = Depends(require_csrf)) -> dict:
    """Start a Razorpay subscription; the browser opens Razorpay Checkout with the returned id.
    The plan changes only once Razorpay confirms the payment (/verify or the webhook)."""
    plan = next((p for p in PLANS if p["id"] == body.plan_id), None)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown plan: {body.plan_id}")

    with db.session() as s:
        user = _user(s, cu)
        if billing.configured():
            try:
                sub = billing.create_subscription(body.plan_id, body.interval, user_id=user.id, email=user.email)
            except billing.BillingError as e:
                raise _billing_fail(e) from None
            user.razorpay_pending_subscription_id = sub["id"]
            return {"mode": "razorpay", "key_id": billing.key_id(), "subscription_id": sub["id"],
                    "plan": plan["name"], "email": user.email or "", "name": user.name or ""}

        if not _dev_instant():
            raise _fail(status.HTTP_503_SERVICE_UNAVAILABLE, "payments_unavailable", _UNAVAILABLE)

        # Local development only: activate without payment (see _dev_instant)
        before = (user.subscription_tier, user.subscription_status)
        user.subscription_tier, user.subscription_status = body.plan_id, "active"
        change = _change(user, before, "dev_instant")
    _log(change)
    return {"ok": True, "tier": body.plan_id, "status": "active", "mode": "instant",
            "message": f"Switched to {plan['name']} (local development: no payment)."}


@router.post("/verify")
def verify_payment(body: VerifyBody, cu: CurrentUser = Depends(require_csrf)) -> dict:
    """Razorpay Checkout's success callback. The signature proves Razorpay issued it; the plan then comes from
    the subscription as Razorpay reports it, not from anything the browser sent."""
    if not billing.payment_signature_ok(body.razorpay_payment_id, body.razorpay_subscription_id,
                                        body.razorpay_signature):
        raise _fail(status.HTTP_400_BAD_REQUEST, "bad_signature", "That payment confirmation isn't valid.")
    with db.session() as s:
        user = _user(s, cu)
        if body.razorpay_subscription_id not in (user.razorpay_pending_subscription_id, user.razorpay_subscription_id):
            raise _fail(status.HTTP_400_BAD_REQUEST, "bad_signature", "That payment isn't for this account.")
        try:
            sub = billing.fetch_subscription(body.razorpay_subscription_id)
        except billing.BillingError as e:
            raise _billing_fail(e) from None
        before = (user.subscription_tier, user.subscription_status)
        outcome = billing.apply(user, sub)
        change = _change(user, before, "checkout")
        # a subscription still settling its first charge stays as it was here; the webhook finishes it
        out = {"ok": True, "outcome": outcome, "tier": user.subscription_tier, "status": user.subscription_status}
    _log(change)
    return out


@router.post("/cancel")
def cancel_subscription(cu: CurrentUser = Depends(require_csrf)) -> dict:
    """Cancel at the end of the period already paid for; the webhook downgrades the plan when it ends."""
    with db.session() as s:
        user = _user(s, cu)
        if not user.razorpay_subscription_id:
            raise _fail(status.HTTP_400_BAD_REQUEST, "no_subscription", "There's no paid subscription to cancel.")
        try:
            billing.cancel_subscription(user.razorpay_subscription_id, at_cycle_end=True)
        except billing.BillingError as e:
            raise _billing_fail(e) from None
        before = (user.subscription_tier, user.subscription_status)
        user.subscription_status = "canceling"
        change = _change(user, before, "cancel")
        out = {"ok": True, "tier": user.subscription_tier, "status": user.subscription_status, "renews_at": _renews(user)}
    _log(change)
    return out


@public_router.post("/razorpay/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request) -> dict:
    """Razorpay subscription events. Public (Razorpay calls it), so the signature is the only authority."""
    raw = await request.body()
    if not billing.webhook_signature_ok(raw, request.headers.get("x-razorpay-signature", "")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad signature")
    try:
        event = json.loads(raw)
        sub = event["payload"]["subscription"]["entity"]
        sub_id = sub["id"]
    except (ValueError, KeyError, TypeError):
        return {"ok": True, "outcome": "ignored"}       # signed, but not a subscription event: nothing to do
    with db.session() as s:
        user = s.scalars(select(User).where(or_(User.razorpay_subscription_id == sub_id,
                                                User.razorpay_pending_subscription_id == sub_id))).first()
        if not user:
            log.info("webhook %s for an unknown subscription", event.get("event"))
            return {"ok": True, "outcome": "ignored"}
        before = (user.subscription_tier, user.subscription_status)
        outcome = billing.apply(user, sub)
        change = _change(user, before, f"webhook:{event.get('event')}")
    _log(change)
    return {"ok": True, "outcome": outcome}
