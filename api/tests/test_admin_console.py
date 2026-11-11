"""Comprehensive tests for the Admin & Stakeholder Console (/api/admin/*).

Covers:
- Zero-trust RBAC (401 unauthenticated, 403 client, 200 admin/owner)
- Live MRR/ARR calculation, stuck job detection, YouTube quota meter
- Tenant search/pagination, unit economics (COGS vs revenue), suspend + token invalidation, bonus quota
- Stuck job reconciliation
- Failed publish DLQ grouping & single/bulk retry
- Global emergency kill-switches (503 on /api/auth/signup and /api/generate) & feature flags CRUD + TTL cache
- Strictly audited 15-min read-only Support Impersonation boundaries + exit
- GST-ready CSV export (CGST/SGST/IGST/Export)
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.app import ratelimit
from api.app.main import create_app
from api.app.security import hash_password
from api.tests.conftest import GOOD
from src import actions, db, flags, plan_limits
from src.db.models import ActivityLog, GenerationJob, Post, Setting, User


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_client() -> TestClient:
    return TestClient(create_app())


def _login_client(tc: TestClient, username: str, password: str) -> dict:
    r = tc.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    tc.headers["X-CSRF-Token"] = data["csrf"]
    return data


def _make_user(
    *,
    username: str,
    email: str,
    role: str = "client",
    tier: str = "free",
    sub_status: str = "active",
    is_active: bool = True,
    billing_country: str | None = None,
    billing_state: str | None = None,
    billing_gstin: str | None = None,
) -> int:
    with db.session() as s:
        u = User(
            username=username,
            email=email,
            name=username,
            password_hash=hash_password("strong pass 1234!"),
            role=role,
            subscription_tier=tier,
            subscription_status=sub_status,
            is_active=is_active,
            billing_country=billing_country,
            billing_state=billing_state,
            billing_gstin=billing_gstin,
            config_completed=True,
        )
        s.add(u)
        s.flush()
        return u.id


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    ratelimit.login_limiter.clear()
    ratelimit.otp_limiter.clear()
    flags.reset()
    monkeypatch.setenv("SELLER_GSTIN", "27AAPFU0939F1ZV")
    with db.session() as s:
        for model in (GenerationJob, Post, ActivityLog):
            s.execute(delete(model))
        s.execute(delete(Setting).where(Setting.key.in_(("kill_switches", "feature_flags", "tenant_bonus_quotas"))))
        # Keep only the seeded owner/admin (username == "admin")
        for u in s.scalars(select(User)).all():
            if u.username != "admin":
                s.delete(u)
            else:
                u.subscription_tier = "free"
                u.subscription_status = "active"
                u.is_active = True
                u.token_version = 0
    yield
    flags.reset()


# --------------------------------------------------------------------------- #
# 1. Zero-Trust RBAC (401 / 403 / 200)
# --------------------------------------------------------------------------- #
def test_admin_rbac_401_and_403(client):
    endpoints = [
        ("GET", "/api/admin/overview"),
        ("GET", "/api/admin/tenants"),
        ("GET", "/api/admin/jobs"),
        ("GET", "/api/admin/failures"),
        ("GET", "/api/admin/safety"),
        ("GET", "/api/admin/flags"),
        ("GET", "/api/admin/revenue/gst-export"),
        ("GET", "/api/admin/audit"),
    ]
    for method, path in endpoints:
        r = client.request(method, path)
        assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}"

    # Client account gets 403 on all /api/admin/* endpoints
    cid = _make_user(username="creator1", email="c1@example.com", role="client")
    with _new_client() as cc:
        _login_client(cc, "creator1", "strong pass 1234!")
        for method, path in endpoints:
            r = cc.request(method, path)
            assert r.status_code == 403, f"client {method} {path} expected 403, got {r.status_code}"
        assert cc.post(f"/api/admin/tenants/{cid}/suspend", json={"active": False}).status_code == 403
        assert cc.post(f"/api/admin/tenants/{cid}/bonus-quota", json={"reels": 5}).status_code == 403
        assert cc.put("/api/admin/safety", json={"generation": True}).status_code == 403
        assert cc.put("/api/admin/flags", json={"key": "x", "enabled": True}).status_code == 403
        assert cc.post("/api/admin/jobs/reconcile", json={}).status_code == 403
        assert cc.post("/api/admin/failures/retry", json={"post_ids": ["p1"]}).status_code == 403

    # Admin role succeeds
    _make_user(username="opsadmin", email="ops@example.com", role="admin")
    with _new_client() as ac:
        _login_client(ac, "opsadmin", "strong pass 1234!")
        assert ac.get("/api/admin/overview").status_code == 200


# --------------------------------------------------------------------------- #
# 2. Overview MRR / ARR, Stuck Jobs, YouTube Quota
# --------------------------------------------------------------------------- #
def test_overview_mrr_stuck_jobs_and_yt_quota(authed):
    u1 = _make_user(username="u_starter", email="u1@example.com", tier="starter", sub_status="active")   # 1499
    u2 = _make_user(username="u_creator", email="u2@example.com", tier="creator", sub_status="trialing") # 2999
    _make_user(username="u_lite", email="u3@example.com", tier="lite", sub_status="active")              # 699
    _make_user(username="u_pro_dead", email="u4@example.com", tier="pro", sub_status="canceled")         # 0

    now = _utc_now()
    with db.session() as s:
        s.add(GenerationJob(
            id="jobrunstuck1", trigger="dashboard", user_id=u1, status="running",
            phase="rendering", created_at=now - timedelta(minutes=45), started_at=now - timedelta(minutes=40),
        ))
        s.add(GenerationJob(
            id="jobqstuck2", trigger="dashboard", user_id=u2, status="queued",
            created_at=now - timedelta(minutes=15),
        ))
        s.add(GenerationJob(
            id="jobok3", trigger="scheduled", user_id=u1, status="succeeded",
            created_at=now - timedelta(hours=2), started_at=now - timedelta(hours=2), finished_at=now - timedelta(hours=1, minutes=50),
        ))
        s.add(Post(
            id="20261111-r-yt1", kind="reel", date=date.today(), topic="YT Post", category="AI",
            post_dir="output/2026-11-11/yt-post/reel", caption="Cap", status="published",
            published_at=now, platforms={"yt": {"status": "published", "id": "yt123"}}, user_id=u1,
        ))
        s.add(Post(
            id="20261111-c-fail1", kind="carousel", date=date.today(), topic="Broken", category="AI",
            post_dir="output/2026-11-11/broken/carousel", caption="Cap", status="failed",
            error="IG error 190: token expired", attempts=3,
            platforms={"ig": {"status": "failed", "error": "IG error 190: token expired", "attempts": 3}}, user_id=u2,
        ))

    r = authed.get("/api/admin/overview")
    assert r.status_code == 200
    data = r.json()
    expected_mrr = 1499 + 2999 + 699
    assert data["revenue"]["mrr_inr"] == expected_mrr
    assert data["revenue"]["arr_inr"] == expected_mrr * 12
    assert data["revenue"]["active_subscribers"] == 3
    assert data["jobs"]["stuck_count"] == 2
    assert data["jobs"]["counts_24h"]["succeeded"] == 1
    assert data["failures"]["failed_publishes_count"] == 1
    assert data["failures"]["ig_needs_reauth_count"] == 1
    assert data["youtube_quota"]["uploads_today"] == 1
    assert data["youtube_quota"]["units_used"] == 1600


# --------------------------------------------------------------------------- #
# 3. Tenants: Search, Unit Economics, Suspend + Token Invalidation, Bonus Quota
# --------------------------------------------------------------------------- #
def test_tenants_suspend_token_invalidation_and_bonus_quota(authed):
    uid = _make_user(username="burnuser", email="burn@example.com", tier="lite", sub_status="active")
    now = _utc_now()
    with db.session() as s:
        for i in range(3):
            s.add(Post(
                id=f"20261111-c-b{i}", kind="carousel", date=date.today(), topic=f"T{i}", category="AI",
                post_dir=f"output/2026-11-11/t{i}/carousel", caption="Cap", status="published",
                version=1, created_at=now, user_id=uid,
            ))

    res = authed.get("/api/admin/tenants?q=burnuser")
    assert res.status_code == 200
    t = res.json()["tenants"][0]
    assert t["username"] == "burnuser"
    assert t["quota_used"]["carousels"] == 3
    assert t["cogs_inr"] == 27  # 3 * 9
    assert t["revenue_inr"] == 699
    assert t["margin_pct"] == round((699 - 27) / 699 * 100, 1)

    # Bonus quota adds cleanly and reflects in plan_limits.summary
    bq = authed.post(f"/api/admin/tenants/{uid}/bonus-quota", json={"reels": 5, "carousels": 10, "reason": "Promo gift"})
    assert bq.status_code == 200
    assert bq.json()["bonus_quota"] == {"reels": 5, "carousels": 10}
    with db.session() as s:
        u_obj = s.get(User, uid)
        summ = plan_limits.summary(u_obj)
        assert summ["quota"] == {"reels": 5, "carousels": 40}

    # Client signs in, then gets suspended -> existing session immediately invalid (401)
    with _new_client() as cc:
        _login_client(cc, "burnuser", "strong pass 1234!")
        assert cc.get("/api/session/ping").status_code == 200

        sr = authed.post(f"/api/admin/tenants/{uid}/suspend", json={"active": False, "reason": "Abuse"})
        assert sr.status_code == 200
        assert sr.json()["is_active"] is False
        assert sr.json()["token_version"] >= 1
        assert cc.get("/api/session/ping").status_code == 401

    # Cannot suspend self or owner
    me_id = authed.get("/api/auth/me").json()["id"]
    assert authed.post(f"/api/admin/tenants/{me_id}/suspend", json={"active": False}).status_code == 400
    # Restore works
    assert authed.post(f"/api/admin/tenants/{uid}/suspend", json={"active": True, "reason": "Resolved"}).status_code == 200

    # Verify audit trail recorded
    audit = authed.get("/api/admin/audit").json()["events"]
    events = [e["event"] for e in audit]
    assert "admin.tenant.suspended" in events
    assert "admin.tenant.reactivated" in events
    assert "admin.tenant.bonus_quota" in events


# --------------------------------------------------------------------------- #
# 4. Stuck Jobs & Reconcile + DLQ Bulk Retry
# --------------------------------------------------------------------------- #
def test_reconcile_stuck_jobs_and_dlq_bulk_retry(authed):
    uid = _make_user(username="dlquser", email="dlq@example.com", tier="creator", sub_status="active")
    now = _utc_now()
    with db.session() as s:
        s.add(GenerationJob(
            id="stuck001", trigger="dashboard", user_id=uid, status="running",
            phase="writing", created_at=now - timedelta(minutes=50), started_at=now - timedelta(minutes=45),
        ))
        s.add(Post(
            id="fail-ig-1", kind="carousel", date=date.today(), topic="IG 1", category="AI",
            post_dir="output/1", caption="c", status="failed", attempts=3,
            error="IG error 190/None: token expired",
            platforms={"ig": {"status": "failed", "error": "IG error 190", "attempts": 3, "at": "2026-11-11T00:00:00+00:00"}},
            user_id=uid,
        ))
        s.add(Post(
            id="fail-yt-2", kind="reel", date=date.today(), topic="YT 2", category="AI",
            post_dir="output/2", caption="c", status="failed", attempts=1,
            error="YouTube quotaExceeded",
            platforms={"yt": {"status": "failed", "error": "quotaExceeded", "attempts": 1, "quota_exhausted": True, "at": "2026-11-11T00:00:00+00:00"}},
            user_id=uid,
        ))

    jobs_res = authed.get("/api/admin/jobs?stuck_only=true")
    assert jobs_res.status_code == 200
    assert [j["id"] for j in jobs_res.json()["jobs"]] == ["stuck001"]

    rec_res = authed.post("/api/admin/jobs/reconcile", json={})
    assert rec_res.status_code == 200
    assert "stuck001" in rec_res.json()["released"]
    with db.session() as s:
        assert s.get(GenerationJob, "stuck001").status == "failed"

    dlq = authed.get("/api/admin/failures").json()
    assert dlq["total"] == 2
    sigs = {g["signature"] for g in dlq["groups"]}
    assert "IG_TOKEN_190" in sigs
    assert "YT_QUOTA_EXCEEDED" in sigs

    # Bulk retry IG_TOKEN_190 signature
    retry_res = authed.post("/api/admin/failures/retry", json={"signature": "IG_TOKEN_190"})
    assert retry_res.status_code == 200
    assert retry_res.json()["retried"] == ["fail-ig-1"]
    with db.session() as s:
        p1 = s.get(Post, "fail-ig-1")
        assert p1.status == "approved"
        assert p1.attempts == 0
        assert p1.error is None
        assert p1.platforms["ig"]["attempts"] == 0

    # Single retry YT post clears quota_exhausted
    retry_yt = authed.post("/api/admin/failures/retry", json={"post_ids": ["fail-yt-2"]})
    assert retry_yt.status_code == 200
    with db.session() as s:
        p2 = s.get(Post, "fail-yt-2")
        assert p2.status == "approved"
        assert "quota_exhausted" not in p2.platforms["yt"]


# --------------------------------------------------------------------------- #
# 5. Kill-Switches (503 Enforcement) & Feature Flags
# --------------------------------------------------------------------------- #
def test_kill_switches_503_and_feature_flags(authed):
    # Trip signup kill-switch -> /api/auth/signup returns 503
    assert authed.put("/api/admin/safety", json={"signups": True, "reason": "Bot wave"}).status_code == 200
    with _new_client() as anon:
        r = anon.post(
            "/api/auth/signup",
            json={"username": "newcreator", "email": "new@example.com", "password": "unique pass 999!"},
        )
        assert r.status_code == 503

    # Clear signups, trip generation -> /api/generate returns 503
    assert authed.put("/api/admin/safety", json={"signups": False, "generation": True}).status_code == 200
    gen_res = authed.post("/api/generate", json={"slot": "auto", "idempotency_key": "kill-switch-test-01"})
    assert gen_res.status_code == 503
    assert gen_res.json()["detail"]["code"] == "generation_paused"

    # Trip publishing -> actions.publishing_enabled() turns False
    assert authed.put("/api/admin/safety", json={"publishing": True}).status_code == 200
    assert actions.publishing_enabled() is False
    assert authed.put("/api/admin/safety", json={"generation": False, "publishing": False}).status_code == 200
    assert actions.publishing_enabled() is True

    # Feature flags CRUD + evaluation
    f_put = authed.put(
        "/api/admin/flags",
        json={"key": "ai_editor_v3", "enabled": True, "rollout_pct": 100, "description": "Beta editor"},
    )
    assert f_put.status_code == 200
    assert any(f["key"] == "ai_editor_v3" and f["enabled"] for f in f_put.json()["flags"])
    assert flags.is_enabled("ai_editor_v3", type("U", (), {"id": 42, "subscription_tier": "pro"})()) is True

    f_del = authed.delete("/api/admin/flags/ai_editor_v3")
    assert f_del.status_code == 200
    assert not any(f["key"] == "ai_editor_v3" for f in f_del.json()["flags"])


# --------------------------------------------------------------------------- #
# 6. Support Impersonation Security Boundaries
# --------------------------------------------------------------------------- #
def test_support_impersonation_boundaries_and_exit(authed):
    admin_id = _make_user(username="otheradmin", email="oa@example.com", role="admin")
    client_id = _make_user(username="helpee", email="helpee@example.com", role="client")
    susp_id = _make_user(username="suspended_c", email="sc@example.com", role="client", is_active=False)

    # Reason < 10 chars rejected
    assert authed.post(f"/api/admin/tenants/{client_id}/impersonate", json={"reason": "short"}).status_code == 422
    # Cannot impersonate another admin/owner
    assert authed.post(f"/api/admin/tenants/{admin_id}/impersonate", json={"reason": "Ticket #101: debug admin"}).status_code == 403
    # Cannot impersonate suspended client
    assert authed.post(f"/api/admin/tenants/{susp_id}/impersonate", json={"reason": "Ticket #102: inspect suspended"}).status_code == 409

    # Start impersonation on active client
    with _new_client() as op:
        _login_client(op, GOOD["username"], GOOD["password"])
        imp = op.post(
            f"/api/admin/tenants/{client_id}/impersonate",
            json={"reason": "Ticket #103: inspecting broken YouTube link"},
        )
        assert imp.status_code == 200
        body = imp.json()
        assert body["read_only"] is True
        assert body["user"]["username"] == "helpee"
        assert body["user"]["impersonated_by"] is not None

        # Update CSRF token to the impersonation token's CSRF
        me = op.get("/api/auth/me").json()
        assert me["username"] == "helpee"
        assert me["impersonation_read_only"] is True
        op.headers["X-CSRF-Token"] = me["csrf"]

        # Reads work
        assert op.get("/api/posts").status_code == 200
        # Admin endpoints are forbidden while impersonating
        assert op.get("/api/admin/overview").status_code == 403
        # Write mutations are blocked (403 impersonation_read_only)
        w1 = op.post("/api/generate", json={"slot": "auto", "idempotency_key": "imp-blocked-001"})
        assert w1.status_code == 403
        assert w1.json()["detail"]["code"] == "impersonation_read_only"
        w2 = op.post("/api/auth/logout")
        assert w2.status_code == 403

        # Exit impersonation succeeds and restores admin session
        ex = op.post("/api/admin/impersonation/exit")
        assert ex.status_code == 200
        restored = ex.json()["user"]
        assert restored["username"] == "admin"
        assert "impersonated_by" not in restored
        op.headers["X-CSRF-Token"] = restored["csrf"]
        assert op.get("/api/admin/overview").status_code == 200

    # Verify both start and exit were logged immutably
    events = [e["event"] for e in authed.get("/api/admin/audit").json()["events"]]
    assert "admin.impersonation.start" in events
    assert "admin.impersonation.exit" in events


# --------------------------------------------------------------------------- #
# 7. GST CSV Export
# --------------------------------------------------------------------------- #
def test_gst_csv_export(authed):
    # Seller is 27 (Maharashtra)
    _make_user(
        username="mh_client", email="mh@example.com", tier="starter", sub_status="active",
        billing_country="IN", billing_state="27", billing_gstin="27AAACM0000A1Z5",
    )
    _make_user(
        username="ka_client", email="ka@example.com", tier="creator", sub_status="active",
        billing_country="IN", billing_state="29",
    )
    _make_user(
        username="us_client", email="us@example.com", tier="pro", sub_status="active",
        billing_country="US",
    )

    r = authed.get("/api/admin/revenue/gst-export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(r.text)))
    by_user = {row["username"]: row for row in rows}
    assert by_user["mh_client"]["supply_type"] == "INTRA_STATE"
    assert float(by_user["mh_client"]["cgst_inr"]) > 0
    assert float(by_user["mh_client"]["sgst_inr"]) > 0
    assert float(by_user["mh_client"]["igst_inr"]) == 0.0

    assert by_user["ka_client"]["supply_type"] == "INTER_STATE"
    assert float(by_user["ka_client"]["igst_inr"]) == round(2999 * 0.18, 2)
    assert float(by_user["ka_client"]["cgst_inr"]) == 0.0

    assert by_user["us_client"]["supply_type"] == "EXPORT"
    assert float(by_user["us_client"]["export_inr"]) == 5999.0
    assert float(by_user["us_client"]["igst_inr"]) == 0.0
