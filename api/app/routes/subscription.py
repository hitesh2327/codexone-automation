"""Subscription plans and Stripe checkout (src/billing.py holds the gateway logic).

A plan changes only from a subscription Stripe itself confirms: the return from Checkout (/verify, which
re-fetches the session and subscription with our secret key), the signed webhook, or an in-place switch of a
subscription the user already pays for (/switch: prorated, the difference charged or credited now; /checkout
returns the exact amount first so the page can ask). All go through billing.adopt / billing.apply, with the
user's row locked (SELECT ... FOR UPDATE) so two Stripe events arriving together are handled one after the other. Without STRIPE_SECRET_KEY, checkout refuses (503); a gateway error returns 502;
neither ever changes a plan. BILLING_DEV_INSTANT=true allows instant activation for local development only: it is
ignored on a real deployment (SSM_PREFIX set or COOKIE_SECURE on), so it can't be switched on in production.
"""
from __future__ import annotations

import json
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

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
_DECLINED = "Your card was declined, so your plan didn't change. Update your card and try again."
PRORATION_MAX_AGE = 30 * 60      # a switch must be confirmed within 30 minutes of seeing its price
# Stripe events that can change a plan; anything else is acknowledged and ignored
_SUB_EVENTS = {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted",
               "customer.subscription.paused", "customer.subscription.resumed"}


def _dev_instant() -> bool:
    """Instant plan activation without payment: local development only, never on a deployment."""
    deployed = settings().cookie_secure or bool((os.getenv("SSM_PREFIX") or "").strip())
    return (os.getenv("BILLING_DEV_INSTANT") or "").strip().lower() == "true" and not deployed


def _fail(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(code, detail={"code": error, "message": message})


def _billing_fail(e: billing.BillingError) -> HTTPException:
    if e.code == "payments_unavailable":
        return _fail(status.HTTP_503_SERVICE_UNAVAILABLE, e.code, _UNAVAILABLE)
    if e.code == "card_declined":
        return _fail(status.HTTP_402_PAYMENT_REQUIRED, e.code, _DECLINED)
    return _fail(status.HTTP_502_BAD_GATEWAY, "payment_error", _GATEWAY)


def _user(s, cu: CurrentUser, lock: bool = False) -> User:
    """The signed-in user's row; lock=True holds it (FOR UPDATE) until the session ends, for billing changes."""
    user = s.get(User, cu.id, with_for_update=lock)
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
    session_id: str = Field(min_length=1, max_length=255)


class SwitchBody(CheckoutBody):
    proration_date: int = Field(gt=0)      # from /checkout's quote, so the charge matches what was shown


def _plan(plan_id: str) -> dict:
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown plan: {plan_id}")
    return plan


def _live_subscription(user: User) -> dict | None:
    """The user's current Stripe subscription when it can be switched in place, else None (start a Checkout)."""
    if not user.stripe_subscription_id:
        return None
    sub = billing.fetch_subscription(user.stripe_subscription_id)
    return sub if sub.get("status") in billing.LIVE else None


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
            "has_subscription": bool(user.stripe_subscription_id),
            "payments_enabled": billing.configured(),
        }


@router.post("/checkout")
def create_checkout_session(body: CheckoutBody, cu: CurrentUser = Depends(require_csrf)) -> dict:
    """For a new subscriber, a Stripe Checkout page the browser goes to; the plan changes once Stripe confirms the
    payment (/verify on the way back, or the webhook). For someone already subscribed, nothing is charged here:
    the answer is a quote (mode "switch": what changing plan costs or credits right now) for /switch."""
    plan = _plan(body.plan_id)

    with db.session() as s:
        user = _user(s, cu)
        if billing.configured():
            try:
                sub = _live_subscription(user)
                if sub:
                    meta = sub.get("metadata") or {}
                    if (meta.get("plan"), meta.get("interval")) == (plan["id"], body.interval):
                        raise _fail(status.HTTP_400_BAD_REQUEST, "same_plan", "You're already on this plan.")
                    when = int(time.time())
                    quote = billing.preview_switch(sub, plan, body.interval, when)
                    return {"mode": "switch", "plan": plan["name"], "interval": body.interval,
                            "proration_date": when, "currency": quote["currency"],
                            "charge_now": quote["amount_due"], "credit": max(0, -quote["total"])}
            except billing.BillingError as e:
                raise _billing_fail(e) from None
            base = settings().public_url.rstrip("/")
            try:
                session = billing.create_checkout(
                    plan, body.interval, user_id=user.id, customer=user.stripe_customer_id, email=user.email,
                    success_url=f"{base}/subscription?session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{base}/subscription?checkout=cancelled")
            except billing.BillingError as e:
                raise _billing_fail(e) from None
            return {"mode": "stripe", "url": session["url"], "session_id": session["id"]}

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
def verify_checkout(body: VerifyBody, cu: CurrentUser = Depends(require_csrf)) -> dict:
    """The return from Stripe Checkout. Everything is re-read from Stripe with our secret key; the browser only
    says which session to look at, and it must be this user's."""
    try:
        session = billing.fetch_session(body.session_id)
    except billing.BillingError as e:
        if str(e).startswith("HTTP 4"):         # Stripe doesn't know that session (a typo or another account's)
            raise _fail(status.HTTP_400_BAD_REQUEST, "bad_session", "That checkout couldn't be found.") from None
        raise _billing_fail(e) from None
    if str(session.get("client_reference_id") or "") != str(cu.id) or session.get("mode") != "subscription":
        raise _fail(status.HTTP_400_BAD_REQUEST, "bad_session", "That checkout isn't for this account.")
    sub_id = session.get("subscription")
    if session.get("status") != "complete" or not sub_id:
        return {"ok": True, "outcome": "ignored", "pending": True}     # not paid (yet): nothing changes
    try:
        sub = billing.fetch_subscription(sub_id)
    except billing.BillingError as e:
        raise _billing_fail(e) from None
    with db.session() as s:
        user = _user(s, cu, lock=True)
        before = (user.subscription_tier, user.subscription_status)
        outcome = billing.adopt(user, sub)
        change = _change(user, before, "checkout")
        out = {"ok": True, "outcome": outcome, "tier": user.subscription_tier, "status": user.subscription_status,
               "pending": outcome == "ignored" and sub.get("status") == "incomplete"}
    _log(change)
    return out


@router.post("/switch")
def switch_plan(body: SwitchBody, cu: CurrentUser = Depends(require_csrf)) -> dict:
    """Change the plan of the subscription the user already pays for, prorated: Stripe charges the difference to
    the card on file now, or credits the unused time to future invoices. A declined card changes nothing."""
    plan = _plan(body.plan_id)
    when = body.proration_date
    if not 0 <= time.time() - when <= PRORATION_MAX_AGE:
        raise _fail(status.HTTP_409_CONFLICT, "quote_expired", "That price is out of date. Choose the plan again.")
    with db.session() as s:
        user = _user(s, cu, lock=True)
        try:
            sub = _live_subscription(user)
            if not sub:
                raise _fail(status.HTTP_409_CONFLICT, "no_subscription",
                            "There's no active subscription to change. Choose the plan again to subscribe.")
            updated = billing.switch(sub, plan, body.interval, when)
        except billing.BillingError as e:
            raise _billing_fail(e) from None
        before = (user.subscription_tier, user.subscription_status)
        outcome = billing.apply(user, updated)
        change = _change(user, before, "switch")
        out = {"ok": True, "outcome": outcome, "tier": user.subscription_tier, "status": user.subscription_status,
               "renews_at": _renews(user)}
    _log(change)
    return out


@router.post("/cancel")
def cancel_subscription(cu: CurrentUser = Depends(require_csrf)) -> dict:
    """Cancel at the end of the period already paid for; the webhook downgrades the plan when it ends."""
    with db.session() as s:
        user = _user(s, cu, lock=True)
        if not user.stripe_subscription_id:
            raise _fail(status.HTTP_400_BAD_REQUEST, "no_subscription", "There's no paid subscription to cancel.")
        try:
            sub = billing.cancel_at_period_end(user.stripe_subscription_id)
        except billing.BillingError as e:
            raise _billing_fail(e) from None
        before = (user.subscription_tier, user.subscription_status)
        billing.apply(user, sub)
        change = _change(user, before, "cancel")
        out = {"ok": True, "tier": user.subscription_tier, "status": user.subscription_status, "renews_at": _renews(user)}
    _log(change)
    return out


@public_router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request) -> dict:
    """Stripe events. Public (Stripe calls it), so the signature is the only authority."""
    raw = await request.body()
    if not billing.webhook_event_ok(raw, request.headers.get("stripe-signature", "")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad signature")
    try:
        event = json.loads(raw)
        kind, obj = event["type"], event["data"]["object"]
    except (ValueError, KeyError, TypeError):
        return {"ok": True, "outcome": "ignored"}

    if kind == "checkout.session.completed":
        if obj.get("mode") != "subscription" or not obj.get("subscription"):
            return {"ok": True, "outcome": "ignored"}
        try:
            sub = billing.fetch_subscription(obj["subscription"])
        except billing.BillingError:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Stripe unavailable") from None   # Stripe retries
        uid = str(obj.get("client_reference_id") or "")
    elif kind in _SUB_EVENTS:
        sub, uid = obj, ""
    else:
        return {"ok": True, "outcome": "ignored"}

    with db.session() as s:
        # FOR UPDATE: Stripe often sends checkout.session.completed and customer.subscription.created together;
        # the second waits here for the first to finish, then finds nothing left to change (one activity entry)
        user = s.scalars(select(User).where(User.stripe_subscription_id == sub.get("id")).with_for_update()).first()
        if user:
            how = billing.apply
        else:
            # not anyone's current subscription: a new one, for the user our checkout wrote into it
            owner = int(uid) if uid.isdigit() else billing.owner_id(sub)
            if owner and billing.owner_id(sub) not in (None, owner):
                owner = None                    # the checkout and the subscription disagree on whose it is
            user = s.get(User, owner, with_for_update=True) if owner else None
            how = billing.adopt
        if not user:
            log.info("stripe %s for an unknown subscription", kind)
            return {"ok": True, "outcome": "ignored"}
        before = (user.subscription_tier, user.subscription_status)
        outcome = how(user, sub)
        change = _change(user, before, f"webhook:{kind}")
    _log(change)
    return {"ok": True, "outcome": outcome}
