"""Tests for multi-user subscription tiers, Stripe checkout, taste, and cadence preferences."""
from __future__ import annotations

import pytest
from src import db
from src.db.models import User


def test_public_subscription_plans(client):
    r = client.get("/api/subscription/plans")
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data
    assert len(data["plans"]) >= 3
    starter = next(p for p in data["plans"] if p["id"] == "starter")
    creator = next(p for p in data["plans"] if p["id"] == "creator")
    pro = next(p for p in data["plans"] if p["id"] == "pro")
    assert starter["price_monthly"] == 19
    assert creator["popular"] is True
    assert pro["posts_per_day"] == 4


def test_user_subscription_status(authed):
    r = authed.get("/api/subscription/status")
    assert r.status_code == 200
    data = r.json()
    assert "tier" in data
    assert "status" in data


def _tier(c) -> str:
    return c.get("/api/profile").json()["subscription_tier"]


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


def test_gateway_error_never_upgrades(authed, monkeypatch):
    import sys
    from types import SimpleNamespace

    def boom(**_):
        raise RuntimeError("card network down")

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")         # even with dev activation allowed
    monkeypatch.setitem(sys.modules, "stripe", SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(create=boom))))
    before = _tier(authed)
    r = authed.post("/api/subscription/checkout", json={"plan_id": "pro", "interval": "month"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "payment_error"
    assert _tier(authed) == before


def test_user_checkout_instant_activation_in_local_dev(authed, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SSM_PREFIX", raising=False)
    monkeypatch.setenv("BILLING_DEV_INSTANT", "true")
    r = authed.post("/api/subscription/checkout", json={"plan_id": "creator", "interval": "month"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["tier"] == "creator"

    # Verify user profile reflects updated tier and cadence
    prof = authed.get("/api/profile").json()
    assert prof["subscription_tier"] == "creator"
    assert prof["cadence"]["posts_per_day"] == 2


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
