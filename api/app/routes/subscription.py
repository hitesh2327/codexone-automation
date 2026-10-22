"""Subscription plans, billing details, GST quotes and Razorpay checkout (src/billing.py holds the gateway logic).

The page asks for a quote first (/quote: itemised, with GST, nothing charged), shows it, and only then starts
checkout (/checkout recomputes the same quote and refuses if the total changed). A plan changes only from a
subscription Razorpay itself confirms: the signed checkout callback (/verify, which re-fetches it with our key)
or the signed webhook. Both go through billing.apply with the user's row locked (SELECT ... FOR UPDATE), so two
events arriving together are handled one after the other. Without Razorpay keys, checkout refuses (503); a
gateway error returns 502; neither ever changes a plan. BILLING_DEV_INSTANT=true allows instant activation for
local development only: it is ignored on a real deployment (SSM_PREFIX set or COOKIE_SECURE on).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from api.app.deps import CurrentUser, current_user, require_csrf
from api.app.settings import settings
from src import activity, billing, db, plan_limits
from src.plans import PLANS
from src.db.models import User

log = logging.getLogger("codexone.api.subscription")
public_router = APIRouter(prefix="/subscription", tags=["subscription"])
router = APIRouter(prefix="/subscription", tags=["subscription"])


_UNAVAILABLE = "Payments aren't set up yet, so plans can't be changed right now."
_GATEWAY = ("Couldn't reach the payment provider. Nothing was charged and your plan didn't change. "
            "Try again in a few minutes.")
_SCHEDULED = "A plan change is already scheduled for your renewal date."
QUOTE_MAX_AGE = 30 * 60          # a quote must be paid within 30 minutes of seeing it
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


def _dev_instant() -> bool:
    """Instant plan activation without payment: local development only, never on a deployment."""
    deployed = settings().cookie_secure or bool((os.getenv("SSM_PREFIX") or "").strip())
    return (os.getenv("BILLING_DEV_INSTANT") or "").strip().lower() == "true" and not deployed


def _fail(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(code, detail={"code": error, "message": message})


def _billing_fail(e: billing.BillingError) -> HTTPException:
    if e.code == "payments_unavailable":
        return _fail(status.HTTP_503_SERVICE_UNAVAILABLE, e.code, _UNAVAILABLE)
    return _fail(status.HTTP_502_BAD_GATEWAY, "payment_error", _GATEWAY)


def _user(s, cu: CurrentUser, lock: bool = False) -> User:
    """The signed-in user's row; lock=True holds it (FOR UPDATE) until the session ends, for billing changes."""
    user = s.get(User, cu.id, with_for_update=lock)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def _plan(plan_id: str) -> dict:
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown plan: {plan_id}")
    return plan


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


def _details(user: User) -> dict:
    return {"name": user.billing_name or user.name or "", "country": user.billing_country,
            "state": user.billing_state, "gstin": user.billing_gstin, "complete": bool(user.billing_country)}


class PlanBody(BaseModel):
    plan_id: str = Field(min_length=1, max_length=32)
    interval: str = Field(default="month", pattern="^(month|year)$")


class CheckoutBody(PlanBody):
    quote_at: int = Field(default=0, ge=0)        # from /quote, so the charge is exactly what was shown
    expected_total: int = Field(default=0, ge=0)  # paise the page showed; a different total is refused


class VerifyBody(BaseModel):
    razorpay_payment_id: str = Field(min_length=1, max_length=64)
    razorpay_subscription_id: str = Field(min_length=1, max_length=64)
    razorpay_signature: str = Field(min_length=1, max_length=128)


class DetailsBody(BaseModel):
    name: str = Field(default="", max_length=120)
    country: str = Field(min_length=2, max_length=2)
    state: str | None = Field(default=None, max_length=2)
    gstin: str | None = Field(default=None, max_length=15)


# --------------------------------------------------------------------------- #
# Catalogue, status, billing details
# --------------------------------------------------------------------------- #
@public_router.get("/plans")
@router.get("/plans")
def get_plans() -> dict:
    """Public subscription plans catalogue."""
    return {"plans": PLANS, "currency": billing.CURRENCY, "payments_enabled": billing.configured(),
            "gst": {"enabled": billing.gst_enabled(), "rate": billing.GST_RATE}}


@public_router.get("/states")
def get_states() -> dict:
    """Indian states and union territories with their GST state codes (for the billing details form)."""
    return {"states": [{"code": c, "name": n} for c, n in sorted(billing.STATES.items(), key=lambda kv: kv[1])]}


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
            "change_scheduled": user.subscription_status == "changing",
            "payments_enabled": billing.configured(),
            "billing": _details(user),
            "usage": plan_limits.summary(user),
        }


@router.put("/billing-details")
def put_billing_details(body: DetailsBody, cu: CurrentUser = Depends(require_csrf)) -> dict:
    country = body.country.strip().upper()
    if not _COUNTRY_RE.match(country):
        raise _fail(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_country", "Choose your country.")
    state = (body.state or "").strip() or None
    gstin = (body.gstin or "").strip().upper() or None
    if country == "IN":
        if state not in billing.STATES:
            raise _fail(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_state", "Choose your state.")
        if gstin and not billing.valid_gstin(gstin, state):
            raise _fail(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_gstin",
                        "That GSTIN isn't valid for the state you chose. Check it, or leave it empty.")
    else:
        state, gstin = None, None
    with db.session() as s:
        user = _user(s, cu, lock=True)
        user.billing_name = " ".join(body.name.split())
        user.billing_country, user.billing_state, user.billing_gstin = country, state, gstin
        return _details(user)


# --------------------------------------------------------------------------- #
# Quote -> checkout -> verify
# --------------------------------------------------------------------------- #
def _quote(user: User, plan: dict, interval: str, now: int) -> dict:
    if not user.billing_country:
        raise _fail(status.HTTP_409_CONFLICT, "billing_details_required", "Add your billing details first.")
    try:
        q = billing.quote(user, plan, interval, now)
    except ValueError:
        raise _fail(status.HTTP_400_BAD_REQUEST, "same_plan", "You're already on this plan.") from None
    except billing.BillingError as e:
        raise _billing_fail(e) from None
    return {**q, "plan": plan["id"], "plan_name": plan["name"], "interval": interval, "quote_at": now}


@router.post("/quote")
def quote_change(body: PlanBody, cu: CurrentUser = Depends(current_user)) -> dict:
    """What choosing this plan costs right now, itemised with GST. Nothing is charged."""
    plan = _plan(body.plan_id)
    if not billing.configured():
        raise _fail(status.HTTP_503_SERVICE_UNAVAILABLE, "payments_unavailable", _UNAVAILABLE)
    with db.session() as s:
        user = _user(s, cu)
        if user.subscription_status == "changing":
            raise _fail(status.HTTP_409_CONFLICT, "change_scheduled", _SCHEDULED)
        return _quote(user, plan, body.interval, int(time.time()))


@router.post("/checkout")
def create_checkout(body: CheckoutBody, cu: CurrentUser = Depends(require_csrf)) -> dict:
    """Start the Razorpay subscription for a quote the user has seen. The browser opens Razorpay Checkout with it;
    the plan changes only once Razorpay confirms (/verify or the webhook)."""
    plan = _plan(body.plan_id)
    with db.session() as s:
        user = _user(s, cu, lock=True)
        if billing.configured():
            if not 0 <= time.time() - body.quote_at <= QUOTE_MAX_AGE:
                raise _fail(status.HTTP_409_CONFLICT, "quote_expired", "That price is out of date. Choose the plan again.")
            if user.subscription_status == "changing":
                raise _fail(status.HTTP_409_CONFLICT, "change_scheduled", _SCHEDULED)
            q = _quote(user, plan, body.interval, body.quote_at)
            if q["total_now"] != body.expected_total:
                raise _fail(status.HTTP_409_CONFLICT, "quote_changed",
                            "The price changed since you looked. Review it again.")
            try:
                sub = billing.start(user, plan, body.interval, q)
            except billing.BillingError as e:
                raise _billing_fail(e) from None
            user.razorpay_pending_subscription_id = sub["id"]
            return {"mode": "razorpay", "key_id": billing.key_id(), "subscription_id": sub["id"],
                    "kind": q["kind"], "plan": plan["name"], "total_now": q["total_now"],
                    "email": user.email or "", "name": user.billing_name or user.name or ""}

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
        user = _user(s, cu, lock=True)
        if body.razorpay_subscription_id not in (user.razorpay_pending_subscription_id, user.razorpay_subscription_id):
            raise _fail(status.HTTP_400_BAD_REQUEST, "bad_signature", "That payment isn't for this account.")
        try:
            sub = billing.fetch_subscription(body.razorpay_subscription_id)
        except billing.BillingError as e:
            raise _billing_fail(e) from None
        before = (user.subscription_tier, user.subscription_status)
        outcome = billing.apply(user, sub)
        change = _change(user, before, "checkout")
        out = {"ok": True, "outcome": outcome, "tier": user.subscription_tier, "status": user.subscription_status,
               "renews_at": _renews(user)}
    _log(change)
    return out


@router.post("/cancel")
def cancel_subscription(cu: CurrentUser = Depends(require_csrf)) -> dict:
    """Cancel at the end of the period already paid for; the webhook downgrades the plan when it ends."""
    with db.session() as s:
        user = _user(s, cu, lock=True)
        if not user.razorpay_subscription_id:
            raise _fail(status.HTTP_400_BAD_REQUEST, "no_subscription", "There's no paid subscription to cancel.")
        if user.subscription_status == "changing":
            raise _fail(status.HTTP_409_CONFLICT, "change_scheduled", _SCHEDULED)
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
        # FOR UPDATE: Razorpay often sends several events for one change together; the next one waits here for
        # the previous to finish, then finds nothing left to change (one activity entry per change)
        user = s.scalars(select(User).where(or_(User.razorpay_subscription_id == sub_id,
                                                User.razorpay_pending_subscription_id == sub_id))
                         .with_for_update()).first()
        if not user:
            log.info("razorpay %s for an unknown subscription", event.get("event"))
            return {"ok": True, "outcome": "ignored"}
        before = (user.subscription_tier, user.subscription_status)
        outcome = billing.apply(user, sub)
        change = _change(user, before, f"webhook:{event.get('event')}")
    _log(change)
    return {"ok": True, "outcome": outcome}
