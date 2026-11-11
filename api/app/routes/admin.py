"""Operator & Stakeholder Admin Console API (/api/admin/*).

Zero-trust RBAC: every endpoint on `router` is gated by `require_admin` (`role in ("owner", "admin")`
and not currently inside an impersonation session).
`impersonation_router` hosts `/api/admin/impersonation/exit` so an operator can cleanly exit a
read-only client impersonation session back into their own admin session.
"""
from __future__ import annotations

import csv
import io
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from api.app.deps import CurrentUser, current_user, require_admin
from api.app.routes.auth import _user_out
from api.app.security import IMPERSONATION_TTL_MINUTES, create_impersonation_token, create_session_token, set_session_cookie
from src import actions, activity, billing, db, flags, generation, github_actions, plan_limits
from src.db.models import ActivityLog, ConfigCheck, GenerationJob, Post, User, UserConfigValue
from src.plans import BY_ID, PLANS

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
impersonation_router = APIRouter(prefix="/admin", tags=["admin"])

STUCK_RUNNING_MINUTES = 35
STUCK_QUEUED_MINUTES = 10
COGS_PER_REEL_INR = 13
COGS_PER_CAROUSEL_INR = 9
YT_UNITS_PER_UPLOAD = 1600
YT_DEFAULT_DAILY_QUOTA = 10000
ACTIVE_SUB_STATUSES = ("active", "trialing")
BILLABLE_SUB_STATUSES = ("active", "trialing", "past_due", "canceling", "changing")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _iso(dt: datetime | None) -> str | None:
    d = _aware(dt)
    return d.isoformat(timespec="seconds") if d else None


def _actor(cu: CurrentUser) -> str:
    return cu.username or cu.email or f"admin:{cu.id}"


def _is_job_stuck(job: GenerationJob, now: datetime) -> bool:
    if job.status == "running":
        ref = _aware(job.started_at) or _aware(job.created_at)
        return bool(ref and (now - ref) > timedelta(minutes=STUCK_RUNNING_MINUTES))
    if job.status == "queued":
        ref = _aware(job.created_at)
        return bool(ref and (now - ref) > timedelta(minutes=STUCK_QUEUED_MINUTES))
    return False


def _seller_state() -> str:
    gstin = billing.seller_gstin()
    if gstin:
        return gstin[:2]
    return (os.getenv("SELLER_STATE") or "27").strip()[:2] or "27"


def _gst_row(user: User, plan: dict, seller_state: str) -> dict[str, Any]:
    taxable = float(plan["price_inr_monthly"])
    country = (user.billing_country or "").strip().upper()
    state = (user.billing_state or "").strip()
    cgst = sgst = igst = export = 0.0
    if country and country != "IN":
        supply_type = "EXPORT"
        export = taxable
    elif country == "IN":
        gst_total = round(taxable * 0.18, 2)
        if state and state == seller_state:
            supply_type = "INTRA_STATE"
            cgst = round(gst_total / 2.0, 2)
            sgst = round(gst_total - cgst, 2)
        else:
            supply_type = "INTER_STATE"
            igst = gst_total
    else:
        supply_type = "UNCLASSIFIED"
    total = round(taxable + cgst + sgst + igst, 2)
    return {
        "user_id": user.id,
        "username": user.username or "",
        "email": user.email or "",
        "billing_name": user.billing_name or user.name or "",
        "billing_country": country,
        "billing_state": state,
        "billing_gstin": user.billing_gstin or "",
        "plan_tier": plan["id"],
        "subscription_status": user.subscription_status or "",
        "supply_type": supply_type,
        "taxable_inr": taxable,
        "cgst_inr": cgst,
        "sgst_inr": sgst,
        "igst_inr": igst,
        "export_inr": export,
        "total_inr": total,
    }


def _error_signature(post: Post) -> str:
    parts = [post.error or ""]
    for p, rec in (post.platforms or {}).items():
        if isinstance(rec, dict) and rec.get("status") == "failed":
            parts.append(f"{p}:{rec.get('error', '')}")
    text = " | ".join(parts).lower()
    if "190" in text and ("token" in text or "instagram" in text or "ig" in text or "expired" in text):
        return "IG_TOKEN_190"
    if "2207001" in text or "transient" in text:
        return "IG_TRANSIENT_2207001"
    if "quotaexceeded" in text or "ytquotaexceeded" in text or ("quota" in text and "youtube" in text):
        return "YT_QUOTA_EXCEEDED"
    if "404" in text or "cloudinary" in text or "media url" in text:
        return "MEDIA_404"
    if "plan isn't active" in text or "no active plan" in text:
        return "PLAN_INACTIVE"
    cleaned = re.sub(r"\b[0-9a-f]{6,}\b|\d{4,}", "#", (post.error or "unknown").strip())
    return (cleaned[:48] or "UNKNOWN_FAILURE").upper().replace(" ", "_")


# --------------------------------------------------------------------------- #
# 1. Overview & GST Revenue Export
# --------------------------------------------------------------------------- #
@router.get("/overview")
def get_overview() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)
    today_utc_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seller_state = _seller_state()

    with db.session() as s:
        users = s.scalars(select(User)).all()
        jobs_7d_rows = s.scalars(
            select(GenerationJob).where(GenerationJob.created_at >= cutoff_7d)
        ).all()
        active_jobs = s.scalars(
            select(GenerationJob).where(GenerationJob.status.in_(("queued", "running")))
        ).all()
        failed_posts = s.scalars(select(Post).where(Post.status == "failed")).all()
        published_today_posts = s.scalars(
            select(Post).where(Post.published_at >= today_utc_start)
        ).all()
        ucv_rows = s.execute(
            select(UserConfigValue.key, func.count(func.distinct(UserConfigValue.user_id)))
            .where(UserConfigValue.key.in_(("IG_ACCESS_TOKEN", "YT_REFRESH_TOKEN", "TG_CHAT_ID")))
            .group_by(UserConfigValue.key)
        ).all()
        check_rows = s.scalars(
            select(ConfigCheck).order_by(ConfigCheck.ran_at.desc()).limit(50)
        ).all()

    by_tier: dict[str, dict[str, Any]] = {
        "free": {"id": "free", "name": "Free", "count": 0, "mrr_inr": 0},
        **{p["id"]: {"id": p["id"], "name": p["name"], "count": 0, "mrr_inr": 0} for p in PLANS},
    }
    by_status: dict[str, int] = {}
    mrr_inr = 0
    active_subscribers = 0
    gst_totals = {"taxable_inr": 0.0, "cgst_inr": 0.0, "sgst_inr": 0.0, "igst_inr": 0.0, "export_inr": 0.0, "total_tax_inr": 0.0}

    for u in users:
        tier = (u.subscription_tier or "free").lower()
        st = u.subscription_status or "active"
        by_status[st] = by_status.get(st, 0) + 1
        plan = BY_ID.get(tier)
        if st in ACTIVE_SUB_STATUSES and plan is not None:
            price = int(plan["price_inr_monthly"])
            mrr_inr += price
            active_subscribers += 1
            by_tier[tier]["count"] += 1
            by_tier[tier]["mrr_inr"] += price
            g = _gst_row(u, plan, seller_state)
            gst_totals["taxable_inr"] = round(gst_totals["taxable_inr"] + g["taxable_inr"], 2)
            gst_totals["cgst_inr"] = round(gst_totals["cgst_inr"] + g["cgst_inr"], 2)
            gst_totals["sgst_inr"] = round(gst_totals["sgst_inr"] + g["sgst_inr"], 2)
            gst_totals["igst_inr"] = round(gst_totals["igst_inr"] + g["igst_inr"], 2)
            gst_totals["export_inr"] = round(gst_totals["export_inr"] + g["export_inr"], 2)
        elif tier in by_tier and st in ACTIVE_SUB_STATUSES:
            by_tier[tier]["count"] += 1

    gst_totals["total_tax_inr"] = round(
        gst_totals["cgst_inr"] + gst_totals["sgst_inr"] + gst_totals["igst_inr"], 2
    )

    statuses = ("queued", "running", "succeeded", "failed", "skipped", "cancelled")
    jobs_24h = {st: 0 for st in statuses}
    jobs_7d = {st: 0 for st in statuses}
    for j in jobs_7d_rows:
        st = j.status if j.status in jobs_7d else "failed"
        jobs_7d[st] += 1
        created = _aware(j.created_at)
        if created and created >= cutoff_24h:
            jobs_24h[st] += 1

    stuck_jobs = [
        {
            "id": j.id,
            "user_id": j.user_id,
            "status": j.status,
            "phase": j.phase,
            "trigger": j.trigger,
            "created_at": _iso(j.created_at),
            "started_at": _iso(j.started_at),
            "elapsed_sec": int((now - (_aware(j.started_at) or _aware(j.created_at) or now)).total_seconds()),
        }
        for j in active_jobs
        if _is_job_stuck(j, now)
    ]

    yt_uploads_today = 0
    for p in published_today_posts:
        yt_rec = (p.platforms or {}).get("yt")
        if isinstance(yt_rec, dict) and yt_rec.get("status") == "published":
            yt_uploads_today += 1
    try:
        yt_limit = max(1, int(os.getenv("YT_DAILY_QUOTA_LIMIT") or YT_DEFAULT_DAILY_QUOTA))
    except ValueError:
        yt_limit = YT_DEFAULT_DAILY_QUOTA
    yt_units_used = yt_uploads_today * YT_UNITS_PER_UPLOAD
    yt_util_pct = round(min(100.0, (yt_units_used / yt_limit) * 100.0), 1)

    ig_reauth_count = 0
    yt_quota_err_count = 0
    for fp in failed_posts:
        sig = _error_signature(fp)
        if sig == "IG_TOKEN_190":
            ig_reauth_count += 1
        elif sig == "YT_QUOTA_EXCEEDED":
            yt_quota_err_count += 1

    ucv_counts = {k: int(c) for k, c in ucv_rows}
    latest_checks: dict[str, dict[str, Any]] = {}
    for chk in check_rows:
        if chk.integration not in latest_checks:
            latest_checks[chk.integration] = {
                "integration": chk.integration,
                "status": chk.status,
                "message": chk.message,
                "ran_at": _iso(chk.ran_at),
            }

    return {
        "revenue": {
            "mrr_inr": mrr_inr,
            "arr_inr": mrr_inr * 12,
            "active_subscribers": active_subscribers,
            "total_users": len(users),
            "total_tenants": sum(1 for u in users if (u.role or "client") == "client"),
            "by_tier": list(by_tier.values()),
            "by_status": by_status,
            "gst_summary": gst_totals,
        },
        "jobs": {
            "counts_24h": jobs_24h,
            "counts_7d": jobs_7d,
            "stuck_count": len(stuck_jobs),
            "stuck_jobs": stuck_jobs[:20],
        },
        "failures": {
            "failed_publishes_count": len(failed_posts),
            "ig_needs_reauth_count": ig_reauth_count,
            "yt_quota_errors_count": yt_quota_err_count,
        },
        "youtube_quota": {
            "units_used": yt_units_used,
            "daily_limit": yt_limit,
            "utilization_pct": yt_util_pct,
            "uploads_today": yt_uploads_today,
            "warning": yt_util_pct >= 80.0 or yt_quota_err_count > 0,
        },
        "oauth_health": {
            "ig_connected_tenants": ucv_counts.get("IG_ACCESS_TOKEN", 0),
            "yt_connected_tenants": ucv_counts.get("YT_REFRESH_TOKEN", 0),
            "tg_connected_tenants": ucv_counts.get("TG_CHAT_ID", 0),
            "ig_needs_reauth_posts": ig_reauth_count,
            "config_checks": list(latest_checks.values()),
        },
        "kill_switches": flags.get_kill_switches(),
    }


@router.get("/revenue/gst-export")
def export_gst_csv() -> Response:
    seller_state = _seller_state()
    with db.session() as s:
        users = s.scalars(select(User).order_by(User.id.asc())).all()

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "user_id",
            "username",
            "email",
            "billing_name",
            "billing_country",
            "billing_state",
            "billing_gstin",
            "plan_tier",
            "subscription_status",
            "supply_type",
            "taxable_inr",
            "cgst_inr",
            "sgst_inr",
            "igst_inr",
            "export_inr",
            "total_inr",
        ],
    )
    writer.writeheader()
    for u in users:
        tier = (u.subscription_tier or "free").lower()
        plan = BY_ID.get(tier)
        if plan is None or (u.subscription_status or "") not in BILLABLE_SUB_STATUSES:
            continue
        writer.writerow(_gst_row(u, plan, seller_state))

    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="mintly-gst-summary.csv"'},
    )


# --------------------------------------------------------------------------- #
# 2. Tenants & Unit Economics
# --------------------------------------------------------------------------- #
class SuspendBody(BaseModel):
    active: bool
    reason: str = Field(default="", max_length=300)


class BonusQuotaBody(BaseModel):
    reels: int = Field(default=0, ge=-500, le=5000)
    carousels: int = Field(default=0, ge=-500, le=5000)
    mode: Literal["add", "set"] = "add"
    reason: str = Field(default="", max_length=300)


@router.get("/tenants")
def list_tenants(
    q: str = Query("", max_length=120),
    tier: str | None = Query(None, max_length=32),
    sub_status: str | None = Query(None, alias="status", max_length=32),
    active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    with db.session() as s:
        stmt = select(User)
        search = q.strip().lower()
        if search:
            pat = f"%{search}%"
            stmt = stmt.where(
                or_(
                    func.lower(func.coalesce(User.username, "")).like(pat),
                    func.lower(func.coalesce(User.email, "")).like(pat),
                    func.lower(func.coalesce(User.name, "")).like(pat),
                )
            )
        if tier:
            stmt = stmt.where(func.lower(User.subscription_tier) == tier.lower())
        if sub_status:
            stmt = stmt.where(User.subscription_status == sub_status)
        if active is not None:
            stmt = stmt.where(User.is_active.is_(active))

        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = s.scalars(stmt.order_by(User.id.desc()).offset(offset).limit(limit)).all()

        user_ids = [u.id for u in rows]
        job_counts: dict[int, int] = {}
        if user_ids:
            jc_rows = s.execute(
                select(GenerationJob.user_id, func.count())
                .where(GenerationJob.user_id.in_(user_ids))
                .group_by(GenerationJob.user_id)
            ).all()
            job_counts = {int(uid): int(cnt) for uid, cnt in jc_rows if uid is not None}

    bonus_map = flags.all_bonus_quotas()
    tenants = []
    for u in rows:
        utier = (u.subscription_tier or "free").lower()
        ustatus = u.subscription_status or "active"
        plan = BY_ID.get(utier)
        window = plan_limits.cycle_window(u)
        used = plan_limits.usage(u.id, window=window)
        b_entry = bonus_map.get(str(u.id)) or {}
        bonus = {
            "reels": max(0, int(b_entry.get("reels", 0) or 0)),
            "carousels": max(0, int(b_entry.get("carousels", 0) or 0)),
        }
        base_quota = dict(plan["quota"]) if plan else {"reels": 0, "carousels": 0}
        eff_quota = {
            "reels": base_quota["reels"] + bonus["reels"],
            "carousels": base_quota["carousels"] + bonus["carousels"],
        }
        revenue_inr = int(plan["price_inr_monthly"]) if (plan and ustatus in BILLABLE_SUB_STATUSES) else 0
        cogs_inr = used["reels"] * COGS_PER_REEL_INR + used["carousels"] * COGS_PER_CAROUSEL_INR
        if revenue_inr > 0:
            margin_pct: float | None = round(((revenue_inr - cogs_inr) / revenue_inr) * 100.0, 1)
        elif cogs_inr > 0:
            margin_pct = -100.0
        else:
            margin_pct = None

        tenants.append(
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "name": u.name,
                "role": u.role or "client",
                "is_active": bool(u.is_active),
                "subscription_tier": utier,
                "subscription_status": ustatus,
                "subscription_renews_at": _iso(u.subscription_renews_at),
                "created_at": _iso(u.created_at),
                "last_login_at": _iso(u.last_login_at),
                "config_completed": bool(u.config_completed),
                "billing_country": u.billing_country,
                "billing_state": u.billing_state,
                "billing_gstin": u.billing_gstin,
                "quota_used": used,
                "quota_limit": eff_quota,
                "bonus_quota": bonus,
                "generation_jobs_count": job_counts.get(u.id, 0),
                "cogs_inr": cogs_inr,
                "revenue_inr": revenue_inr,
                "margin_pct": margin_pct,
            }
        )
    return {"tenants": tenants, "total": int(total), "limit": limit, "offset": offset}


@router.post("/tenants/{user_id}/suspend")
def suspend_tenant(user_id: int, body: SuspendBody, cu: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    if user_id == cu.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot suspend your own account")
    with db.session() as s:
        target = s.get(User, user_id)
        if not target:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
        target_role = target.role or "client"
        if target_role == "owner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot suspend an owner account")
        if target_role == "admin" and cu.role != "owner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can suspend admin accounts")

        target.is_active = body.active
        if not body.active:
            target.token_version += 1  # immediately invalidate all active sessions
        tv = target.token_version
        tname = target.username or target.email or f"user:{target.id}"

    event = "admin.tenant.reactivated" if body.active else "admin.tenant.suspended"
    verb = "Reactivated" if body.active else "Suspended"
    activity.record(
        event,
        f"{verb} account {tname}" + (f" ({body.reason.strip()})" if body.reason.strip() else ""),
        level="info" if body.active else "warning",
        source="admin",
        actor=_actor(cu),
        user_id=user_id,
        detail={"target_user_id": user_id, "active": body.active, "reason": body.reason.strip(), "token_version": tv},
    )
    return {"ok": True, "user_id": user_id, "is_active": body.active, "token_version": tv}


@router.post("/tenants/{user_id}/bonus-quota")
def adjust_bonus_quota(user_id: int, body: BonusQuotaBody, cu: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    with db.session() as s:
        target = s.get(User, user_id)
        if not target:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
        tname = target.username or target.email or f"user:{target.id}"

    entry = flags.set_bonus_quota(
        user_id,
        body.reels,
        body.carousels,
        mode=body.mode,
        actor=_actor(cu),
        reason=body.reason.strip(),
    )
    activity.record(
        "admin.tenant.bonus_quota",
        f"Updated bonus quota for {tname}: +{entry['reels']} reels, +{entry['carousels']} carousels ({body.mode})",
        source="admin",
        actor=_actor(cu),
        user_id=user_id,
        detail={"target_user_id": user_id, "mode": body.mode, "bonus_quota": entry, "reason": body.reason.strip()},
    )
    return {"ok": True, "user_id": user_id, "bonus_quota": {"reels": entry["reels"], "carousels": entry["carousels"]}}


# --------------------------------------------------------------------------- #
# 3. Generation Jobs & Stuck-Job Reconciliation
# --------------------------------------------------------------------------- #
class ReconcileBody(BaseModel):
    job_ids: list[str] | None = None
    force_fail_stuck: bool = True


@router.get("/jobs")
def list_admin_jobs(
    status_filter: str | None = Query(None, alias="status"),
    stuck_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    with db.session() as s:
        stmt = select(GenerationJob).order_by(GenerationJob.created_at.desc())
        if status_filter:
            stmt = stmt.where(GenerationJob.status == status_filter)
        rows = s.scalars(stmt.limit(limit if not stuck_only else 200)).all()

        recent_7d = s.scalars(select(GenerationJob).where(GenerationJob.created_at >= cutoff_7d)).all()
        user_ids = {j.user_id for j in rows if j.user_id is not None}
        user_map: dict[int, tuple[str | None, str | None]] = {}
        if user_ids:
            for u in s.scalars(select(User).where(User.id.in_(user_ids))).all():
                user_map[u.id] = (u.username, u.email)

    statuses = ("queued", "running", "succeeded", "failed", "skipped", "cancelled")
    counts_24h = {st: 0 for st in statuses}
    counts_7d = {st: 0 for st in statuses}
    for j in recent_7d:
        st = j.status if j.status in counts_7d else "failed"
        counts_7d[st] += 1
        c_at = _aware(j.created_at)
        if c_at and c_at >= cutoff_24h:
            counts_24h[st] += 1

    out = []
    stuck_count = 0
    for j in rows:
        stuck = _is_job_stuck(j, now)
        if stuck:
            stuck_count += 1
        if stuck_only and not stuck:
            continue
        d = generation.to_dict(j)
        uname, uemail = user_map.get(j.user_id or -1, (None, None))
        d["username"] = uname
        d["email"] = uemail
        d["is_stuck"] = stuck
        out.append(d)
        if len(out) >= limit:
            break

    return {
        "jobs": out,
        "stuck_count": stuck_count,
        "counts_24h": counts_24h,
        "counts_7d": counts_7d,
        "github_configured": github_actions.configured(),
    }


@router.post("/jobs/reconcile")
def reconcile_stuck_jobs(
    body: ReconcileBody = Body(default_factory=ReconcileBody),
    cu: CurrentUser = Depends(current_user),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with db.session() as s:
        stmt = select(GenerationJob).where(GenerationJob.status.in_(("queued", "running")))
        if body.job_ids:
            stmt = stmt.where(GenerationJob.id.in_(body.job_ids))
        active_rows = s.scalars(stmt).all()

    reconciled: list[str] = []
    released: list[str] = []
    for row in active_rows:
        job_dict = generation.to_dict(row)
        was_stuck = _is_job_stuck(row, now)
        if github_actions.configured():
            updated, _ = generation.reconcile(job_dict, now=now)
            if not updated["active"]:
                reconciled.append(row.id)
                continue
        if body.force_fail_stuck and (was_stuck or bool(body.job_ids)):
            if generation.finish(
                row.id,
                "failed",
                reason="timeout",
                message="Released by operator reconcile (stuck job).",
            ):
                released.append(row.id)

    if reconciled or released:
        activity.record(
            "admin.jobs.reconcile",
            f"Operator reconciled {len(reconciled)} and released {len(released)} stuck job(s)",
            source="admin",
            actor=_actor(cu),
            detail={"reconciled": reconciled, "released": released},
        )
    return {"ok": True, "checked": len(active_rows), "reconciled": reconciled, "released": released}


# --------------------------------------------------------------------------- #
# 4. Cross-Tenant Failed Publish Dead-Letter Queue (DLQ)
# --------------------------------------------------------------------------- #
class RetryFailuresBody(BaseModel):
    post_ids: list[str] | None = None
    signature: str | None = Field(default=None, max_length=120)


@router.get("/failures")
def list_failures(limit: int = Query(100, ge=1, le=300)) -> dict[str, Any]:
    with db.session() as s:
        posts = s.scalars(
            select(Post).where(Post.status == "failed").order_by(Post.updated_at.desc()).limit(limit)
        ).all()
        user_ids = {p.user_id for p in posts if p.user_id is not None}
        user_map: dict[int, tuple[str | None, str | None]] = {}
        if user_ids:
            for u in s.scalars(select(User).where(User.id.in_(user_ids))).all():
                user_map[u.id] = (u.username, u.email)

    failures = []
    groups_map: dict[str, dict[str, Any]] = {}
    for p in posts:
        sig = _error_signature(p)
        uname, uemail = user_map.get(p.user_id or -1, (None, None))
        entry = {
            "id": p.id,
            "kind": p.kind,
            "topic": p.topic,
            "user_id": p.user_id,
            "username": uname,
            "email": uemail,
            "status": p.status,
            "attempts": p.attempts,
            "error": p.error,
            "signature": sig,
            "platforms": p.platforms or {},
            "publish_at": _iso(p.publish_at),
            "updated_at": _iso(p.updated_at),
        }
        failures.append(entry)
        grp = groups_map.setdefault(
            sig,
            {"signature": sig, "count": 0, "sample_error": p.error or sig, "post_ids": []},
        )
        grp["count"] += 1
        grp["post_ids"].append(p.id)

    groups = sorted(groups_map.values(), key=lambda g: g["count"], reverse=True)
    return {"failures": failures, "groups": groups, "total": len(failures)}


@router.post("/failures/retry")
def retry_failures(
    body: RetryFailuresBody = Body(default_factory=RetryFailuresBody),
    cu: CurrentUser = Depends(current_user),
) -> dict[str, Any]:
    if not body.post_ids and not body.signature:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Specify post_ids or signature to retry")

    with db.session() as s:
        stmt = select(Post).where(Post.status == "failed")
        if body.post_ids:
            stmt = stmt.where(Post.id.in_(body.post_ids))
        posts = s.scalars(stmt).all()

        retried: list[str] = []
        for p in posts:
            if body.signature and _error_signature(p) != body.signature:
                continue
            p.status = "approved"
            p.attempts = 0
            p.error = None
            new_platforms: dict[str, Any] = {}
            for plat, rec in (p.platforms or {}).items():
                if isinstance(rec, dict):
                    copied = dict(rec)
                    if copied.get("status") == "failed":
                        copied["attempts"] = 0
                        copied.pop("quota_exhausted", None)
                        copied.pop("at", None)
                    new_platforms[plat] = copied
                else:
                    new_platforms[plat] = rec
            p.platforms = new_platforms
            retried.append(p.id)

    if retried:
        activity.record(
            "admin.failures.retry",
            f"Queued {len(retried)} failed post(s) for retry",
            source="admin",
            actor=_actor(cu),
            detail={"post_ids": retried, "signature": body.signature},
        )
    return {"ok": True, "retried": retried, "count": len(retried)}


# --------------------------------------------------------------------------- #
# 5. Safety Kill-Switches & Feature Flags
# --------------------------------------------------------------------------- #
class SafetyBody(BaseModel):
    generation: bool | None = None
    publishing: bool | None = None
    signups: bool | None = None
    reason: str | None = Field(default=None, max_length=300)


class FeatureFlagItem(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    enabled: bool = False
    rollout_pct: int = Field(default=0, ge=0, le=100)
    description: str = Field(default="", max_length=300)
    allow_user_ids: list[int] = Field(default_factory=list)
    allow_tiers: list[str] = Field(default_factory=list)


class FlagsPutBody(BaseModel):
    flags: list[FeatureFlagItem] | None = None
    key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    enabled: bool | None = None
    rollout_pct: int | None = Field(default=None, ge=0, le=100)
    description: str | None = Field(default=None, max_length=300)
    allow_user_ids: list[int] | None = None
    allow_tiers: list[str] | None = None


@router.get("/safety")
def get_safety() -> dict[str, Any]:
    return {
        "kill_switches": flags.get_kill_switches(),
        "publishing_enabled": actions.publishing_enabled(),
    }


@router.put("/safety")
def update_safety(body: SafetyBody, cu: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    updated = flags.set_kill_switches(body.model_dump(exclude_none=True), actor=_actor(cu))
    activity.record(
        "admin.safety.updated",
        f"Updated kill-switches: gen={updated['generation']}, pub={updated['publishing']}, signups={updated['signups']}",
        level="warning" if any(updated[k] for k in ("generation", "publishing", "signups")) else "info",
        source="admin",
        actor=_actor(cu),
        detail=updated,
    )
    return {"kill_switches": updated, "publishing_enabled": actions.publishing_enabled()}


@router.get("/flags")
def list_feature_flags() -> dict[str, Any]:
    return {"flags": flags.get_feature_flags()}


@router.put("/flags")
def update_feature_flags(body: FlagsPutBody, cu: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    if body.flags is not None:
        saved = flags.set_feature_flags([f.model_dump() for f in body.flags])
    elif body.key is not None:
        existing = next((f for f in flags.get_feature_flags() if f["key"] == body.key), None) or {"key": body.key}
        merged = {
            "key": body.key,
            "enabled": existing.get("enabled", False) if body.enabled is None else body.enabled,
            "rollout_pct": existing.get("rollout_pct", 0) if body.rollout_pct is None else body.rollout_pct,
            "description": existing.get("description", "") if body.description is None else body.description,
            "allow_user_ids": existing.get("allow_user_ids", []) if body.allow_user_ids is None else body.allow_user_ids,
            "allow_tiers": existing.get("allow_tiers", []) if body.allow_tiers is None else body.allow_tiers,
        }
        saved = flags.upsert_feature_flag(merged)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Provide either 'flags' list or a 'key' to update")

    activity.record(
        "admin.flags.updated",
        f"Updated feature flags ({len(saved)} active definitions)",
        source="admin",
        actor=_actor(cu),
        detail={"keys": [f["key"] for f in saved]},
    )
    return {"flags": saved}


@router.delete("/flags/{key}")
def remove_feature_flag(key: str, cu: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    saved = flags.delete_feature_flag(key)
    activity.record("admin.flags.deleted", f"Deleted feature flag {key}", source="admin", actor=_actor(cu), detail={"key": key})
    return {"flags": saved}


# --------------------------------------------------------------------------- #
# 6. Support Impersonation (15-min, Read-Only, Strictly Audited)
# --------------------------------------------------------------------------- #
class ImpersonateBody(BaseModel):
    reason: str = Field(min_length=10, max_length=300)


@router.post("/tenants/{user_id}/impersonate")
def start_impersonation(
    user_id: int,
    body: ImpersonateBody,
    response: Response,
    cu: CurrentUser = Depends(current_user),
) -> dict[str, Any]:
    reason = body.reason.strip()
    if len(reason) < 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Support reason must be at least 10 characters")

    with db.session() as s:
        target = s.get(User, user_id)
        if not target:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
        if (target.role or "client") != "client":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot impersonate admin or owner accounts")
        if not target.is_active:
            raise HTTPException(status.HTTP_409_CONFLICT, "Cannot impersonate a suspended account")
        admin_row = s.get(User, cu.id)
        if not admin_row or not admin_row.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin session invalid")

        token, csrf, expires_at = create_impersonation_token(
            target.id,
            target.token_version,
            admin_row.id,
            admin_row.token_version,
            reason,
            read_only=True,
        )
        set_session_cookie(response, token, max_age=IMPERSONATION_TTL_MINUTES * 60)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        imp_cu = CurrentUser(
            target.id,
            target.username,
            target.email,
            target.name,
            csrf,
            target.role or "client",
            impersonated_by=admin_row.id,
            read_only=True,
            impersonation_expires_at=expires_at.isoformat(timespec="seconds"),
            impersonation_reason=reason,
        )
        user_payload = _user_out(target, csrf, imp_cu)

    activity.record(
        "admin.impersonation.start",
        f"Support impersonation started for {user_payload.get('username') or user_payload.get('email')}",
        level="warning",
        source="admin",
        actor=_actor(cu),
        user_id=user_id,
        detail={
            "admin_id": cu.id,
            "target_user_id": user_id,
            "reason": reason,
            "read_only": True,
            "expires_at": imp_cu.impersonation_expires_at,
        },
    )
    return {
        "ok": True,
        "read_only": True,
        "expires_at": imp_cu.impersonation_expires_at,
        "user": user_payload,
    }


@impersonation_router.post("/impersonation/exit")
def exit_impersonation(response: Response, cu: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    if cu.impersonated_by is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not in an active impersonation session")

    with db.session() as s:
        admin_row = s.get(User, cu.impersonated_by)
        if not admin_row or not admin_row.is_active or (admin_row.role or "client") not in ("owner", "admin"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Original admin session is no longer valid")
        token, csrf = create_session_token(admin_row.id, admin_row.token_version)
        set_session_cookie(response, token)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        admin_payload = _user_out(admin_row, csrf)

    activity.record(
        "admin.impersonation.exit",
        f"Support impersonation ended for target user {cu.id}",
        source="admin",
        actor=admin_payload.get("username") or admin_payload.get("email") or f"admin:{cu.impersonated_by}",
        user_id=cu.id,
        detail={"admin_id": cu.impersonated_by, "target_user_id": cu.id},
    )
    return {"ok": True, "user": admin_payload}


# --------------------------------------------------------------------------- #
# 7. Admin Audit Log
# --------------------------------------------------------------------------- #
@router.get("/audit")
def list_admin_audit(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    with db.session() as s:
        rows = s.scalars(
            select(ActivityLog)
            .where(or_(ActivityLog.source == "admin", ActivityLog.event.like("admin.%")))
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
        ).all()
    return {
        "events": [
            {
                "id": r.id,
                "created_at": _iso(r.created_at),
                "level": r.level,
                "source": r.source,
                "event": r.event,
                "message": r.message,
                "actor": r.actor,
                "user_id": r.user_id,
                "detail": r.detail,
            }
            for r in rows
        ]
    }
