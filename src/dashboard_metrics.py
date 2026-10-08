"""Dashboard numbers, computed from plain rows. A pure function of (rows, now, config): no database, no
network, no clock reads. The live endpoint and the Demo workspace both call build_overview() with rows of
the same shape, so what a customer sees in the demo is computed by the code that runs on a real account.

Definitions (docs/specs/dashboard-section.md section 2) -- every rate carries its numerator and
denominator, and a rate over fewer than MIN_N items is reported but not judged ("too few to judge").
There is deliberately NO reach / likes / followers anywhere: the product does not measure them.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

log = logging.getLogger("codexone.dashboard")

IST = timezone(timedelta(hours=5, minutes=30))

MIN_N = 10                 # fewer decided/delivered items than this: show the numbers, no judgement
MIN_MIX_N = 20             # fewer topics than this: no deviation colouring in the content mix
PUNCTUAL_MIN = 30          # published within this many minutes of max(slot, decision) = on time
OVERDUE_MIN = 30           # approved + this long after max(slot, decision) and still unpublished = overdue
STUCK_MIN = 30             # "publishing" this long = stuck
MISSING_SLOT_HOURS = 12    # a slot with no post is only listed for this long (matches generation.LATE_LIMIT_HOURS)
SLOT_GRACE_MIN = 30
EXPIRED_LOOKBACK_DAYS = 7
FEED_SIZE = 15
ATTENTION_SHOWN = 8

APPROVED_EVER = {"approved", "publishing", "published", "failed"}
DECLINED = {"rejected", "regenerate", "replaced"}
DEFAULT_TARGETS = {"reel": ["ig", "yt"], "carousel": ["ig"]}
PLATFORM_NAME = {"ig": "Instagram", "yt": "YouTube"}
FEED_EVENTS = {"post.generated", "post.regenerated", "post.approved", "post.scheduled", "post.rejected",
               "post.published", "publish.failed", "post.expired", "generate.finished", "generate.failed"}
APPROVAL_EVENTS = {"post.approved", "post.scheduled"}
FAIL_LABEL = {"quota": "Gemini quota", "fetch": "topic fetch", "rank": "topic choice", "write": "writing",
              "render": "rendering", "upload": "media upload", "telegram": "Telegram previews", "timeout": "timeout",
              "dispatch_rejected": "GitHub refused", "dispatch_failed": "GitHub unreachable",
              "not_started": "run never started", "duplicate": "duplicate topic", "superseded": "superseded"}
_MIN_DT = datetime.min.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass
class PostRow:
    id: str
    kind: str                         # carousel | reel
    status: str
    group_id: str = ""
    topic: str = ""
    category: str = ""
    version: int = 1
    publish_at: datetime | None = None
    created_at: datetime | None = None
    decided_at: datetime | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    attempts: int = 0
    error: str | None = None
    platforms: dict = field(default_factory=dict)
    targets: list | None = None


@dataclass
class JobRow:
    id: str
    status: str                       # queued|running|succeeded|failed|skipped|cancelled
    created_at: datetime
    trigger: str = "scheduled"
    failure_reason: str | None = None


@dataclass
class EventRow:
    id: int
    created_at: datetime
    event: str
    source: str = "system"
    level: str = "info"
    message: str = ""
    post_id: str | None = None


# When the scheduled generate run fires for each slot (IST). Mirrors the crons in
# .github/workflows/daily-generate.yml ("keep in sync", README); a slot not listed shows no start time
# rather than a guessed one.
GENERATE_AT = {"10:00": "08:00", "19:00": "18:00"}


@dataclass
class Config:
    slots: list[str] = field(default_factory=lambda: ["10:00", "19:00"])   # IST "HH:MM"
    weights: dict[str, float] = field(default_factory=dict)
    max_attempts: int = 3
    expire_hours: int = 36
    handle: str = ""
    demo_enabled: bool = False
    generate_at: dict[str, str] = field(default_factory=lambda: dict(GENERATE_AT))


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def iso(dt: datetime | None) -> str | None:
    dt = aware(dt)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if dt else None


def ist_day(dt: datetime) -> date:
    return aware(dt).astimezone(IST).date()


def rate(num: int, den: int) -> dict:
    """A ratio that always shows what it was made of. `judged` is false below MIN_N."""
    return {"num": num, "den": den, "pct": round(100 * num / den) if den else None, "judged": den >= MIN_N}


def percentile(values: list[float], q: float) -> float | None:
    """Median (q = 0.5, midpoint rule) or nearest-rank percentile of a list; None when empty."""
    if not values:
        return None
    s = sorted(values)
    if q == 0.5:
        mid = len(s) // 2
        return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
    return s[max(0, math.ceil(q * len(s)) - 1)]


_SECRET = re.compile(r"(AIza[\w-]{20,}|Bearer\s+\S+|ghp_\w+|github_pat_\w+|(?:key|token|secret|password)=[^&\s]+)", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def scrub(text: str | None, limit: int = 140) -> str:
    """Whitespace collapsed, secrets and emails hidden, cut to `limit` characters."""
    t = _EMAIL.sub("[hidden]", _SECRET.sub("[hidden]", " ".join((text or "").split())))
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def safe_url(url: Any) -> str | None:
    """Only https links to Instagram / YouTube are ever rendered as links."""
    if not isinstance(url, str):
        return None
    m = re.match(r"^https://([a-z0-9.-]+)(:\d+)?(/|$)", url.strip(), re.I)
    if not m:
        return None
    host = m.group(1).lower()
    ok = any(host == d or host.endswith("." + d) for d in ("instagram.com", "youtube.com", "youtu.be"))
    return url.strip() if ok else None


def _targets(p: PostRow) -> list[str]:
    return list(p.targets) if p.targets else DEFAULT_TARGETS.get(p.kind, ["ig"])


def _rec(p: PostRow, plat: str) -> dict:
    r = (p.platforms or {}).get(plat)
    return r if isinstance(r, dict) else {}


def _slot_at(day: date, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=IST)


def _slot_times(cfg: Config) -> list[str]:
    return sorted(cfg.slots)


def _pub_at(p: PostRow) -> datetime | None:
    """When a post's publishing finished: its last platform timestamp, else published_at / updated_at."""
    stamps = []
    for r in (p.platforms or {}).values():
        if isinstance(r, dict) and r.get("at"):
            try:
                stamps.append(aware(datetime.fromisoformat(str(r["at"]).replace("Z", "+00:00"))))
            except ValueError:
                pass
    return max(stamps) if stamps else aware(p.published_at) or aware(p.updated_at)


def _group_key(p: PostRow) -> str:
    return p.group_id or p.id


def _age_min(then: datetime | None, now: datetime) -> int:
    return max(0, int((now - aware(then)).total_seconds() // 60)) if then else 0


def _norm(p: PostRow) -> PostRow:
    for f in ("publish_at", "created_at", "decided_at", "published_at", "updated_at"):
        setattr(p, f, aware(getattr(p, f)))
    return p


def _giving_up(p: PostRow, bad: list[str], max_attempts: int) -> bool:
    if bad:
        return all(int(_rec(p, pl).get("attempts") or 1) >= max_attempts for pl in bad)
    return (p.attempts or 0) >= max_attempts


# --------------------------------------------------------------------------- #
# Context shared by the section builders
# --------------------------------------------------------------------------- #
@dataclass
class Ctx:
    now: datetime
    cfg: Config
    days: int
    posts: list[PostRow]
    jobs: list[JobRow] | None
    events: list[EventRow] | None
    start: datetime = None  # type: ignore[assignment]   # IST midnight of the first day of the window
    today: date = None      # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.today = self.now.astimezone(IST).date()
        self.start = datetime.combine(self.today - timedelta(days=self.days - 1), datetime.min.time(), IST)
        self.posts = [_norm(p) for p in self.posts]

    def created_in_window(self) -> list[PostRow]:
        return [p for p in self.posts if p.created_at and p.created_at >= self.start]

    def anchor_day(self) -> date | None:
        return min((ist_day(p.created_at) for p in self.posts if p.created_at), default=None)

    def groups_by_slot_day(self) -> dict[date, int]:
        """Distinct topics per IST day of their slot, ignoring replaced versions."""
        seen: dict[date, set[str]] = {}
        for p in self.posts:
            if p.status != "replaced" and p.publish_at:
                seen.setdefault(ist_day(p.publish_at), set()).add(_group_key(p))
        return {d: len(g) for d, g in seen.items()}


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def _delivery_scope(c: Ctx) -> list[PostRow]:
    """Posts that reached a publish outcome (published, or failed) inside the window."""
    out = []
    for p in c.posts:
        if p.status in ("published", "failed"):
            at = _pub_at(p)
            if at and at >= c.start:
                out.append(p)
    return out


def _deliveries(posts: list[PostRow]) -> dict:
    pub = fail = first = 0
    skipped: list[dict] = []
    by_plat = {pl: {"published": 0, "failed": 0, "skipped": 0} for pl in PLATFORM_NAME}
    for p in posts:
        for pl in _targets(p):
            if pl not in by_plat:
                continue
            r = _rec(p, pl)
            st = r.get("status")
            if st == "published":
                pub += 1
                by_plat[pl]["published"] += 1
                if int(r.get("attempts") or 1) == 1:
                    first += 1
            elif st == "failed":
                fail += 1
                by_plat[pl]["failed"] += 1
            elif st == "skipped":
                by_plat[pl]["skipped"] += 1
                skipped.append({"platform": pl, "reason": scrub(r.get("error"), 80)})
    return {"pub": pub, "fail": fail, "first": first, "skipped": skipped, "by": by_plat}


def kpis(c: Ctx) -> dict:
    inwin = c.created_in_window()
    # 1. Posts published
    published = [p for p in c.posts if p.status == "published" and p.published_at and p.published_at >= c.start]
    deliveries = sum(1 for p in published for pl in _targets(p) if _rec(p, pl).get("status") == "published")
    # 2. Approval rate = approved-ever / decided (pending and expired are not decisions)
    ever = [p for p in inwin if p.status in APPROVED_EVER]
    declined = [p for p in inwin if p.status in DECLINED]
    first_ever = [p for p in ever if p.version == 1]
    first_declined = [p for p in declined if p.version == 1]
    # 3. Publish success
    d = _deliveries(_delivery_scope(c))
    # 4. Time to approve (an upper bound: decided_at is the LAST decision; Telegram taps are stamped at poll time)
    delays = [(p.decided_at - p.created_at).total_seconds() / 60 for p in ever
              if p.decided_at and p.created_at and p.decided_at >= p.created_at]
    # 5. Punctuality: published within PUNCTUAL_MIN of max(slot, decision)
    on_time = timed = 0
    for p in published:
        if p.publish_at:
            timed += 1
            ready = max(p.publish_at, p.decided_at) if p.decided_at else p.publish_at
            if p.published_at - ready <= timedelta(minutes=PUNCTUAL_MIN):
                on_time += 1
    return {
        "ok": True,
        "posts_published": {"count": len(published), "topics": len({_group_key(p) for p in published}),
                            "deliveries": deliveries},
        "approval": {**rate(len(ever), len(ever) + len(declined)),
                     "first_pass": rate(len(first_ever), len(first_ever) + len(first_declined)),
                     "expired": sum(1 for p in inwin if p.status == "expired"),
                     "pending": sum(1 for p in inwin if p.status == "pending")},
        "publish_success": {**rate(d["pub"], d["pub"] + d["fail"]),
                            "first_attempt": rate(d["first"], d["pub"] + d["fail"]),
                            "skipped": d["skipped"][:5], "skipped_count": len(d["skipped"])},
        "time_to_approve": {"n": len(delays), "median_min": percentile(delays, 0.5), "p90_min": percentile(delays, 0.9),
                            "judged": len(delays) >= MIN_N, "upper_bound": True},
        "punctuality": {**rate(on_time, timed), "threshold_min": PUNCTUAL_MIN},
    }


def _item(code: str, sev: str, title: str, detail: str, age: int, *, post: PostRow | None = None,
          to: str = "/posts", label: str = "Open") -> dict:
    if post is not None:
        to = f"/posts?post={post.id}"
    out = {"code": code, "severity": sev, "title": title, "detail": detail, "age_min": age,
           "post_id": post.id if post else None, "kinds": [post.kind] if post else [],
           "action": {"label": label, "to": to}}
    if post is not None:
        out["_group"] = _group_key(post)
        out["_topic"] = scrub(post.topic, 60)
    return out


_WHAT = "\x00WHAT\x00"   # placeholder for "Reel “X”" / "Reel and carousel “X”", filled after merging


def _what(kinds: list[str], topic: str) -> str:
    names = [k for k in ("reel", "carousel") if k in kinds] or kinds
    return f"{' and '.join(names).capitalize()} “{topic}”"


def _merge_same_topic(items: list[dict]) -> list[dict]:
    """The reel and the carousel of one topic usually need the same thing at the same time: one row, not two."""
    rank = {"high": 0, "medium": 1, "low": 2}
    merged: dict[tuple, dict] = {}
    out: list[dict] = []
    for it in items:
        g = it.get("_group")
        key = (it["code"], g, it["title"]) if g else None    # same need, same wording (e.g. same platform failed)
        if key and key in merged:
            m = merged[key]
            m["kinds"] = sorted(set(m["kinds"]) | set(it["kinds"]), key=("reel", "carousel").index)
            if rank[it["severity"]] < rank[m["severity"]]:
                m["severity"] = it["severity"]
            m["age_min"] = max(m["age_min"], it["age_min"])
            continue
        if key:
            merged[key] = it
        out.append(it)
    for it in out:
        topic = it.pop("_topic", "")
        it.pop("_group", None)
        it["title"] = it["title"].replace(_WHAT, _what(it["kinds"], topic))
    return out


def _clock(mins: float) -> str:
    mins = int(mins)
    return f"{mins}m" if mins < 60 else f"{mins // 60}h {mins % 60:02d}m" if mins < 48 * 60 else f"{mins // 1440}d"


def attention(c: Ctx) -> dict:
    now, cfg = c.now, c.cfg
    items: list[dict] = []
    auth_yt = auth_ig = False
    for p in c.posts:
        t = _WHAT
        if p.status not in ("failed", "approved", "publishing", "pending", "expired"):
            continue  # most rows (published, rejected, replaced): nothing to flag, skip the formatting
        slot = p.publish_at.astimezone(IST).strftime("%H:%M") if p.publish_at else "?"
        if p.status == "failed":
            bad = [pl for pl in _targets(p) if _rec(p, pl).get("status") == "failed"]
            tries = max([int(_rec(p, pl).get("attempts") or 1) for pl in bad] or [p.attempts or 1])
            why = scrub(next((_rec(p, pl).get("error") for pl in bad if _rec(p, pl).get("error")), p.error), 90)
            names = " and ".join(PLATFORM_NAME[pl] for pl in bad) or "Publishing"
            if _giving_up(p, bad, cfg.max_attempts):
                items.append(_item("failed_final", "high", f"{names} failed {tries}x: {t}",
                                   f"{why or 'No reason recorded'}. Automatic retries are used up.",
                                   _age_min(p.updated_at, now), post=p, label="Retry"))
            else:
                items.append(_item("failed_retrying", "medium", f"{names} failed, retrying: {t}",
                                   f"{why or 'No reason recorded'}. Retries automatically at the next check.",
                                   _age_min(p.updated_at, now), post=p, label="Look"))
            err = (" ".join(str(_rec(p, pl).get("error") or "") for pl in bad) + " " + (p.error or "")).lower()
            if "refresh token rejected" in err or "invalid_grant" in err:
                auth_yt = True
            if re.search(r"\b190\b", err) or "access token" in err:
                auth_ig = True
        elif p.status == "approved" and p.publish_at:
            ready = max(p.publish_at, p.decided_at) if p.decided_at else p.publish_at
            late = (now - ready).total_seconds() / 60
            if late > OVERDUE_MIN:
                items.append(_item("overdue", "high", f"Approved for {slot}, not live yet: {t}",
                                   f"{_clock(late)} past its slot. The checker may not be running.",
                                   int(late), post=p, label="Open"))
        elif p.status == "publishing" and p.updated_at and now - p.updated_at > timedelta(minutes=STUCK_MIN):
            items.append(_item("stuck", "high", f"Publishing seems stuck: {t}",
                               f"No progress for {_clock(_age_min(p.updated_at, now))}.",
                               _age_min(p.updated_at, now), post=p, label="Open"))
        elif p.status == "pending" and p.created_at:
            left = (p.created_at + timedelta(hours=cfg.expire_hours) - now).total_seconds() / 3600
            passed = bool(p.publish_at and p.publish_at <= now)
            sev = "high" if left < 6 else "medium" if passed else "low"
            exp = f"expires in {_clock(left * 60)}" if left > 0 else "expires at the next check"
            items.append(_item("pending", sev, f"Waiting for your decision: {t}",
                               f"Slot {slot} IST{' (passed)' if passed else ''}; {exp}.",
                               _age_min(p.created_at, now), post=p, label="Review"))
        elif p.status == "expired" and p.updated_at and now - p.updated_at <= timedelta(days=EXPIRED_LOOKBACK_DAYS):
            items.append(_item("expired", "low", f"Expired without a decision: {t}",
                               "Revive it from Posts, or ignore it.", _age_min(p.updated_at, now), post=p, label="Open"))
    # Slots that came and went without a topic (count-based, so a rescheduled post doesn't confuse it).
    per_day = c.groups_by_slot_day()
    first_seen = min((p.created_at for p in c.posts if p.created_at), default=None)
    for day in (c.today - timedelta(days=1), c.today):
        for i, hhmm in enumerate(_slot_times(cfg)):
            at = _slot_at(day, hhmm)
            since = (now - at).total_seconds() / 60
            if SLOT_GRACE_MIN < since < MISSING_SLOT_HOURS * 60 and first_seen and first_seen < at \
                    and per_day.get(day, 0) <= i:
                items.append(_item("slot_empty", "high", f"The {hhmm} slot has no post",
                                   f"{_clock(since)} ago. Generation didn't produce one for it.", int(since),
                                   to="/logs", label="See logs"))
    if c.jobs:
        last = max(c.jobs, key=lambda j: aware(j.created_at))
        if last.status == "failed" and now - aware(last.created_at) < timedelta(hours=24):
            why = FAIL_LABEL.get(last.failure_reason or "", "unknown reason")
            more = " Free quota refills daily." if last.failure_reason == "quota" else ""
            items.append(_item("generation_failed", "medium", f"Generation failed: {why}",
                               "The last run did not produce a post." + more, _age_min(last.created_at, now),
                               to="/logs", label="See logs"))
    if auth_yt:
        items.append(_item("yt_auth", "high", "YouTube login expired", "Reconnect YouTube, then retry the failed posts.",
                           0, to="/posts?status=failed", label="Open failed posts"))
    if auth_ig:
        items.append(_item("ig_auth", "high", "Instagram token rejected",
                           "Refresh the Instagram token, then retry the failed posts.", 0,
                           to="/posts?status=failed", label="Open failed posts"))
    items = _merge_same_topic(items)
    rank = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda i: (rank[i["severity"]], -i["age_min"]))
    last_decision = max((p.decided_at for p in c.posts if p.decided_at), default=None)
    return {"ok": True, "total": len(items), "items": items[:ATTENTION_SHOWN],
            "high": sum(i["severity"] == "high" for i in items), "medium": sum(i["severity"] == "medium" for i in items),
            "last_decision_at": iso(last_decision)}


def _gen_start(cfg: Config, slot_at: datetime, hhmm: str) -> str | None:
    g = (cfg.generate_at or {}).get(hhmm)
    if not g:
        return None
    start = _slot_at(slot_at.astimezone(IST).date(), g)
    return iso(start if start <= slot_at else start - timedelta(days=1))


def next_slots(c: Ctx) -> dict:
    if not c.cfg.slots:
        return {"ok": True, "items": [], "configured": False}
    by_slot: dict[str, list[PostRow]] = {}
    for p in c.posts:
        if p.publish_at and p.status != "replaced":
            by_slot.setdefault(p.publish_at.astimezone(IST).strftime("%Y-%m-%d %H:%M"), []).append(p)

    def chip(p: PostRow | None) -> dict | None:
        if not p:
            return None
        return {"id": p.id, "status": p.status, "publish_at": iso(p.publish_at), "targets": _targets(p),
                "platforms": {k: {"status": v.get("status")} for k, v in (p.platforms or {}).items() if isinstance(v, dict)},
                "error": scrub(p.error, 120) or None}

    out = []
    for offset in range(0, 4):
        for hhmm in _slot_times(c.cfg):
            at = _slot_at(c.today + timedelta(days=offset), hhmm)
            if at <= c.now:
                continue
            cur: dict[str, PostRow] = {}
            for p in sorted(by_slot.get(at.strftime("%Y-%m-%d %H:%M"), []), key=lambda p: (p.version, p.created_at or at)):
                cur[p.kind] = p
            head = cur.get("reel") or cur.get("carousel")
            out.append({"slot_at": iso(at), "label": hhmm, "in_min": int((at - c.now).total_seconds() // 60),
                        "generated": head is not None, "topic": scrub(head.topic, 90) if head else None,
                        "category": head.category if head else None, "reel": chip(cur.get("reel")),
                        "carousel": chip(cur.get("carousel")),
                        "generation_starts": _gen_start(c.cfg, at, hhmm) if not head else None})
            if len(out) == 4:
                return {"ok": True, "items": out, "configured": True}
    return {"ok": True, "items": out, "configured": True}


def cadence(c: Ctx) -> dict:
    exp = 2 * len(c.cfg.slots)
    by_day: dict[date, list[PostRow]] = {}
    for p in c.posts:
        if p.status == "published" and p.published_at:
            by_day.setdefault(ist_day(p.published_at), []).append(p)
    anchor = c.anchor_day()
    days = []
    for i in range(c.days):
        d = c.today - timedelta(days=c.days - 1 - i)
        n = len(by_day.get(d, []))
        if anchor is None or d < anchor or not exp:
            state = "none"
        elif n >= exp:
            state = "full"
        elif d == c.today:
            state = "today"
        else:
            state = "partial" if n else "missed"
        days.append({"date": d.isoformat(), "n": n, "topics": len({_group_key(p) for p in by_day.get(d, [])}),
                     "expected": 0 if state == "none" else exp, "state": state})
    counted = [x for x in days if x["state"] in ("full", "partial", "missed")]
    streak = 0
    for x in reversed(days):
        if x["state"] == "today":
            continue
        if x["state"] != "full":
            break
        streak += 1
    today_full = days[-1]["state"] == "full"
    return {"ok": True, "days": days, "full_days": sum(x["state"] == "full" for x in counted), "counted_days": len(counted),
            "streak": streak, "today_full": today_full, "expected_per_day": exp}


def mix(c: Ctx) -> dict:
    groups: dict[str, list[PostRow]] = {}
    for p in c.posts:
        groups.setdefault(_group_key(p), []).append(p)
    counts: dict[str, int] = {}
    for members in groups.values():
        stamps = [m.created_at for m in members if m.created_at]
        if not stamps or min(stamps) < c.start:
            continue
        live = [m for m in members if m.status != "replaced"] or members
        head = max(live, key=lambda m: (m.version, m.created_at or _MIN_DT))
        cat = head.category or "other"
        counts[cat] = counts.get(cat, 0) + 1
    n = sum(counts.values())
    total_w = sum(c.cfg.weights.values()) or 0
    judged = n >= MIN_MIX_N
    cats = []
    for cat in list(c.cfg.weights) + [k for k in counts if k not in c.cfg.weights]:
        target = (100 * c.cfg.weights[cat] / total_w) if total_w and cat in c.cfg.weights else None
        share = round(100 * counts.get(cat, 0) / n, 1) if n else 0.0
        margin = round(196 * math.sqrt((target / 100) * (1 - target / 100) / n)) if target and n else None
        delta = round(share - target, 1) if target is not None else None
        tone = "idle"
        if judged and delta is not None and margin is not None:
            tone = "off" if abs(delta) > margin else "on"
        cats.append({"category": cat, "count": counts.get(cat, 0), "share": share,
                     "target": round(target, 1) if target is not None else None, "delta": delta, "margin": margin,
                     "tone": tone})
    return {"ok": True, "n": n, "judged": judged, "min_n": MIN_MIX_N, "categories": cats}


def funnel(c: Ctx) -> dict:
    """Every post created in the window lands in exactly one bucket, so the buckets sum to Generated."""
    rows = c.created_in_window()
    b = {"published": 0, "waiting": 0, "retrying": 0, "failed": 0, "pending": 0, "rejected": 0, "regenerated": 0,
         "expired": 0}
    for p in rows:
        st = p.status
        if st == "published":
            b["published"] += 1
        elif st in ("approved", "publishing"):
            b["waiting"] += 1
        elif st == "failed":
            bad = [pl for pl in _targets(p) if _rec(p, pl).get("status") == "failed"]
            b["failed" if _giving_up(p, bad, c.cfg.max_attempts) else "retrying"] += 1
        elif st == "rejected":
            b["rejected"] += 1
        elif st in ("replaced", "regenerate"):
            b["regenerated"] += 1
        elif st == "expired":
            b["expired"] += 1
        else:
            b["pending"] += 1
    total = len(rows)
    approved = b["published"] + b["waiting"] + b["failed"] + b["retrying"]
    stages = [{"key": "generated", "label": "Generated", "n": total},
              {"key": "decided", "label": "Decided", "n": total - b["pending"] - b["expired"]},
              {"key": "approved", "label": "Approved", "n": approved},
              {"key": "published", "label": "Published", "n": b["published"]}]
    leaks = [{"key": k, "n": b[k]} for k in ("rejected", "regenerated", "expired", "failed", "retrying", "pending", "waiting")]
    return {"ok": True, "total": total, "stages": stages, "buckets": b, "leaks": leaks}


BINS = [("under 30 min", 30), ("under 2 h", 120), ("under 6 h", 360), ("under 24 h", 1440), ("24 h or more", math.inf)]


def turnaround(c: Ctx) -> dict:
    ever = [p for p in c.created_in_window() if p.status in APPROVED_EVER and p.decided_at and p.created_at
            and p.decided_at >= p.created_at]
    delays = [(p.decided_at - p.created_at).total_seconds() / 60 for p in ever]
    bins = [0] * len(BINS)
    for m in delays:
        for i, (_, hi) in enumerate(BINS):
            if m < hi:
                bins[i] += 1
                break
    channels: dict[str, list[float]] = {}
    if c.events:
        created = {p.id: p.created_at for p in c.posts if p.created_at}
        seen: set[str] = set()
        for e in sorted(c.events, key=lambda e: aware(e.created_at)):
            if e.event in APPROVAL_EVENTS and e.post_id and e.post_id not in seen and e.post_id in created \
                    and aware(e.created_at) >= c.start and e.source in ("telegram", "dashboard"):
                seen.add(e.post_id)
                channels.setdefault(e.source, []).append(max(0.0, (aware(e.created_at) - created[e.post_id]).total_seconds() / 60))
    return {"ok": True, "n": len(delays), "judged": len(delays) >= MIN_N, "median_min": percentile(delays, 0.5),
            "p90_min": percentile(delays, 0.9),
            "bins": [{"label": lab, "n": n} for (lab, _), n in zip(BINS, bins)],
            "channels": [{"channel": k, "n": len(v), "median_min": percentile(v, 0.5)} for k, v in sorted(channels.items())]}


def _generation(c: Ctx) -> dict:
    if c.jobs is None:
        return {"ok": False, "error": "unavailable"}
    if not c.jobs:
        return {"ok": True, "tracking_since": None, "runs": 0}
    inwin = [j for j in c.jobs if aware(j.created_at) >= c.start]
    ok_n = sum(j.status == "succeeded" for j in inwin)
    bad_n = sum(j.status == "failed" for j in inwin)
    ordered = sorted(c.jobs, key=lambda j: aware(j.created_at), reverse=True)
    last = next((j for j in ordered if j.status not in ("queued", "running")), None)
    streak = 0
    for j in ordered:
        if j.status == "succeeded":
            streak += 1
        elif j.status == "failed":
            break
    last_fail = next((j for j in ordered if j.status == "failed"), None)
    return {"ok": True, "tracking_since": iso(min(aware(j.created_at) for j in c.jobs)), "runs": len(inwin),
            "success": rate(ok_n, ok_n + bad_n),
            "skipped": sum(j.status == "skipped" for j in inwin), "cancelled": sum(j.status == "cancelled" for j in inwin),
            "last": {"at": iso(last.created_at), "status": last.status} if last else None,
            "last_failure": FAIL_LABEL.get(last_fail.failure_reason or "", "unknown") if last_fail else None,
            "streak": streak}


def pipeline(c: Ctx) -> dict:
    """Slot fill rate comes from posts alone, so it has data from day one; job figures say 'tracking since'."""
    per_day = c.groups_by_slot_day()
    anchor = c.anchor_day()
    elapsed = filled = 0
    for i in range(c.days):
        d = c.today - timedelta(days=c.days - 1 - i)
        if anchor is None or d < anchor:
            continue
        n_elapsed = sum(1 for h in c.cfg.slots if _slot_at(d, h) + timedelta(minutes=SLOT_GRACE_MIN) <= c.now)
        elapsed += n_elapsed
        filled += min(per_day.get(d, 0), n_elapsed)
    published = [p.published_at for p in c.posts if p.status == "published" and p.published_at]
    return {"ok": True, "generation": _guard(lambda: _generation(c)), "slot_fill": rate(filled, elapsed),
            "publishing": {"last_published_at": iso(max(published)) if published else None,
                           "failed_deliveries": _deliveries(_delivery_scope(c))["fail"]}}


def platforms(c: Ctx, links: bool = True) -> dict:
    d = _deliveries(_delivery_scope(c))
    ordered = sorted(c.posts, key=lambda p: _pub_at(p) or _MIN_DT, reverse=True)
    items = []
    for pl in ("ig", "yt"):
        by = d["by"][pl]
        recent = []
        for p in ordered:
            r = _rec(p, pl)
            if pl in _targets(p) and r.get("status") == "published":
                recent.append({"post_id": p.id, "topic": scrub(p.topic, 70), "kind": p.kind,
                               "at": r.get("at") or iso(p.published_at),
                               "url": safe_url(r.get("url")) if links else None,
                               "privacy": r.get("privacy") if pl == "yt" else None})
                if len(recent) == 5:
                    break
        items.append({"platform": pl, "name": PLATFORM_NAME[pl], "published": by["published"], "failed": by["failed"],
                      "skipped": by["skipped"], "success": rate(by["published"], by["published"] + by["failed"]),
                      "recent": recent})
    return {"ok": True, "items": items}


def recent_posts(c: Ctx) -> dict:
    groups: dict[str, list[PostRow]] = {}
    for p in c.posts:
        if p.status == "published":
            groups.setdefault(_group_key(p), []).append(p)
    ranked = sorted(groups.values(), key=lambda m: max(_pub_at(x) or _MIN_DT for x in m), reverse=True)[:8]
    out = []
    for members in ranked:
        head = max(members, key=lambda m: m.kind == "reel")
        car = next((m for m in members if m.kind == "carousel"), None)
        chips = [{"platform": pl, "kind": m.kind, "status": _rec(m, pl).get("status")}
                 for m in members for pl in _targets(m) if _rec(m, pl)]
        out.append({"group_id": head.group_id or head.id, "post_id": head.id, "carousel_id": car.id if car else None,
                    "topic": scrub(head.topic, 90), "category": head.category,
                    "at": iso(max(_pub_at(x) or _MIN_DT for x in members)), "chips": chips, "thumb": None})
    return {"ok": True, "items": out}


ACTOR = {"telegram": "Telegram", "dashboard": "You"}


def activity_feed(c: Ctx) -> dict:
    if c.events is None:
        return {"ok": False, "error": "unavailable"}
    rows = sorted((e for e in c.events if e.event in FEED_EVENTS), key=lambda e: e.id, reverse=True)
    return {"ok": True, "items": [
        {"id": e.id, "at": iso(e.created_at), "event": e.event, "level": e.level, "actor": ACTOR.get(e.source, "System"),
         "message": scrub(e.message, 140), "post_id": e.post_id} for e in rows[:FEED_SIZE]]}


# --------------------------------------------------------------------------- #
# Whole overview
# --------------------------------------------------------------------------- #
def _guard(fn: Callable[[], dict]) -> dict:
    """One failing section must never blank the page, nor leak an exception text to the browser."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        log.exception("dashboard section failed")
        return {"ok": False, "error": "unavailable"}


def _status(c: Ctx, att: dict, slots: dict) -> dict:
    if not att.get("ok"):
        return {"ok": False, "state": "unknown", "needs_count": 0, "reason": "Couldn't check what needs you"}
    top = att["items"][0] if att["items"] else None
    today = [p for p in c.posts if p.status == "published" and p.published_at and ist_day(p.published_at) == c.today]
    nxt = (slots.get("items") or [None])[0] if slots.get("ok") else None
    return {"ok": True, "state": "action" if att["high"] else "heads_up" if att["medium"] else "ok",
            "needs_count": att["total"], "reason": top["title"] if top else None, "today_published": len(today),
            "today_expected": 2 * len(c.cfg.slots), "next_slot_at": nxt["slot_at"] if nxt else None}


def build_overview(posts: list[PostRow] | None, jobs: list[JobRow] | None, events: list[EventRow] | None, *,
                   now: datetime, cfg: Config, days: int = 30, workspace: str = "live") -> dict:
    """`None` for posts/jobs/events means that source could not be read: its sections say 'unavailable'."""
    now = aware(now)
    days = 90 if days == 90 else 30
    demo = workspace == "demo"
    c = Ctx(now=now, cfg=cfg, days=days, posts=list(posts or []), jobs=jobs, events=events)
    unavailable = {"ok": False, "error": "unavailable"}

    def sec(fn: Callable[[Ctx], dict]) -> dict:
        return unavailable if posts is None else _guard(lambda: fn(c))

    att, slots = sec(attention), sec(next_slots)
    total_w = sum(cfg.weights.values()) or 0
    return {
        "workspace": workspace, "demo": demo, "handle": cfg.handle, "generated_at": iso(now), "window_days": days,
        "config": {"slots": _slot_times(cfg), "expected_per_day": 2 * len(cfg.slots), "timezone": "IST",
                   "categories": [{"category": k, "weight": v, "target": round(100 * v / total_w, 1) if total_w else None}
                                  for k, v in cfg.weights.items()],
                   "thresholds": {"min_n": MIN_N, "min_mix_n": MIN_MIX_N, "punctual_min": PUNCTUAL_MIN,
                                  "max_attempts": cfg.max_attempts, "expire_hours": cfg.expire_hours},
                   "demo_enabled": cfg.demo_enabled},
        "status": _guard(lambda: _status(c, att, slots)) if posts is not None
        else {"ok": False, "state": "unknown", "needs_count": 0, "reason": "Couldn't check what needs you"},
        "kpis": sec(kpis), "attention": att, "next_slots": slots, "cadence": sec(cadence), "mix": sec(mix),
        "funnel": sec(funnel), "turnaround": sec(turnaround), "pipeline": sec(pipeline),
        "platforms": sec(lambda c: platforms(c, links=not demo)), "recent_posts": sec(recent_posts),
        "activity": _guard(lambda: activity_feed(c)),
    }
