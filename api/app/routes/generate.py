"""Generate: start a post on demand, watch it, and see which posting slots are filled.

Rendering needs Chromium + FFmpeg, so the API only records a job (src.generation) and dispatches the
daily-generate.yml GitHub workflow; the pipeline reports its progress back into the same job row, and
reads of an unfinished job are reconciled against GitHub (src.generation.reconcile). Nothing here, or in
the workflow it starts, publishes: new items are `pending` until approved in Telegram or the dashboard.

Mounted under /api (signed in + CSRF on writes, see main.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

from api.app.deps import CurrentUser, current_user
from api.app.ratelimit import RateLimiter
from src import activity, approve_bot, generation, github_actions
from src import queue_store as q
from src.actions import publishing_enabled
from src.approve_bot import IST
from src.config import get_env, load_brand


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """The one place to enforce a role once there is more than one kind of user (today: signed in = admin)."""
    return user


router = APIRouter(prefix="/generate", tags=["generate"], dependencies=[Depends(require_admin)])

limiter = RateLimiter()
RATE_LIMIT, RATE_WINDOW = 5, 60          # requests per user per minute
COOLDOWN = timedelta(seconds=60)         # between two dashboard requests of one user
DEFAULT_DAILY_CAP = 4


def _fail(code: int, error: str, message: str, **extra) -> HTTPException:
    return HTTPException(code, detail={"code": error, "message": message, **extra})


def _slots() -> list[str]:
    return [f"{t:%H:%M}" for t in approve_bot.post_times()]


def _user_slots(cu: CurrentUser | None = None) -> list[str]:
    if cu:
        from src import db
        from src.db.models import User
        with db.session() as s:
            user = s.get(User, cu.id)
            if user and user.cadence and user.cadence.get("slots"):
                return list(user.cadence["slots"])
    return _slots()


def _daily_cap() -> int:
    try:
        return max(0, int(get_env("GENERATE_DAILY_CAP", required=False, default=str(DEFAULT_DAILY_CAP))))
    except ValueError:
        return DEFAULT_DAILY_CAP


def _day_start(now: datetime) -> datetime:
    return now.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)


def _actor(user: CurrentUser) -> str:
    return user.username or user.email or f"user {user.id}"


# --------------------------------------------------------------------------- #
# Request body
# --------------------------------------------------------------------------- #
class GenerateBody(BaseModel):
    slot: str = "auto"                              # "auto" = next free slot, or one of today's slots (HH:MM IST)
    category: str | None = None                     # None / "auto" = by the brand weights
    topic: str | None = Field(None, max_length=400)
    source_url: str | None = Field(None, max_length=600)
    force: bool = False                             # extra post for a slot that has one / a slot long past
    allow_duplicate: bool = False
    confirm_quota: bool = False                     # go ahead although Gemini's quota ran out recently
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("topic")
    @classmethod
    def _topic(cls, v):
        return generation.clean_topic(v)

    @field_validator("source_url")
    @classmethod
    def _url(cls, v):
        return generation.clean_source_url(v)

    @field_validator("category")
    @classmethod
    def _category(cls, v):
        if v in (None, "", "auto"):
            return None
        if v not in generation.CATEGORIES:
            raise ValueError(f"Category must be one of {', '.join(generation.CATEGORIES)}")
        return v

    @model_validator(mode="after")
    def _combine(self):
        if self.slot != "auto" and self.slot not in _slots():
            raise ValueError(f"Slot must be auto or one of {', '.join(_slots())}")
        if self.topic and not self.category:
            raise ValueError("Pick a category for a custom topic")
        if self.source_url and not self.topic:
            raise ValueError("A source link needs a topic")
        return self


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def _github_state(ok: bool) -> dict:
    return {"ok": ok, "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds")}


@router.get("/config")
def get_config(cu: CurrentUser = Depends(current_user)) -> dict:
    now = datetime.now(IST)
    cap = _daily_cap()
    quota_at = generation.last_quota_failure(now)
    tomorrow = _day_start(now) + timedelta(days=1)
    return {
        "dispatch_configured": github_actions.configured(),
        "slots": _user_slots(cu),
        "categories": [{"name": c, "weight": w} for c, w in load_brand()["topics_weight"].items()],
        "daily_cap": cap, "used_today": generation.used_today(_day_start(now)), "resets_at": tomorrow.isoformat(),
        "quota_cooldown_until": (quota_at + generation.QUOTA_COOLDOWN).isoformat() if quota_at else None,
        "late_limit_hours": generation.LATE_LIMIT_HOURS,
        "publishing_enabled": publishing_enabled(), "telegram_sync": approve_bot.sync_enabled(),
        "topic_length": [5, 120],
    }


def _items_at(slot: datetime, items: list[q.Item]) -> list[q.Item]:
    return [i for i in items if i.publish_at and datetime.fromisoformat(i.publish_at) == slot]


def _current(items: list[q.Item], kind: str) -> q.Item | None:
    mine = [i for i in items if i.kind == kind and i.status != "replaced"]
    return max(mine, key=lambda i: (i.version, i.created_at)) if mine else None


@router.get("/slots")
def get_slots(days: int = Query(2, ge=1, le=3), cu: CurrentUser = Depends(current_user)) -> dict:
    now = datetime.now(IST)
    first = approve_bot.slot_at(now.date().isoformat(), "00:00")
    items = q.load_window(first, first + timedelta(days=days + 1))  # only these days' slots (QA-M-08)
    jobs = generation.since(now.astimezone(timezone.utc) - timedelta(days=2))
    slots = _user_slots(cu)
    out = []
    for offset in range(days):
        day = (now + timedelta(days=offset)).date()
        for hhmm in slots:
            at = approve_bot.slot_at(day.isoformat(), hhmm)
            there = _items_at(at, items)
            mine = [j for j in jobs if j["slot_at"] and datetime.fromisoformat(j["slot_at"]) == at]
            job = mine[0] if mine else None  # newest first
            hours_late = (now - at).total_seconds() / 3600
            if there:
                state = "generated"
            elif any(j["active"] for j in mine):
                state, job = "generating", next(j for j in mine if j["active"])
            elif job and job["status"] in ("failed", "skipped"):
                state = job["status"]
            else:
                state = "upcoming" if hours_late < 0 else "late" if hours_late <= generation.LATE_LIMIT_HOURS else "stale"
            reel, carousel = _current(there, "reel"), _current(there, "carousel")
            head = reel or carousel
            out.append({
                "slot_at": at.isoformat(), "time": hhmm, "date": day.isoformat(),
                "day": "today" if offset == 0 else "tomorrow" if offset == 1 else day.isoformat(),
                "state": state, "hours_late": round(hours_late, 1),
                "can_generate": offset == 0 and state != "generated" and state != "generating",
                "group_id": head.group_id if head else None, "topic": head.topic if head else None,
                "category": head.category if head else None,
                "items": {k: {"id": v.id, "status": v.status} if v else None
                          for k, v in (("reel", reel), ("carousel", carousel))},
                "job": {k: job[k] for k in ("id", "status", "phase", "failure_reason", "message", "trigger")} if job else None,
            })
    return {"now": now.isoformat(timespec="seconds"), "slots": out}


@router.get("/jobs")
def list_jobs(limit: int = Query(20, ge=1, le=50)) -> dict:
    reachable = True
    if live := generation.active():
        _, reachable = generation.reconcile(live)
    jobs = generation.recent(limit)
    return {"jobs": jobs, "active": next((j for j in jobs if j["active"]), None), "github": _github_state(reachable)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = generation.get(job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    job, reachable = generation.reconcile(job)
    return {"job": job, "github": _github_state(reachable)}


@router.get("/for-group")
def job_for_group(group_id: str = Query(..., min_length=1, max_length=120)) -> dict:
    """Which request generated a post group (shown in the Posts panel), or null for older posts."""
    job = generation.for_group(group_id)
    return {"job": {k: job[k] for k in ("id", "trigger", "requested_by", "created_at", "status")} if job else None}


@router.get("/check")
def check_topic(topic: str = Query(..., max_length=400)) -> dict:
    """Is this topic a repeat of a recent post? (Shown while the admin types, before they submit.)"""
    try:
        clean = generation.clean_topic(topic)
    except ValueError:
        clean = None
    dup = generation.find_duplicate(clean) if clean else None
    return {"duplicate": {"title": dup[0], "date": dup[1]} if dup else None}


# --------------------------------------------------------------------------- #
# Start a run
# --------------------------------------------------------------------------- #
@router.post("", status_code=status.HTTP_201_CREATED)
def request_generation(body: GenerateBody, response: Response, user: CurrentUser = Depends(require_admin)) -> dict:
    if not github_actions.configured():
        raise _fail(503, "not_configured", "Generation can't be started from the dashboard until the GitHub "
                    "token is configured. Scheduled runs still happen.")
    if replay := generation.by_idempotency_key(body.idempotency_key):
        response.status_code = status.HTTP_200_OK  # a retry of a request we already took: same job, no 2nd dispatch
        return replay

    if wait := limiter.retry_after(str(user.id), RATE_LIMIT, RATE_WINDOW):
        raise HTTPException(429, detail={"code": "rate_limited", "message": "Too many requests. Wait a moment."},
                            headers={"Retry-After": str(wait)})
    limiter.hit(str(user.id))

    now = datetime.now(IST)
    if live := generation.active():
        live, _ = generation.reconcile(live)  # a dead job must not block the form forever
        if live["active"]:
            raise _fail(409, "job_active", "A generation is already running.", job=live)
    cap = _daily_cap()
    if generation.used_today(_day_start(now)) >= cap:
        raise _fail(409, "cap_reached", f"Daily limit ({cap}) reached; resets at 00:00 IST.",
                    resets_at=(_day_start(now) + timedelta(days=1)).isoformat())
    last = generation.last_dashboard_request(_actor(user))
    if last and now - last < COOLDOWN:
        wait = int((COOLDOWN - (now - last)).total_seconds()) + 1
        raise HTTPException(429, detail={"code": "cooldown", "message": f"Wait {wait}s before the next request."},
                            headers={"Retry-After": str(wait)})
    if not body.confirm_quota and (quota_at := generation.last_quota_failure(now)):
        raise _fail(409, "quota_cooldown", "Gemini's free quota ran out recently. Generating now will probably "
                    "fail; confirm to try anyway.", until=(quota_at + generation.QUOTA_COOLDOWN).isoformat())

    slot_at = approve_bot.next_slot(now) if body.slot == "auto" else approve_bot.slot_at(now.date().isoformat(), body.slot)
    if not body.force:
        taken = bool(q.load_window(slot_at, slot_at))
        state = generation.slot_state(slot_at, now, taken)
        if state == "taken":
            raise _fail(409, "slot_taken", f"The {slot_at:%H:%M} slot already has a post. Tick “extra post” to add another.")
        if state == "stale":
            raise _fail(409, "slot_stale", f"The {slot_at:%H:%M} slot passed more than {generation.LATE_LIMIT_HOURS}h ago. "
                        "Pick another slot, or tick “extra post”.")
    if body.topic and not body.allow_duplicate and (dup := generation.find_duplicate(body.topic)):
        raise _fail(409, "duplicate_topic", f"Looks like “{dup[0]}” ({dup[1]}).", title=dup[0], date=dup[1])

    try:
        job = generation.create(trigger="dashboard", requested_by=_actor(user), slot_at=slot_at, category=body.category,
                                topic=body.topic, source_url=body.source_url, force=body.force,
                                allow_duplicate=body.allow_duplicate, idempotency_key=body.idempotency_key)
    except generation.Replay as r:  # two identical requests raced: the first one owns the dispatch
        response.status_code = status.HTTP_200_OK
        return r.job
    except generation.JobActive:
        raise _fail(409, "job_active", "A generation is already running.", job=generation.active()) from None

    activity.record("generate.requested",
                    f"Generation {job['id']} requested for {slot_at:%d %b %H:%M} IST"
                    + (f": “{body.topic}” [{body.category}]" if body.topic else f" ({body.category or 'auto category'})"),
                    source="generate", actor=_actor(user),
                    detail={"request_id": job["id"], "slot": slot_at.isoformat(), "category": body.category,
                            "topic": body.topic, "source_url": body.source_url, "force": body.force})
    # The slot the API validated (taken/stale) and showed, not "auto": a run that waits in the queue past the
    # 30-minute lead would otherwise resolve "auto" to the NEXT slot (QA-L-10).
    inputs = {"slot": f"{slot_at:%H:%M}", "date": slot_at.date().isoformat(), "category": body.category or "", "topic": body.topic or "",
              "source_url": body.source_url or "", "request_id": job["id"], "dry_run": "false",
              "force": str(body.force).lower(), "allow_duplicate": str(body.allow_duplicate).lower()}
    try:
        github_actions.dispatch(generation.WORKFLOW, inputs)
    except github_actions.GitHubError as e:
        reason = "dispatch_rejected" if e.kind == "rejected" else "dispatch_failed"
        generation.finish(job["id"], "failed", reason=reason, message=generation.REASON_TEXT[reason])
        raise _fail(502, "dispatch_failed", generation.REASON_TEXT[reason], job=generation.get(job["id"])) from None
    generation.mark_dispatched(job["id"])
    return generation.get(job["id"]) or job
