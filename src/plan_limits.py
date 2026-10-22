"""What a user's plan lets them generate, schedule and publish (catalogue: src/plans.py).

    from src import plan_limits
    plan_limits.check_generation(user)      # raises PlanLimit; returns {"reel": bool} (False = carousel only)
    plan_limits.check_cadence(user, cadence)
    plan_limits.check_targets(user, ["ig", "yt"])
    plan_limits.check_regenerate(item)
    plan_limits.allowed_platforms(user_id)  # None = unrestricted, () = no active plan
    plan_limits.summary(user)               # usage this month, for the Subscription page

Rules:
- A plan counts only while it is paid for: status active, past_due (Razorpay retrying), canceling or changing
  (both run to the end of the paid period). Anything else is "no plan": nothing is generated or published.
- Quotas are per calendar month in IST and count new posts only (version 1 of each reel and carousel), whatever
  happened to them afterwards: the work was done. Regenerations don't use quota, but each post can be
  regenerated at most MAX_REGENERATIONS times.
- When the month's reels are used up but carousels remain, a run makes the carousel only.
- The owner account (users.role = "owner") runs the brand's own posts and is not limited. Without a database
  (local file mode) there are no accounts, so nothing is limited either.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src import db
from src.plans import BY_ID

IST = ZoneInfo("Asia/Kolkata")
PAID = ("active", "past_due", "canceling", "changing")
MAX_REGENERATIONS = 3
NO_PLAN = {"id": "free", "name": "Free", "posts_per_day": 1, "quota": {"reels": 0, "carousels": 0},
           "platforms": []}


class PlanLimit(Exception):
    """`code`: plan_required | quota_reached | too_many_slots | platform_not_in_plan | regenerate_limit."""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra


def is_exempt(user) -> bool:
    return user is None or (getattr(user, "role", "") or "") == "owner"


def plan_for(user) -> dict:
    """The plan the user is paying for right now, or NO_PLAN."""
    tier = (getattr(user, "subscription_tier", "") or "").lower()
    status = getattr(user, "subscription_status", "") or ""
    return BY_ID.get(tier, NO_PLAN) if status in PAID else NO_PLAN


def load_user(user_id: int | None):
    """The user row (detached, read-only use), or None without a database or for an unknown id."""
    if not db.enabled() or not user_id:
        return None
    from src.db.models import User
    with db.session() as s:
        user = s.get(User, user_id)
        if user is not None:
            s.expunge(user)
        return user


def month_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """This calendar month in IST: [first day 00:00, first day of next month 00:00)."""
    now = (now or datetime.now(IST)).astimezone(IST)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def usage(user_id: int, now: datetime | None = None) -> dict[str, int]:
    """New reels and carousels the user's runs made this month (regenerated versions not counted)."""
    if not db.enabled():
        return {"reels": 0, "carousels": 0}
    from sqlalchemy import func, select
    from src.db.models import Post
    start, end = month_window(now)
    with db.session() as s:
        rows = s.execute(select(Post.kind, func.count()).where(
            Post.user_id == user_id, Post.version == 1, Post.created_at >= start, Post.created_at < end)
            .group_by(Post.kind)).all()
    counts = {kind: n for kind, n in rows}
    return {"reels": counts.get("reel", 0), "carousels": counts.get("carousel", 0)}


def _resets(now: datetime | None) -> str:
    return f"{month_window(now)[1]:%d %b}".lstrip("0")


def summary(user, now: datetime | None = None) -> dict:
    """The plan, this month's usage and what's left (None = unlimited), for the dashboard."""
    plan = plan_for(user)
    exempt = is_exempt(user)
    used = usage(user.id, now) if user is not None else {"reels": 0, "carousels": 0}
    quota = plan["quota"]
    return {
        "plan": plan["id"], "exempt": exempt, "used": used,
        "quota": None if exempt else quota,
        "left": None if exempt else {k: max(0, quota[k] - used[k]) for k in quota},
        "platforms": ["ig", "yt"] if exempt else plan["platforms"],
        "posts_per_day": None if exempt else plan["posts_per_day"],
        "max_regenerations": None if exempt else MAX_REGENERATIONS,
        "resets_at": month_window(now)[1].isoformat(),
    }


def check_generation(user, now: datetime | None = None) -> dict:
    """May this user start a run now? Returns {"reel": bool}: False means make the carousel only."""
    if is_exempt(user):
        return {"reel": True}
    plan = plan_for(user)
    if plan is NO_PLAN:
        raise PlanLimit("plan_required", "Choose a plan to start generating posts.")
    used, quota = usage(user.id, now), plan["quota"]
    if used["carousels"] >= quota["carousels"]:
        raise PlanLimit("quota_reached",
                        f"You've used all {quota['carousels']} posts in your {plan['name']} plan this month. "
                        f"They reset on {_resets(now)}, or upgrade to post more.",
                        used=used, quota=quota, resets_at=month_window(now)[1].isoformat())
    return {"reel": used["reels"] < quota["reels"]}


def slots_per_day(cadence: dict | None) -> int:
    """The most posts any one day of this schedule holds (see approve_bot.post_times_for_cadence)."""
    if not cadence:
        return 0
    mode = cadence.get("schedule_mode", "uniform")
    if mode == "weekly":
        days = (cadence.get("weekly_slots") or {}).values()
        per_day = max((len({t for t in (slots or []) if t}) for slots in days), default=0)
    elif mode == "ai":
        merged = {t for times in (cadence.get("ai_schedule") or {}).values() for t in (times or []) if t}
        per_day = len(merged) or len({t for t in (cadence.get("slots") or []) if t})
    else:
        per_day = len({t for t in (cadence.get("slots") or []) if t})
    return max(per_day, int(cadence.get("posts_per_day") or 0))


def check_cadence(user, cadence: dict | None) -> None:
    """A schedule may hold no more posts a day than the plan allows (1 without a plan: a preview of a schedule)."""
    if is_exempt(user):
        return
    plan = plan_for(user)
    cap, have = plan["posts_per_day"], slots_per_day(cadence)
    if have > cap:
        raise PlanLimit("too_many_slots",
                        f"Your {plan['name']} plan allows {cap} post{'s' if cap != 1 else ''} a day; this schedule "
                        f"has {have}. Remove a slot or upgrade.", allowed=cap)


def check_targets(user, targets: list[str] | None) -> None:
    """Default platforms must be in the plan (Lite: Instagram only). Without a plan nothing publishes anyway."""
    if is_exempt(user) or not targets:
        return
    plan = plan_for(user)
    if plan is NO_PLAN:
        return
    extra = [t for t in targets if t not in plan["platforms"]]
    if extra:
        names = {"yt": "YouTube Shorts", "ig": "Instagram"}
        raise PlanLimit("platform_not_in_plan",
                        f"{', '.join(names.get(t, t) for t in extra)} isn't in your {plan['name']} plan. "
                        "Upgrade to post there.", platforms=plan["platforms"])


def allowed_platforms(user_id: int | None) -> tuple[str, ...] | None:
    """Where this owner's posts may be published: None = unrestricted, () = nowhere (no active plan)."""
    user = load_user(user_id)
    if user is None or is_exempt(user):
        return None
    return tuple(plan_for(user)["platforms"])


def check_regenerate(item) -> None:
    """Each post can be regenerated MAX_REGENERATIONS times (version 1 is the original)."""
    user = load_user(getattr(item, "user_id", None))
    if user is None or is_exempt(user):
        return
    if (item.version or 1) > MAX_REGENERATIONS:
        raise PlanLimit("regenerate_limit",
                        f"This post has already been regenerated {MAX_REGENERATIONS} times, the most a plan allows. "
                        "Reject it and generate a new one instead.")
