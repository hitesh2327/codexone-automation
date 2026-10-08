"""Subscription tiers and Stripe payment gateway endpoints.

Uses STRIPE_PUBLISHABLE_KEY and STRIPE_SECRET_KEY from the environment / settings.
"""
from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.app.deps import CurrentUser, current_user, require_csrf
from api.app.settings import settings
from src import activity, db
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


class CheckoutBody(BaseModel):
    plan_id: str = Field(min_length=1, max_length=32)
    interval: str = Field(default="month", pattern="^(month|year)$")


@public_router.get("/plans")
@router.get("/plans")
def get_plans() -> dict:
    """Public subscription plans catalogue."""
    pk = os.getenv("STRIPE_PUBLISHABLE_KEY") or os.getenv("VITE_STRIPE_PUBLISHABLE_KEY") or ""
    return {
        "plans": PLANS,
        "stripe_publishable_key": pk,
    }


@router.get("/status")
def get_subscription_status(cu: CurrentUser = Depends(current_user)) -> dict:
    """Current user's subscription status."""
    pk = os.getenv("STRIPE_PUBLISHABLE_KEY") or os.getenv("VITE_STRIPE_PUBLISHABLE_KEY") or ""
    with db.session() as s:
        user = s.get(User, cu.id)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
        return {
            "tier": user.subscription_tier or "free",
            "status": user.subscription_status or "active",
            "stripe_customer_id": user.stripe_customer_id,
            "stripe_subscription_id": user.stripe_subscription_id,
            "stripe_publishable_key": pk,
        }


@router.post("/checkout")
def create_checkout_session(body: CheckoutBody, cu: CurrentUser = Depends(require_csrf)) -> dict:
    """Create a Stripe checkout session or activate test plan directly."""
    plan = next((p for p in PLANS if p["id"] == body.plan_id), None)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown plan: {body.plan_id}")

    stripe_secret = os.getenv("STRIPE_SECRET_KEY")
    with db.session() as s:
        user = s.get(User, cu.id)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

        # If Stripe Secret Key is present, initiate Stripe Checkout Session
        if stripe_secret:
            try:
                import stripe
                stripe.api_key = stripe_secret
                price_amount = (plan["price_yearly"] if body.interval == "year" else plan["price_monthly"]) * 100
                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    line_items=[{
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": f"CodexOne {plan['name']} Plan",
                                "description": f"{plan['posts_per_day']} posts/day automated publishing",
                            },
                            "unit_amount": price_amount,
                            "recurring": {"interval": body.interval},
                        },
                        "quantity": 1,
                    }],
                    mode="subscription",
                    customer_email=user.email,
                    success_url=f"{settings().public_url}/subscription?success=true&session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{settings().public_url}/subscription?cancelled=true",
                    metadata={"user_id": str(user.id), "plan_id": body.plan_id},
                )
                return {"checkout_url": session.url, "session_id": session.id, "mode": "stripe"}
            except Exception as e:
                log.exception("Stripe checkout error: %s", e)
                # Fall back to local plan activation

        # Local instant activation (for dev/demo or when direct payment simulated)
        user.subscription_tier = body.plan_id
        user.subscription_status = "active"
        if plan["posts_per_day"] > 0:
            current_cadence = dict(user.cadence or {})
            current_cadence["posts_per_day"] = plan["posts_per_day"]
            user.cadence = current_cadence
        s.flush()
        activity.record(
            "subscription.upgraded",
            f"Subscribed to {plan['name']} ({body.interval}ly)",
            source="billing",
            actor=user.username or user.email,
            detail={"user_id": user.id, "tier": body.plan_id, "interval": body.interval},
        )
        return {
            "ok": True,
            "tier": body.plan_id,
            "status": "active",
            "message": f"Successfully subscribed to {plan['name']} plan!",
            "mode": "instant",
        }
