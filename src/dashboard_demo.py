"""Synthetic rows for the dashboard's Demo workspace.

Built entirely in memory from a fixed seed (dates are relative to `now`, so the demo is always fresh) and
fed through the SAME aggregator as live data (src.dashboard_metrics.build_overview). It never touches the
database, Telegram, Cloudinary, GitHub, Gemini, Instagram or YouTube; this module imports none of them.

Everything in here is fictional: a made-up handle, made-up evergreen topics (technically correct),
no real URLs, ids prefixed "demo-". Numbers are deliberately unglamorous (some rejections, regenerations,
two expiries, two publishes that needed a retry, one YouTube upload that gave up after three tries,
one quota-failed run). There is NO engagement, reach,
follower or "hours saved" figure, because the product does not measure them.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta

from src.dashboard_metrics import (IST, Config, EventRow, JobRow, PostRow, aware, iso)

HANDLE = "@demo_dev_daily"
SEED = 20261005
HISTORY_DAYS = 42
SLOTS = ["10:00", "19:00"]
WEIGHTS = {"AI": 30, "SystemDesign": 20, "DSA": 20, "Interview": 15, "OS": 10, "Dev": 5}

TOPICS: dict[str, list[str]] = {
    "AI": ["What a context window actually is", "Why language models hallucinate", "Embeddings in one minute",
           "RAG or fine-tuning: how to choose", "What temperature does to model output", "Tokens are not words",
           "Prompt injection in plain English", "Why evals beat vibes", "How a transformer attends to context",
           "Vector search versus keyword search", "Guardrails: where to put them", "What a system prompt can and cannot do",
           "Chunking documents for retrieval", "Why small models can be enough", "Structured output and JSON schemas",
           "How tool calling works", "Caching prompts to cut latency", "Why models forget the middle of long prompts",
           "Streaming responses: why it feels faster", "Batch inference versus real time", "What fine-tuning data should look like", "Why long prompts cost more", "Hallucination checks you can automate"],
    "SystemDesign": ["Cache-aside versus write-through", "Why load balancers need health checks",
                     "Idempotency keys for payment APIs", "Consistent hashing, explained", "What a message queue buys you",
                     "Rate limiting with a token bucket", "Read replicas and replication lag", "CDN: what actually gets cached",
                     "Database indexes: the cost side", "Back-pressure in one picture", "Retries with exponential backoff",
                     "Circuit breakers, explained", "Sharding versus partitioning", "Eventual consistency without the jargon",
                     "Blue-green versus canary deploys", "Why timeouts need budgets", "Write-ahead logs in one picture", "Bloom filters: no false negatives", "Leader election without magic"],
    "DSA": ["Two pointers on a sorted array", "Why hash map lookups are O(1) on average", "Binary search off-by-one traps",
            "BFS versus DFS: pick by the question", "Sliding window in 60 seconds", "Heap versus sorted array for top-K",
            "Detecting a cycle in a linked list", "Prefix sums for range queries", "When recursion needs memoization",
            "Stack for matching brackets", "Union-find in plain English", "Topological sort and build order",
            "Trie for autocomplete", "Quickselect for the k-th element", "Monotonic stack, step by step",
            "Why sorting is O(n log n) at best", "Kadane's algorithm, step by step", "Dijkstra needs non-negative weights", "Backtracking: choose, explore, undo", "Two heaps for a running median"],
    "Interview": ["Clarify the question before you code", "Estimating capacity on a whiteboard",
                  "Talking through trade-offs out loud", "Answering 'tell me about a bug you shipped'",
                  "How to recover from a blank mind", "Testing your own solution before they ask", "Naming things in a live round",
                  "Asking for hints without losing points", "Behavioural answers with a clear result",
                  "Reading the room in a system design round", "What to do when you find the bug late",
                  "Questions worth asking your interviewer", "Pacing a 45-minute coding round", "How to give a tight project summary", "Explaining a trade-off to a non-engineer"],
    "OS": ["What a context switch costs", "Processes versus threads", "Virtual memory and page faults",
           "Deadlock: the four conditions", "What the kernel does on a system call", "Mutex versus semaphore",
           "Why the page cache makes reads fast", "Zombie processes explained", "How a scheduler picks the next task", "What a file descriptor is", "Copy-on-write, explained", "Why fork is cheap"],
    "Dev": ["Git rebase versus merge", "Why you should pin dependencies", "Reading a stack trace bottom-up",
            "Small pull requests get reviewed faster", "Feature flags without the mess", "Logging that helps at 3 a.m.", "Code review: comment on the code, not the coder", "Semantic versioning in practice"],
}

# (day offset from today, slot index) -> what happens to that topic. Fixed, so the demo tells the same story each time.
EXPIRED = {(-21, 1), (-9, 0)}                  # carousel never decided -> expired
RETRIED = {(-15, 0), (-5, 1)}                  # YouTube failed once, recovered on the retry
REGENERATED = {(-33, 1), (-27, 0), (-19, 1), (-12, 0), (-7, 1), (-3, 0), (-1, 0)}
REJECTED_REEL = {(-30, 0), (-22, 0), (-16, 1), (-11, 1), (-8, 0), (-4, 1)}
REJECTED_BOTH = {(-26, 1), (-14, 0), (-2, 1)}
LATE_PUBLISH = {(-24, 1), (-13, 0), (-6, 1)}   # the poller ran late: published 40-60 minutes after it was due
QUOTA_FAIL = (-2, 0)                           # the 10:00 run hit the Gemini quota; a manual run recovered it
FAILED_FINAL = (-10, 1)                        # YouTube refused the reel 3x (upload limit); still waiting for a manual retry


def _slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:48]


def build_demo(now: datetime) -> tuple[list[PostRow], list[JobRow], list[EventRow], Config]:
    now = aware(now)
    rng = random.Random(SEED)
    today = now.astimezone(IST).date()
    posts: list[PostRow] = []
    jobs: list[JobRow] = []
    events: list[EventRow] = []
    seq = {"post": 0, "event": 0, "job": 0}
    pools = {c: rng.sample(v, len(v)) for c, v in TOPICS.items()}
    used: dict[str, int] = {}
    last_cat = None

    def ev(at: datetime, event: str, message: str, *, source: str = "system", level: str = "info", post_id: str | None = None):
        seq["event"] += 1
        events.append(EventRow(id=seq["event"], created_at=at, event=event, source=source, level=level,
                               message=message, post_id=post_id))

    def pick_topic() -> tuple[str, str]:
        nonlocal last_cat
        cats = [c for c in WEIGHTS if c != last_cat]
        cat = rng.choices(cats, weights=[WEIGHTS[c] for c in cats])[0]
        last_cat = cat
        i = used.get(cat, 0)
        used[cat] = i + 1
        pool = pools[cat]
        title = pool[i % len(pool)] + (" (revisited)" if i >= len(pool) else "")
        return cat, title

    def platform(at: datetime, plat: str, attempts: int = 1) -> dict:
        r = {"status": "published", "id": f"demo-{plat}-{rng.randrange(10**6):06d}", "at": iso(at), "attempts": attempts}
        if plat == "yt":
            r["privacy"] = "public"
        return r

    def make(kind: str, group: str, topic: str, cat: str, slot: datetime, created: datetime, version: int = 1) -> PostRow:
        seq["post"] += 1
        return PostRow(id=f"demo-{seq['post']:04d}", kind=kind, status="pending", group_id=group, topic=topic,
                       category=cat, version=version, publish_at=slot, created_at=created, updated_at=created, attempts=0)

    def decide(p: PostRow, created: datetime, slot: datetime, delay_min: float, *, late: bool = False) -> None:
        """Approve and (when due) publish one post, or leave it approved if its slot hasn't arrived."""
        p.decided_at = created + timedelta(minutes=delay_min)
        p.status = "approved"
        p.updated_at = p.decided_at
        src = "telegram" if rng.random() < 0.6 else "dashboard"
        rng.randint(1, 12)   # (kept so the seeded sequence, and with it the sample story, stays the same)
        # the poll stamps decided_at and the event together, so an approval never appears after its publish
        ev(p.decided_at, "post.approved",
           f"Approved {p.kind} “{p.topic}”", source=src, post_id=p.id)
        ready = max(slot, p.decided_at)
        done = ready + timedelta(minutes=rng.randint(40, 60) if late else rng.randint(3, 18))
        if done > now:
            return
        p.status, p.attempts, p.published_at, p.updated_at = "published", 1, done, done
        targets = ["ig", "yt"] if p.kind == "reel" else ["ig"]
        p.platforms = {t: platform(done + timedelta(minutes=i), t) for i, t in enumerate(targets)}
        for t in targets:
            ev(done + timedelta(minutes=targets.index(t)), "post.published",
               f"Published {p.kind} “{p.topic}” to {'Instagram' if t == 'ig' else 'YouTube'}", source="publisher", post_id=p.id)

    next_pending_done = False
    for off in range(-HISTORY_DAYS, 2):
        day = today + timedelta(days=off)
        for si, hhmm in enumerate(SLOTS):
            h, m = (int(x) for x in hhmm.split(":"))
            slot = datetime(day.year, day.month, day.day, h, m, tzinfo=IST)
            if slot - timedelta(minutes=90) > now and next_pending_done:
                continue
            key = (off, si)
            cat, title = pick_topic()
            group = f"demo/{day.isoformat()}/{_slug(title)}"
            created = slot - timedelta(minutes=90 + rng.randint(0, 25))
            upcoming = slot > now
            if upcoming:
                created = min(created, now - timedelta(minutes=rng.randint(35, 55)))
                next_pending_done = True
            elif key == QUOTA_FAIL:
                # the scheduled run failed on quota; someone re-ran it from the dashboard a few hours later
                seq["job"] += 1
                jobs.append(JobRow(id=f"demo-job-{seq['job']:03d}", status="failed", created_at=created - timedelta(minutes=3),
                                   trigger="scheduled", failure_reason="quota"))
                ev(created - timedelta(minutes=2), "generate.failed", "Generation failed: Gemini free quota used up",
                   level="error", source="generate")
                created = created + timedelta(hours=4, minutes=20)
            reel = make("reel", group, title, cat, slot, created)
            car = make("carousel", group, title, cat, slot, created)
            for p in (car, reel):
                ev(created + timedelta(minutes=1 if p.kind == "reel" else 0), "post.generated",
                   f"Generated {p.kind} “{title}”", source="pipeline", post_id=p.id)
            seq["job"] += 1
            jobs.append(JobRow(id=f"demo-job-{seq['job']:03d}", status="succeeded", created_at=created - timedelta(minutes=4),
                               trigger="dashboard" if key == QUOTA_FAIL else "scheduled"))
            ev(created + timedelta(minutes=2), "generate.finished", f"Generated “{title}” ({cat})", source="generate")
            posts += [car, reel]
            if upcoming:
                continue  # waits for the owner: this is what "needs you" shows
            delay = rng.choice([6, 9, 14, 18, 25, 38, 55, 80, 130, 210, 340, 520])
            delay = min(delay, max(2.0, (now - created).total_seconds() / 60 - 8))  # never decided in the future
            if key in EXPIRED:
                decide(reel, created, slot, delay)
                car.status, car.updated_at = "expired", created + timedelta(hours=36)
                ev(created + timedelta(hours=36), "post.expired", f"No decision in 36h; carousel “{title}” expired",
                   source="pipeline", post_id=car.id)
                continue
            if key in REJECTED_BOTH:
                for p in (car, reel):
                    p.status, p.decided_at, p.updated_at = "rejected", created + timedelta(minutes=delay), created + timedelta(minutes=delay)
                    ev(p.decided_at, "post.rejected", f"Rejected {p.kind} “{title}”", source="dashboard", post_id=p.id)
                continue
            decide(car, created, slot, delay + rng.choice([0, 2, 5]), late=key in LATE_PUBLISH)
            if key in REJECTED_REEL:
                reel.status, reel.decided_at = "rejected", created + timedelta(minutes=delay + 3)
                reel.updated_at = reel.decided_at
                ev(reel.decided_at, "post.rejected", f"Rejected reel “{title}”", source="telegram", post_id=reel.id)
            elif key in REGENERATED:
                reel.status, reel.decided_at = "replaced", created + timedelta(minutes=delay + 4)
                reel.updated_at = reel.decided_at
                v2 = make("reel", group, title, cat, slot, reel.decided_at + timedelta(minutes=6), version=2)
                ev(v2.created_at, "post.regenerated", f"Regenerated reel “{title}” (v2)", source="pipeline", post_id=v2.id)
                posts.append(v2)
                decide(v2, v2.created_at, slot, rng.choice([5, 9, 16]))
            else:
                decide(reel, created, slot, delay + rng.choice([1, 3, 6]), late=key in LATE_PUBLISH)
                if key in RETRIED and reel.status == "published":
                    reel.attempts = 2
                    reel.platforms["yt"]["attempts"] = 2
                    t = aware(datetime.fromisoformat(reel.platforms["yt"]["at"].replace("Z", "+00:00")))
                    ev(t - timedelta(minutes=20), "publish.failed",
                       f"YouTube publish failed for reel “{title}” (attempt 1/3)", level="error", source="publisher", post_id=reel.id)
                elif key == FAILED_FINAL and reel.status == "published":
                    # Instagram went live; YouTube gave up after three tries. Not hidden: it shows in "needs you".
                    reel.status, reel.attempts = "failed", 3
                    t = aware(datetime.fromisoformat(reel.platforms["yt"]["at"].replace("Z", "+00:00")))
                    reel.platforms["yt"] = {"status": "failed", "attempts": 3, "at": iso(t + timedelta(minutes=40)),
                                            "error": "YouTube daily upload limit hit (quotaExceeded)"}
                    reel.error = "YouTube: daily upload limit hit"
                    reel.updated_at = t + timedelta(minutes=40)
                    for i in range(3):
                        ev(t + timedelta(minutes=20 * i), "publish.failed",
                           f"YouTube publish failed for reel “{title}” (attempt {i + 1}/3): upload limit hit",
                           level="error", source="publisher", post_id=reel.id)

    # Ids in time order, as the real activity_log's autoincrement ids are (the feed sorts by id).
    events.sort(key=lambda e: aware(e.created_at))
    for i, e in enumerate(events, 1):
        e.id = i
    cfg = Config(slots=list(SLOTS), weights={k: float(v) for k, v in WEIGHTS.items()}, handle=HANDLE, demo_enabled=True)
    return posts, jobs, events, cfg
