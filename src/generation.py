"""Generation jobs: one row per generate request, so the dashboard can start a run, watch it, and explain
what happened. The pipeline (main.py generate) reports into it; the API creates and reconciles it.

Lifecycle: queued (API dispatched the workflow) -> running (the pipeline started) -> succeeded | failed |
skipped | cancelled. Scheduled runs (cron) create their own row when they start. Everything the pipeline
calls here (Reporter) NEVER raises: reporting must not break generating. Generation never publishes.
"""
from __future__ import annotations

import difflib
import ipaddress
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from src import activity, db
from src.db.models import GenerationJob, utcnow
from src.logger import get_logger

log = get_logger("generation")

WORKFLOW = "daily-generate.yml"
ACTIVE = ("queued", "running")
TERMINAL = ("succeeded", "failed", "skipped", "cancelled")
PHASES = ("starting", "fetching_topics", "ranking", "writing", "rendering", "uploading", "sending_previews", "done")
CATEGORIES = ("AI", "SystemDesign", "DSA", "Interview", "OS", "Dev")
RETENTION_DAYS = 90
RUN_LIMIT = timedelta(minutes=45)          # the workflow's own timeout is 40
QUEUE_LIMIT = timedelta(minutes=90)        # a run may legitimately wait behind another generate run
NOT_STARTED_AFTER = timedelta(seconds=90)  # dispatched, but GitHub never created the run
QUOTA_COOLDOWN = timedelta(minutes=60)
DUPLICATE_RATIO = 0.85

# GitHub's cron regularly fires 4-6h late, so a late trigger must still produce a post: it
# generates for its (already past) slot and publishes as soon as it is approved. Only a truly
# ancient trigger -- e.g. a manual re-run of an old slot -- is skipped.
LATE_LIMIT_HOURS = 12


def slot_state(publish_at: datetime, now: datetime, slot_taken: bool) -> str:
    """Should this run generate? "taken" | "stale" | "late" | "ok" (see LATE_LIMIT_HOURS)."""
    if slot_taken:
        return "taken"
    late = now - publish_at
    if late > timedelta(hours=LATE_LIMIT_HOURS):
        return "stale"
    return "late" if late > timedelta(minutes=30) else "ok"


REASON_TEXT = {
    "quota": "Gemini's free quota is used up. Try again after about 12:30 IST, or tomorrow.",
    "fetch": "Fetching trending topics failed.",
    "rank": "Choosing a topic failed.",
    "write": "Writing the post failed.",
    "render": "Rendering the carousel or reel failed.",
    "upload": "Uploading the media to Cloudinary failed.",
    "telegram": "Sending the Telegram previews failed.",
    "dispatch_rejected": "GitHub refused the request (token expired or missing Actions permission).",
    "dispatch_failed": "Couldn't reach GitHub to start the run.",
    "not_started": "GitHub did not start the run. Check the Actions tab before trying again.",
    "timeout": "The run did not finish in time.",
    "duplicate": "This topic was already covered recently.",
    "superseded": "GitHub replaced this run with a newer one.",
    "unknown": "The run failed. Open the GitHub run for details.",
}
_PHASE_REASON = {"fetching_topics": "fetch", "ranking": "rank", "writing": "write", "rendering": "render",
                 "uploading": "upload", "sending_previews": "telegram"}
_SECRET = re.compile(r"(AIza[\w-]{20,}|Bearer\s+\S+|ghp_\w+|github_pat_\w+|(?:key|token)=[^&\s]+)", re.I)
_ID = re.compile(r"^[a-f0-9]{6,16}$")
_SLOT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class JobActive(Exception):
    """Another job of this trigger is already queued or running."""


class Replay(Exception):
    """The idempotency key was already used: `job` is the request it created (don't dispatch again)."""

    def __init__(self, job: dict):
        super().__init__(job["id"])
        self.job = job


# --------------------------------------------------------------------------- #
# Validation (shared by the API and the pipeline)
# --------------------------------------------------------------------------- #
def valid_id(value: str | None) -> bool:
    return bool(value and _ID.match(value))


def valid_slot(value: str) -> bool:
    return bool(_SLOT.match(value))


def clean_topic(value: str | None) -> str | None:
    """5-120 characters of plain text; None when empty."""
    raw = value or ""
    if _CONTROL.search(raw.replace("\n", " ").replace("\t", " ")):
        raise ValueError("Topic must be plain text")
    value = " ".join(raw.split())
    if not value:
        return None
    if not 5 <= len(value) <= 120:
        raise ValueError("Topic must be 5-120 characters")
    return value


def clean_source_url(value: str | None) -> str | None:
    """An https URL on a public host. (The runner never fetches it in the MVP, but it ends up in captions.)"""
    value = (value or "").strip()
    if not value:
        return None
    if len(value) > 500 or _CONTROL.search(value) or " " in value:
        raise ValueError("Source URL must be a single link of at most 500 characters")
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        parts.port  # noqa: B018 -- raises on a bad port
    except ValueError as e:
        raise ValueError("Source URL isn't a valid link") from e
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise ValueError("Source URL must be a plain https:// link")
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip or "." not in host or host.split(".")[-1].isdigit() or host == "localhost" \
            or host.endswith((".local", ".internal", ".localhost", ".lan", ".home", ".corp")):
        raise ValueError("Source URL must point to a public website")
    return value


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def recent_topics(limit: int = 200) -> list[tuple[str, str]]:
    """(title, date) of recent posts, newest first: the queue plus the publishing history."""
    from src import queue_store as q
    rows = q.recent_topic_rows(limit)  # bounded queries, not every post ever made (QA-M-08)
    seen: dict[str, tuple[str, str]] = {}
    for title, day in rows:
        if title:
            seen.setdefault(_norm(title), (title, day))
    return list(seen.values())[:limit]


def find_duplicate(title: str) -> tuple[str, str] | None:
    """The recent (title, date) that `title` repeats (same words, or very similar), else None."""
    mine = _norm(title)
    for other, day in recent_topics():
        theirs = _norm(other)
        if mine == theirs or difflib.SequenceMatcher(None, mine, theirs).ratio() >= DUPLICATE_RATIO:
            return other, day
    return None


def scrub(text: str, limit: int = 300) -> str:
    return _SECRET.sub("[hidden]", " ".join((text or "").split()))[:limit]


def classify(exc: BaseException, phase: str | None) -> str:
    text = f"{type(exc).__name__} {exc}".lower()
    if "quota" in text or "resource_exhausted" in text or (phase in ("ranking", "writing") and "429" in text):
        return "quota"
    return _PHASE_REASON.get(phase or "", "unknown")


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _iso(dt: datetime | None) -> str | None:
    dt = _aware(dt)
    return dt.isoformat(timespec="seconds") if dt else None


def _utc(dt: datetime) -> datetime:
    """SQLite stores naive UTC, so compare in UTC whatever zone the caller thinks in."""
    return dt.astimezone(timezone.utc)


def to_dict(r: GenerationJob) -> dict:
    end = _aware(r.finished_at) or utcnow()
    begin = _aware(r.started_at) or _aware(r.created_at)
    return {
        "id": r.id, "trigger": r.trigger, "requested_by": r.requested_by, "status": r.status, "phase": r.phase,
        "active": r.status in ACTIVE, "failure_reason": r.failure_reason,
        "message": r.message or (REASON_TEXT.get(r.failure_reason or "") if r.status in ("failed", "cancelled") else None),
        "slot_at": _iso(r.slot_at), "category": r.category, "topic": r.topic, "source_url": r.source_url,
        "force": bool(r.force), "allow_duplicate": bool(r.allow_duplicate),
        "github_run_id": r.github_run_id, "github_run_url": r.github_run_url,
        "created_at": _iso(r.created_at), "started_at": _iso(r.started_at), "finished_at": _iso(r.finished_at),
        "duration_sec": int((end - begin).total_seconds()) if begin else None,
        "topic_title": r.topic_title, "topic_category": r.topic_category,
        "post_group_id": r.post_group_id, "post_ids": r.post_ids or [],
    }


def get(job_id: str) -> dict | None:
    with db.session() as s:
        row = s.get(GenerationJob, job_id)
        return to_dict(row) if row else None


def recent(limit: int = 20) -> list[dict]:
    with db.session() as s:
        return [to_dict(r) for r in s.scalars(select(GenerationJob).order_by(GenerationJob.created_at.desc()).limit(limit))]


def since(when: datetime) -> list[dict]:
    with db.session() as s:
        return [to_dict(r) for r in s.scalars(
            select(GenerationJob).where(GenerationJob.created_at >= _utc(when)).order_by(GenerationJob.created_at.desc()))]


def active() -> dict | None:
    """The queued/running job (dashboard ones first), if any."""
    with db.session() as s:
        row = s.scalars(select(GenerationJob).where(GenerationJob.status.in_(ACTIVE))
                        .order_by((GenerationJob.trigger == "dashboard").desc(), GenerationJob.created_at.desc())).first()
        return to_dict(row) if row else None


def for_group(group_id: str) -> dict | None:
    """The request that generated this post group (newest first), if it came through a job."""
    with db.session() as s:
        row = s.scalars(select(GenerationJob).where(GenerationJob.post_group_id == group_id)
                        .order_by(GenerationJob.created_at.desc())).first()
        return to_dict(row) if row else None


def by_idempotency_key(key: str) -> dict | None:
    with db.session() as s:
        row = s.scalars(select(GenerationJob).where(GenerationJob.idempotency_key == key)).first()
        return to_dict(row) if row else None


def used_today(day_start: datetime) -> int:
    """Dashboard requests since `day_start` (IST midnight). Ones GitHub refused cost nothing."""
    with db.session() as s:
        return s.scalar(select(func.count()).select_from(GenerationJob).where(
            GenerationJob.trigger == "dashboard", GenerationJob.created_at >= _utc(day_start),
            func.coalesce(GenerationJob.failure_reason, "").notin_(("dispatch_rejected", "dispatch_failed")))) or 0


def last_quota_failure(now: datetime) -> datetime | None:
    with db.session() as s:
        when = s.scalar(select(func.max(GenerationJob.finished_at)).where(
            GenerationJob.failure_reason == "quota", GenerationJob.finished_at >= _utc(now - QUOTA_COOLDOWN)))
        return _aware(when)


def last_dashboard_request(user: str | None) -> datetime | None:
    with db.session() as s:
        return _aware(s.scalar(select(func.max(GenerationJob.created_at)).where(
            GenerationJob.trigger == "dashboard", GenerationJob.requested_by == user)))


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #
def new_id() -> str:
    return secrets.token_hex(5)


def create(*, trigger: str, requested_by: str | None = None, slot_at: datetime | None = None,
           category: str | None = None, topic: str | None = None, source_url: str | None = None,
           force: bool = False, allow_duplicate: bool = False, idempotency_key: str | None = None,
           status: str = "queued", run_id: int | None = None, run_url: str | None = None) -> dict:
    """Insert a job. Raises JobActive when this trigger already has a queued/running one, Replay on a repeated key."""
    row = GenerationJob(id=new_id(), trigger=trigger, requested_by=requested_by, slot_at=slot_at and _utc(slot_at),
                        category=category, topic=topic, source_url=source_url, force=force,
                        allow_duplicate=allow_duplicate, idempotency_key=idempotency_key, status=status,
                        phase="starting" if status == "running" else None, github_run_id=run_id,
                        github_run_url=run_url, started_at=utcnow() if status == "running" else None)
    try:
        with db.session() as s:
            s.add(row)
        return to_dict(row)
    except IntegrityError as e:
        if idempotency_key and (existing := by_idempotency_key(idempotency_key)):
            raise Replay(existing) from e
        raise JobActive() from e


def _update(job_id: str, only_from: tuple[str, ...] | None, **values) -> bool:
    stmt = update(GenerationJob).where(GenerationJob.id == job_id)
    if only_from:
        stmt = stmt.where(GenerationJob.status.in_(only_from))
    with db.session() as s:
        return s.execute(stmt.values(updated_at=utcnow(), **values)).rowcount == 1


def mark_dispatched(job_id: str) -> None:
    _update(job_id, ACTIVE, dispatched_at=utcnow())


def attach_run(job_id: str, run: dict) -> None:
    """Remember which GitHub run this job is (so the UI can link it) and, once it runs, flip to running."""
    values: dict = {"github_run_id": run["id"], "github_run_url": run["url"] or None}
    if run["status"] == "in_progress":
        values.update(status="running", started_at=func.coalesce(GenerationJob.started_at, utcnow()))
    _update(job_id, ACTIVE, **values)


def set_phase(job_id: str, phase: str) -> None:
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}")
    _update(job_id, ACTIVE, phase=phase, status="running")


_EVENTS = {"succeeded": ("generate.finished", "info"), "failed": ("generate.failed", "error"),
           "skipped": ("generate.skipped", "warning"), "cancelled": ("generate.cancelled", "warning")}


def finish(job_id: str, status: str, *, reason: str | None = None, message: str = "", topic_title: str | None = None,
           category: str | None = None, group_id: str | None = None, post_ids: list[str] | None = None) -> bool:
    """Move an active job to a final state exactly once (and log it). False if it was already final."""
    if status not in TERMINAL:
        raise ValueError(f"not a final status: {status!r}")
    message = scrub(message)
    values = dict(status=status, failure_reason=reason, message=message or None, finished_at=utcnow(),
                  topic_title=topic_title, topic_category=category, post_group_id=group_id, post_ids=post_ids)
    if status == "succeeded":
        values["phase"] = "done"
    if not _update(job_id, ACTIVE, **values):
        return False
    job = get(job_id) or {}
    event, level = _EVENTS[status]
    text = {"succeeded": f"Generation {job_id} finished: “{topic_title}”",
            "failed": f"Generation {job_id} failed ({reason or 'unknown'}): {message or REASON_TEXT.get(reason or '', '')}",
            "skipped": f"Generation {job_id} skipped: {message or reason}",
            "cancelled": f"Generation {job_id} cancelled: {message or REASON_TEXT.get(reason or '', '')}"}[status]
    activity.record(event, scrub(text), level=level, source="generate", post_id=(post_ids or [None])[0],
                    actor=job.get("requested_by") or "system",
                    detail={"request_id": job_id, "reason": reason, "post_ids": post_ids or [],
                            "duration_sec": job.get("duration_sec")})
    return True


def _overdue(job: dict, now: datetime, run_waiting: bool = False) -> bool:
    began = _aware(datetime.fromisoformat(job["started_at"] or job["created_at"]))
    return now - began > (QUEUE_LIMIT if run_waiting else RUN_LIMIT)


def expire_stuck(now: datetime | None = None) -> int:
    """Database-only safety net: fail jobs that have been active far longer than any run can take."""
    now = now or utcnow()
    # A queued job may legitimately wait behind another generate run (same concurrency group).
    return sum(finish(j["id"], "failed", reason="timeout", message=REASON_TEXT["timeout"])
               for j in recent(50) if j["active"] and _overdue(j, now, run_waiting=j["status"] == "queued"))


def prune(days: int = RETENTION_DAYS) -> int:
    try:
        if not db.enabled():
            return 0
        with db.session() as s:
            return s.execute(delete(GenerationJob).where(GenerationJob.created_at < utcnow() - timedelta(days=days))).rowcount or 0
    except Exception as e:  # noqa: BLE001
        log.warning("could not prune generation jobs: %s", e)
        return 0


# --------------------------------------------------------------------------- #
# Reconcile with GitHub (the safety net when the pipeline never reported)
# --------------------------------------------------------------------------- #
def _dispatched_at(job_id: str) -> datetime | None:
    with db.session() as s:
        row = s.get(GenerationJob, job_id)
        return _aware(row.dispatched_at) if row else None


def _close_from_run(job: dict, run: dict) -> None:
    """The run is over but the job is still active: the pipeline died (or was cancelled) before reporting."""
    c = run["conclusion"]
    if c in ("cancelled", "skipped"):
        never_ran = job["status"] == "queued"
        finish(job["id"], "cancelled", reason="superseded" if never_ran else None,
               message=REASON_TEXT["superseded"] if never_ran else "The run was cancelled.")
    elif c == "timed_out":
        finish(job["id"], "failed", reason="timeout", message=REASON_TEXT["timeout"])
    else:
        finish(job["id"], "failed", reason=_PHASE_REASON.get(job["phase"] or "", "unknown"),
               message="The run ended without reporting a result. Open the GitHub run for details.")


def reconcile(job: dict, now: datetime | None = None) -> tuple[dict, bool]:
    """Bring an active job in line with its GitHub run. Returns (job, github_reachable)."""
    from src import github_actions as gh
    now = now or utcnow()
    if not job["active"]:
        return job, True
    reachable, waiting = True, False
    try:
        if gh.configured():
            run = None
            if job["github_run_id"]:
                run = gh.get_run(job["github_run_id"])
            elif job["trigger"] == "dashboard":
                run = gh.find_run(WORKFLOW, f"Generate {job['id']}", datetime.fromisoformat(job["created_at"]))
                sent = _dispatched_at(job["id"])
                if run is None and sent and now - sent > NOT_STARTED_AFTER:
                    finish(job["id"], "failed", reason="not_started", message=REASON_TEXT["not_started"])
                    return get(job["id"]) or job, True
            if run:
                if not job["github_run_id"] or run["status"] == "in_progress":
                    attach_run(job["id"], run)
                waiting = run["status"] in ("queued", "pending", "waiting", "requested")
                if run["status"] == "completed":
                    _close_from_run(job, run)
    except gh.GitHubError as e:
        reachable = False
        log.info("could not reach GitHub for %s: %s", job["id"], e)
    job = get(job["id"]) or job
    if job["active"] and _overdue(job, now, waiting):
        finish(job["id"], "failed", reason="timeout", message=REASON_TEXT["timeout"])
        job = get(job["id"]) or job
    return job, reachable


# --------------------------------------------------------------------------- #
# Reporter: what main.py generate calls. Never raises, no-op without a database.
# --------------------------------------------------------------------------- #
class Reporter:
    def __init__(self, job_id: str | None = None):
        self.job_id = job_id
        self.current: str | None = None  # last phase reported, used to classify a failure

    @classmethod
    def begin(cls, request_id: str | None, *, slot_at: datetime | None, category: str | None, topic: str | None,
              source_url: str | None, force: bool, allow_duplicate: bool) -> "Reporter":
        try:
            if not db.enabled():
                return cls()
            run_id = int(os.getenv("GITHUB_RUN_ID") or 0) or None
            repo = os.getenv("GITHUB_REPOSITORY", "")
            run_url = f"https://github.com/{repo}/actions/runs/{run_id}" if run_id and repo else None
            if valid_id(request_id) and get(request_id):
                started = dict(status="running", phase="starting", started_at=utcnow(), finished_at=None,
                               failure_reason=None, message=None, github_run_id=run_id, github_run_url=run_url,
                               slot_at=slot_at and _utc(slot_at))
                # also revives a job we gave up on as "not started" because GitHub was slow to start the run
                job = get(request_id)
                if job["status"] == "queued" or job["failure_reason"] == "not_started":
                    _update(request_id, ("queued", "failed"), **started)
                    activity.record("generate.started", f"Generation {request_id} started", source="generate",
                                    actor="system", detail={"request_id": request_id, "run_id": run_id})
                    return cls(request_id)
                return cls()  # already final (cancelled, timed out): leave it alone
            expire_stuck()  # a crashed earlier run must not block this one
            job = create(trigger="scheduled", status="running", run_id=run_id, run_url=run_url, slot_at=slot_at,
                         category=category, topic=topic, source_url=source_url, force=force,
                         allow_duplicate=allow_duplicate)
            activity.record("generate.started", f"Generation {job['id']} started", source="generate", actor="system",
                            detail={"request_id": job["id"], "run_id": run_id, "trigger": "scheduled"})
            return cls(job["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("generation job reporting is off for this run: %s", e)
            return cls()

    def _safe(self, fn, *args, **kwargs) -> None:
        if not self.job_id:
            return
        try:
            fn(self.job_id, *args, **kwargs)
        except Exception as e:  # noqa: BLE001
            log.warning("could not report to generation job %s: %s", self.job_id, e)

    def phase(self, name: str) -> None:
        self.current = name
        self._safe(set_phase, name)

    def slot(self, slot_at: datetime) -> None:
        self._safe(lambda job_id, at: _update(job_id, ACTIVE, slot_at=_utc(at)), slot_at)

    def skipped(self, reason: str, message: str) -> None:
        self._safe(finish, "skipped", reason=reason, message=message)

    def succeeded(self, topic_title: str, category: str, group_id: str, post_ids: list[str]) -> None:
        self._safe(finish, "succeeded", topic_title=topic_title, category=category, group_id=group_id, post_ids=post_ids)

    def failed(self, exc: BaseException) -> None:
        reason = classify(exc, self.current)
        self._safe(finish, "failed", reason=reason, message=f"{REASON_TEXT[reason]} {type(exc).__name__}: {exc}")


def end_run(outcome: str, request_id: str | None) -> bool:
    """CI's last-resort step: the pipeline never got to report, so close the job from the workflow."""
    if not db.enabled():
        return False
    run_id = int(os.getenv("GITHUB_RUN_ID") or 0)
    stmt = select(GenerationJob.id, GenerationJob.phase).where(GenerationJob.status.in_(ACTIVE))
    if valid_id(request_id):
        stmt = stmt.where(GenerationJob.id == request_id)
    elif run_id:
        stmt = stmt.where(GenerationJob.github_run_id == run_id)
    else:
        return False
    with db.session() as s:
        found = s.execute(stmt).first()
    if not found:
        return False
    if outcome == "cancelled":
        return finish(found[0], "cancelled", message="The run was cancelled.")
    reason = _PHASE_REASON.get(found[1] or "", "unknown")
    return finish(found[0], "failed", reason=reason, message=REASON_TEXT[reason])
