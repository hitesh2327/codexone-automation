"""Dashboard: metric definitions (pure aggregator), the demo workspace, and the /api/dashboard/overview endpoint."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, event

from api.app.routes import dashboard as route
from src import dashboard_demo, db
from src.dashboard_metrics import (IST, Config, EventRow, JobRow, PostRow, build_overview, percentile, safe_url, scrub)
from src.db.models import ActivityLog, Post

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=IST)       # Mon 12:00 IST
CFG = Config(slots=["10:00", "19:00"], weights={"AI": 30, "DSA": 20, "OS": 10, "Dev": 40})
_n = 0


def at(h: float, day: int = 5) -> datetime:
    return datetime(2026, 10, 5, 0, 0, tzinfo=IST) + timedelta(days=day - 5, hours=h)


def post(status="published", kind="reel", **kw) -> PostRow:
    global _n
    _n += 1
    base = dict(id=f"p{_n}", kind=kind, status=status, group_id=f"2026-10-0{_n % 9 + 1}/t{_n}", topic=f"Topic {_n}",
                category="AI", created_at=at(-30), updated_at=at(-5), version=1)
    base.update(kw)
    return PostRow(**base)


def ov(posts, jobs=None, events=None, now=NOW, cfg=CFG, days=30, **kw):
    return build_overview(posts, jobs, events, now=now, cfg=cfg, days=days, **kw)


def plat(status="published", attempts=1, **kw):
    return {"status": status, "attempts": attempts, **kw}


# ---------------------------------------------------------------- KPI definitions
def test_approval_rate_ac2():
    rows = ([post("published") for _ in range(5)] + [post("failed"), post("approved"), post("rejected"),
            post("replaced"), post("expired")])
    a = ov(rows)["kpis"]["approval"]
    assert (a["num"], a["den"], a["pct"]) == (7, 9, 78)
    assert a["expired"] == 1
    assert a["judged"] is False                     # 9 decided < 10: shown, not judged


def test_approval_pending_excluded_and_first_pass():
    rows = [post("published") for _ in range(8)] + [post("published", version=2), post("replaced"), post("pending")]
    a = ov(rows)["kpis"]["approval"]
    assert (a["num"], a["den"], a["judged"]) == (9, 10, True)
    assert (a["first_pass"]["num"], a["first_pass"]["den"]) == (8, 9)   # v2 left out, the replaced v1 counted as declined
    assert a["pending"] == 1


def test_publish_success_ac3():
    rows = [
        post(targets=["ig", "yt"], platforms={"ig": plat(at=at(5).isoformat()), "yt": plat(attempts=3, at=at(5).isoformat())},
             published_at=at(5)),
        post(kind="carousel", platforms={"ig": plat(at=at(6).isoformat())}, published_at=at(6)),
        post(platforms={"ig": plat(at=at(7).isoformat()), "yt": plat("skipped", error="YouTube not configured", at=at(7).isoformat())},
             published_at=at(7)),
    ]
    s = ov(rows)["kpis"]["publish_success"]
    assert (s["num"], s["den"]) == (4, 4)
    assert (s["first_attempt"]["num"], s["first_attempt"]["den"]) == (3, 4)   # the YouTube upload needed 3 attempts
    assert s["skipped_count"] == 1 and s["skipped"][0]["platform"] == "yt"


def test_publish_success_ac3_literal_fixture():
    """AC-3 as written: reel IG ok + YT ok on attempt 3; carousel IG ok on attempt 1; another reel's YT skipped."""
    rows = [
        post(targets=["ig", "yt"], published_at=at(5),
             platforms={"ig": plat(at=at(5).isoformat()), "yt": plat(attempts=3, at=at(5).isoformat())}),
        post(kind="carousel", targets=["ig"], published_at=at(6), platforms={"ig": plat(at=at(6).isoformat())}),
        post(targets=["yt"], published_at=at(7),
             platforms={"yt": plat("skipped", error="YouTube not configured", at=at(7).isoformat())}),
    ]
    s = ov(rows)["kpis"]["publish_success"]
    assert (s["num"], s["den"], s["pct"]) == (3, 3, 100)            # skipped is not in the denominator
    assert (s["first_attempt"]["num"], s["first_attempt"]["den"]) == (2, 3)
    assert s["skipped_count"] == 1 and "not configured" in s["skipped"][0]["reason"]
    assert s["judged"] is False


def test_attention_merges_reel_and_carousel_of_one_topic():
    g = "2026-10-05/same"
    car = post("pending", kind="carousel", group_id=g, topic="Tries", created_at=NOW - timedelta(hours=1), publish_at=at(19))
    reel = post("pending", kind="reel", group_id=g, topic="Tries", created_at=NOW - timedelta(hours=2), publish_at=at(19))
    other = post("pending", kind="reel", group_id="2026-10-05/other", topic="Heaps", created_at=NOW - timedelta(hours=1), publish_at=at(19))
    a = ov([car, reel, other])["attention"]
    assert a["total"] == 2
    merged = next(i for i in a["items"] if "Tries" in i["title"])
    assert merged["title"] == "Waiting for your decision: Reel and carousel “Tries”"
    assert merged["kinds"] == ["reel", "carousel"] and merged["age_min"] == 120
    assert "\x00" not in json.dumps(a) and "_group" not in json.dumps(a)
    # different failing platforms are different needs: not merged
    f1 = post("failed", kind="reel", group_id="g/f", targets=["yt"], platforms={"yt": plat("failed", attempts=3, error="x")})
    f2 = post("failed", kind="carousel", group_id="g/f", targets=["ig"], platforms={"ig": plat("failed", attempts=3, error="x")})
    assert sum(i["code"] == "failed_final" for i in ov([f1, f2])["attention"]["items"]) == 2


def test_turnaround_bins_and_channels_hand_computed():
    delays = [10, 45, 200, 500, 2000]                     # one per bin
    rows = [post(id=f"t{m}", created_at=at(-20), decided_at=at(-20) + timedelta(minutes=m)) for m in delays]
    ev = [EventRow(1, at(-20) + timedelta(minutes=10), "post.approved", "telegram", post_id="t10"),
          EventRow(2, at(-20) + timedelta(minutes=45), "post.approved", "dashboard", post_id="t45"),
          EventRow(3, at(-20) + timedelta(minutes=200), "post.approved", "dashboard", post_id="t200")]
    t = ov(rows, events=ev)["turnaround"]
    assert [b["n"] for b in t["bins"]] == [1, 1, 1, 1, 1]
    assert t["median_min"] == 200 and t["p90_min"] == 2000      # nearest rank: ceil(0.9*5) = 5th
    ch = {c["channel"]: c for c in t["channels"]}
    assert ch["telegram"]["n"] == 1 and ch["dashboard"]["n"] == 2 and ch["dashboard"]["median_min"] == 122.5


def test_status_line_first_match_rule():
    low = post("pending", created_at=NOW - timedelta(hours=1), publish_at=at(19))
    med = post("failed", platforms={"ig": plat("failed", attempts=1, error="x")}, targets=["ig"])
    high = post("approved", publish_at=at(10), decided_at=at(8))
    assert ov([low])["status"]["state"] == "ok"            # only low items: green, but still counted
    assert ov([low])["status"]["needs_count"] == 1
    assert ov([low, med])["status"]["state"] == "heads_up"
    assert ov([low, med, high])["status"]["state"] == "action"


def test_time_to_approve_ac4():
    rows = [post(created_at=at(8), decided_at=at(8) + timedelta(minutes=m)) for m in (10, 20, 240)]
    t = ov(rows)["kpis"]["time_to_approve"]
    assert t["median_min"] == 20 and t["p90_min"] == 240 and t["upper_bound"] is True and t["judged"] is False


def test_punctuality_ac5():
    late_approval = post(publish_at=at(19, 4), decided_at=at(20 + 1 / 6, 4), published_at=at(20.4, 4))       # 19:00 slot, ok 20:10, live 20:24
    slow = post(publish_at=at(19, 4), decided_at=at(18, 4), published_at=at(19 + 50 / 60, 4))               # 50 min after the slot
    p = ov([late_approval, slow])["kpis"]["punctuality"]
    assert (p["num"], p["den"]) == (1, 2)


def test_small_n_is_flagged_not_hidden():
    k = ov([post() for _ in range(3)])["kpis"]
    assert k["approval"]["pct"] == 100 and k["approval"]["judged"] is False
    assert ov([post() for _ in range(10)])["kpis"]["approval"]["judged"] is True


def test_percentile_helpers():
    assert percentile([], 0.5) is None
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile(list(range(1, 11)), 0.9) == 9


# ---------------------------------------------------------------- funnel
def test_funnel_buckets_sum_to_generated_ac9():
    statuses = ["published"] * 4 + ["approved", "publishing", "pending", "rejected", "regenerate", "replaced", "expired"]
    rows = [post(s) for s in statuses]
    rows.append(post("failed", platforms={"yt": plat("failed", attempts=3, error="boom")}, targets=["yt"]))   # giving up
    rows.append(post("failed", platforms={"yt": plat("failed", attempts=1, error="boom")}, targets=["yt"]))   # will retry
    f = ov(rows)["funnel"]
    assert sum(f["buckets"].values()) == f["total"] == len(rows)
    assert f["buckets"]["failed"] == 1 and f["buckets"]["retrying"] == 1 and f["buckets"]["regenerated"] == 2
    st = {s["key"]: s["n"] for s in f["stages"]}
    assert st["generated"] == len(rows) and st["published"] == 4
    assert st["approved"] == 4 + 2 + 2                     # published + waiting + both failed


# ---------------------------------------------------------------- attention queue
def test_attention_queue_ac6():
    overdue = post("approved", publish_at=at(10), decided_at=at(8), created_at=at(7))                       # 2h past its slot
    giving_up = post("failed", platforms={"yt": plat("failed", attempts=3, error="quota exceeded")}, targets=["yt"], updated_at=at(11))
    expiring = post("pending", created_at=NOW - timedelta(hours=32), publish_at=at(19))
    items = ov([overdue, giving_up, expiring])["attention"]["items"]
    assert [i["severity"] for i in items] == ["high", "high", "high"]
    assert {i["post_id"] for i in items} == {overdue.id, giving_up.id, expiring.id}
    assert all(i["action"]["to"].startswith("/posts?post=") for i in items)
    assert ov([overdue, giving_up, expiring])["status"]["state"] == "action"


def test_attention_all_clear_and_error_state():
    slots = [post(published_at=at(h, d) + timedelta(minutes=5), publish_at=at(h, d), created_at=at(h - 2, d), group_id=f"g{d}{h}")
             for d, h in ((4, 10), (4, 19), (5, 10))]
    quiet = ov(slots)
    assert quiet["attention"]["items"] == [] and quiet["status"]["state"] == "ok" and quiet["status"]["needs_count"] == 0
    broken = ov(None)
    assert broken["attention"]["ok"] is False and broken["status"]["state"] == "unknown"   # never "all clear" on failure


def test_overdue_respects_late_approval():
    p = post("approved", publish_at=at(10), decided_at=at(11.8))      # approved 12 minutes ago, slot long gone
    assert ov([p])["attention"]["items"] == []


def test_pending_severities_and_expired_and_failed_retrying():
    low = post("pending", created_at=NOW - timedelta(hours=1), publish_at=at(19))
    med = post("pending", created_at=NOW - timedelta(hours=20), publish_at=at(10))
    exp = post("expired", updated_at=NOW - timedelta(days=2))
    old_exp = post("expired", updated_at=NOW - timedelta(days=12))
    retry = post("failed", platforms={"ig": plat("failed", attempts=1, error="x")}, targets=["ig"])
    sev = {i["post_id"]: i["severity"] for i in ov([low, med, exp, old_exp, retry])["attention"]["items"]}
    assert sev == {low.id: "low", med.id: "medium", exp.id: "low", retry.id: "medium"}


def test_auth_failures_and_missing_slot_and_failed_generation():
    yt = post("failed", platforms={"yt": plat("failed", attempts=3, error="YouTube refresh token rejected")}, targets=["yt"])
    old = post(created_at=at(-40), publish_at=at(-40))
    out = ov([yt, old], jobs=[JobRow("j1", "failed", NOW - timedelta(hours=2), failure_reason="quota")])
    codes = {i["code"] for i in out["attention"]["items"]}
    assert {"yt_auth", "slot_empty", "generation_failed", "failed_final"} <= codes
    gen = next(i for i in out["attention"]["items"] if i["code"] == "generation_failed")
    assert "Gemini quota" in gen["title"] and gen["severity"] == "medium"


# ---------------------------------------------------------------- heatmap / mix / pipeline
def test_cadence_states_and_text_figures_ac7():
    rows = []
    for d in range(-29, 0):                  # 29 completed days
        n = 4 if d not in (-5, -9, -12) else (2 if d != -12 else 0)
        for i in range(n):
            rows.append(post(published_at=at(10 + i, 5 + d), created_at=at(5, 5 + d), group_id=f"g{d}{i // 2}"))
    c = ov(rows)["cadence"]
    states = [x["state"] for x in c["days"]]
    assert states.count("full") == 26 and states.count("partial") == 2 and states.count("missed") == 1
    assert states[-1] == "today" and c["full_days"] == 26 and c["counted_days"] == 29 and c["streak"] == 4
    assert c["days"][-2]["n"] == 4 and c["days"][-2]["topics"] == 2


def test_mix_ac8():
    rows = [post(category="DSA", group_id=f"g{i}") for i in range(6)] + \
           [post(category="AI", group_id=f"a{i}") for i in range(18)]
    m = ov(rows)["mix"]
    dsa = next(c for c in m["categories"] if c["category"] == "DSA")
    assert m["n"] == 24 and m["judged"] and dsa["share"] == 25.0 and dsa["target"] == 20.0 and dsa["delta"] == 5.0
    small = ov(rows[:3] + rows[6:15])["mix"]
    assert small["judged"] is False and all(c["tone"] == "idle" for c in small["categories"])


def test_mix_counts_topics_not_posts_and_ignores_replaced_versions():
    g = "2026-10-01/x"
    rows = [post(kind="carousel", group_id=g, category="AI"), post(kind="reel", group_id=g, category="AI", status="replaced"),
            post(kind="reel", group_id=g, category="AI", version=2)]
    assert ov(rows)["mix"]["n"] == 1


def test_pipeline_from_posts_alone_and_jobs():
    rows = [post(publish_at=at(10, 5), created_at=at(8, 5)), post(publish_at=at(19, 4), created_at=at(17, 4))]
    pl = ov(rows, jobs=None)["pipeline"]
    assert pl["generation"]["ok"] is False and pl["slot_fill"]["den"] >= 1      # jobs unavailable, posts-based part still works
    jobs = [JobRow("a", "succeeded", NOW - timedelta(days=3)), JobRow("b", "failed", NOW - timedelta(days=2), failure_reason="quota"),
            JobRow("c", "succeeded", NOW - timedelta(days=1)), JobRow("d", "succeeded", NOW - timedelta(hours=3)),
            JobRow("e", "skipped", NOW - timedelta(hours=2))]
    g = ov(rows, jobs=jobs)["pipeline"]["generation"]
    assert (g["success"]["num"], g["success"]["den"], g["streak"], g["skipped"]) == (3, 4, 2, 1)
    assert g["last_failure"] == "Gemini quota"
    assert ov(rows, jobs=[])["pipeline"]["generation"]["tracking_since"] is None


def test_next_slots_shapes():
    p = post("pending", kind="reel", publish_at=at(19), created_at=at(10))
    s = ov([p])["next_slots"]["items"]
    assert [x["label"] for x in s][:2] == ["19:00", "10:00"] and s[0]["generated"] and s[0]["reel"]["id"] == p.id
    assert s[1]["generated"] is False
    assert s[1]["generation_starts"] == "2026-10-06T02:30:00Z"            # 08:00 IST, the 10:00 slot's cron
    odd = ov([], cfg=Config(slots=["12:00"], weights={}))["next_slots"]["items"][0]
    assert odd["generation_starts"] is None                               # unknown schedule: no guessed time


def test_platform_links_only_https_instagram_youtube():
    assert safe_url("https://www.instagram.com/reel/abc/") and safe_url("https://youtube.com/shorts/x")
    assert safe_url("http://instagram.com/x") is None and safe_url("https://evil.example/instagram.com") is None
    assert safe_url("javascript:alert(1)") is None and safe_url("https://instagram.com.evil.io/x") is None
    rows = [post(targets=["ig", "yt"], published_at=at(9), platforms={
        "ig": plat(url="https://www.instagram.com/reel/abc/", at=at(9).isoformat()),
        "yt": plat(url="https://evil.example/x", privacy="private", at=at(9).isoformat())})]
    items = {i["platform"]: i for i in ov(rows)["platforms"]["items"]}
    assert items["ig"]["recent"][0]["url"].startswith("https://www.instagram.com")
    assert items["yt"]["recent"][0]["url"] is None and items["yt"]["recent"][0]["privacy"] == "private"


def test_feed_is_curated_masked_and_scrubbed():
    ev = [EventRow(1, at(9), "login.success", "auth", message="Signed in", ),
          EventRow(2, at(10), "post.approved", "dashboard", message="Approved reel “X” by me@example.com token=abc123", post_id="p1"),
          EventRow(3, at(11), "post.published", "publisher", message="y" * 400),
          EventRow(4, at(11.5), "post.approved", "telegram", message="ok")]
    items = ov([post()], events=ev)["activity"]["items"]
    assert [i["event"] for i in items] == ["post.approved", "post.published", "post.approved"]
    assert [i["actor"] for i in items] == ["Telegram", "System", "You"]
    assert "me@example.com" not in json.dumps(items) and "abc123" not in json.dumps(items)
    assert len(items[1]["message"]) <= 140
    assert ov([post()], events=None)["activity"]["ok"] is False


def test_section_failure_is_isolated(monkeypatch):
    from src import dashboard_metrics as m
    monkeypatch.setattr(m, "funnel", lambda c: 1 / 0)
    out = ov([post()])
    assert out["funnel"] == {"ok": False, "error": "unavailable"} and out["kpis"]["ok"] and out["attention"]["ok"]


def test_scrub_limits():
    assert scrub("a   b\n c") == "a b c" and len(scrub("x" * 500, 50)) == 50


# ---------------------------------------------------------------- demo workspace
def test_demo_goes_through_the_same_aggregator_and_is_realistic():
    posts, jobs, events, cfg = dashboard_demo.build_demo(NOW)
    assert cfg.handle == "@demo_dev_daily" and all(p.id.startswith("demo-") for p in posts)
    out = build_overview(posts, jobs, events, now=NOW, cfg=cfg, days=30, workspace="demo")
    assert out["demo"] and out["workspace"] == "demo"
    k = out["kpis"]
    assert 70 <= k["approval"]["pct"] < 100 and k["approval"]["expired"] >= 1      # not a flawless 100%
    b = out["funnel"]["buckets"]
    assert b["rejected"] and b["regenerated"] and sum(b.values()) == out["funnel"]["total"]
    assert any(j.failure_reason == "quota" for j in jobs)
    ps = k["publish_success"]
    assert ps["den"] - ps["num"] >= 1 and ps["first_attempt"]["num"] < ps["num"]   # one gave up, two needed a retry
    assert any(i["code"] == "failed_final" for i in out["attention"]["items"])
    assert sum(p.status == "expired" for p in posts) == 2
    assert all(e.event in {"post.generated", "post.regenerated", "post.approved", "post.rejected", "post.published",
                           "publish.failed", "post.expired", "generate.finished", "generate.failed"} for e in events)
    assert out["attention"]["total"] >= 1 and out["next_slots"]["items"]
    assert [d["state"] for d in out["cadence"]["days"]].count("partial") >= 1
    blob = json.dumps(out).lower()
    for banned in ("follower", "reach", "likes", "impression", "hours saved", "http://", "https://"):
        assert banned not in blob, banned
    assert all(i["url"] is None for p in out["platforms"]["items"] for i in p["recent"])
    # a coherent story: nothing in the future, no approval logged after its own publish, feed ids in time order
    assert all(e.created_at <= NOW for e in events)
    first_pub = {}
    for e in events:
        if e.event == "post.published":
            first_pub.setdefault(e.post_id, e.created_at)
    assert all(e.created_at <= first_pub[e.post_id] for e in events if e.event == "post.approved" and e.post_id in first_pub)
    assert [e.id for e in sorted(events, key=lambda e: e.created_at)] == sorted(e.id for e in events)
    # deterministic: same instant, same numbers
    again = build_overview(*dashboard_demo.build_demo(NOW)[:3], now=NOW, cfg=cfg, days=30, workspace="demo")
    assert again["kpis"] == out["kpis"]


def test_demo_builder_and_aggregation_never_touch_the_database(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("demo must not open a database session")
    monkeypatch.setattr(db, "session", boom)
    out = route.compute("demo", 30)
    assert out["demo"] and out["kpis"]["ok"]


# ---------------------------------------------------------------- API
@pytest.fixture(autouse=True)
def clean():
    route._cache.clear()
    route._limiter._hits.clear()
    with db.session() as s:
        s.execute(delete(Post))
        s.execute(delete(ActivityLog))
    yield
    route._cache.clear()


def _live_row(id_, **kw):
    now = datetime.now(timezone.utc)
    base = dict(id=id_, kind="reel", date=now.date(), topic="Private topic", category="AI", post_dir="x",
                caption="SECRET CAPTION #ai", media={"carousel": ["https://res.cloudinary.com/x/1.jpg"]}, status="published",
                version=1, group_id=f"{now.date()}/{id_}", created_at=now - timedelta(hours=5), publish_at=now - timedelta(hours=3),
                decided_at=now - timedelta(hours=4), published_at=now - timedelta(hours=3), attempts=1,
                feedback="private feedback", source_url="https://secret.example/src", tg_message_ids=[1], tg_control_id=99,
                platforms={"ig": {"status": "published", "url": "https://www.instagram.com/p/abc/", "id": "9", "attempts": 1,
                                  "at": (now - timedelta(hours=3)).isoformat()}})
    base.update(kw)
    return Post(**base)


def test_requires_login(client):
    assert client.get("/api/dashboard/overview").status_code == 401


def test_overview_privacy_and_shape(authed):
    with db.session() as s:
        s.add(_live_row("a1", kind="carousel"))
        s.add(_live_row("a2", status="failed", error="Bearer abcdef boom", platforms={"yt": {"status": "failed", "attempts": 3, "error": "token=SECRETVALUE failed"}}))
        s.add(ActivityLog(event="post.published", source="publisher", message="Published", actor="owner@example.com", post_id="a1"))
        s.add(ActivityLog(event="login.success", source="auth", message="x", actor="owner@example.com"))
    r = authed.get("/api/dashboard/overview")
    assert r.status_code == 200, r.text
    body = r.text
    for secret in ("SECRET CAPTION", "private feedback", "secret.example", "owner@example.com", "SECRETVALUE", "abcdef", "tg_control", "post_dir"):
        assert secret not in body, secret
    d = r.json()
    assert d["workspace"] == "live" and d["demo"] is False and d["kpis"]["posts_published"]["count"] == 1
    assert {i["event"] for i in d["activity"]["items"]} == {"post.published"} and d["activity"]["items"][0]["actor"] == "System"
    assert d["recent_posts"]["items"][0]["thumb"] == "https://res.cloudinary.com/x/1.jpg"
    assert d["pipeline"]["generation"]["ok"] in (True, False)
    assert r.headers["cache-control"].startswith("private")


def test_etag_and_cache(authed):
    r1 = authed.get("/api/dashboard/overview")
    etag = r1.headers["etag"]
    r2 = authed.get("/api/dashboard/overview", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    with db.session() as s:
        s.add(_live_row("b1"))
    assert authed.get("/api/dashboard/overview").json()["kpis"]["posts_published"]["count"] == 0   # served from the 15 s cache
    route._cache.clear()
    assert authed.get("/api/dashboard/overview").json()["kpis"]["posts_published"]["count"] == 1


def test_validation_and_partial_failure(authed, monkeypatch):
    assert authed.get("/api/dashboard/overview?range=7").status_code == 422
    assert authed.get("/api/dashboard/overview?workspace=bogus").status_code == 422
    r90 = authed.get("/api/dashboard/overview?range=90")
    assert r90.status_code == 200, r90.text
    assert r90.json()["window_days"] == 90
    monkeypatch.setattr(route, "_load_events", lambda *a, **k: None)
    monkeypatch.setattr(route, "_load_jobs", lambda *a, **k: None)
    route._cache.clear()
    d = authed.get("/api/dashboard/overview").json()
    assert d["activity"]["ok"] is False and d["pipeline"]["generation"]["ok"] is False
    assert d["kpis"]["ok"] and d["attention"]["ok"] and "Traceback" not in json.dumps(d)
    monkeypatch.setattr(route, "_load_posts", lambda *a, **k: None)
    route._cache.clear()
    d = authed.get("/api/dashboard/overview").json()
    assert d["attention"]["ok"] is False and d["status"]["state"] == "unknown"       # not "all clear"


def test_demo_endpoint_zero_writes_and_no_live_tables(authed, monkeypatch):
    with db.session() as s:
        s.add(_live_row("real1"))
    with db.session() as s:
        activity_before = s.query(ActivityLog).count()
    statements: list[str] = []

    def spy(conn, cursor, statement, *a):
        statements.append(statement.lower())
    event.listen(db.engine(), "before_cursor_execute", spy)
    try:
        r = authed.get("/api/dashboard/overview?workspace=demo")
    finally:
        event.remove(db.engine(), "before_cursor_execute", spy)
    assert r.status_code == 200 and r.json()["demo"] is True
    assert "real1" not in r.text and "Private topic" not in r.text
    touched = [s for s in statements if any(t in s for t in ("posts", "activity_log", "generation_jobs", "posted_topics"))]
    writes = [s for s in statements if s.lstrip().startswith(("insert", "update", "delete"))]
    assert not touched and not writes
    with db.session() as s:
        assert s.query(Post).count() == 1 and s.query(ActivityLog).count() == activity_before


def test_demo_switched_off(authed, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DEMO_ENABLED", "false")
    assert authed.get("/api/dashboard/overview?workspace=demo").status_code == 404
    assert authed.get("/api/dashboard/overview").json()["config"]["demo_enabled"] is False
    monkeypatch.setenv("DASHBOARD_DEMO_ENABLED", "true")
    route._cache.clear()
    assert authed.get("/api/dashboard/overview").json()["config"]["demo_enabled"] is True


def test_rate_limited(authed):
    for _ in range(route.LIMIT_PER_MIN):
        assert authed.get("/api/dashboard/overview").status_code == 200
    r = authed.get("/api/dashboard/overview")
    assert r.status_code == 429 and r.headers["retry-after"]


def test_open_items_older_than_the_lookback_are_not_read():
    """QA-M-09: every failed/pending post of all time used to be read and aggregated on each refresh."""
    from sqlalchemy import update
    from src import queue_store as qs
    now = datetime.now(timezone.utc)
    mk = lambda i: qs.Item(id=i, kind="reel", date="2026-01-01", topic="T", category="AI",  # noqa: E731
                           post_dir=f"output/2026-01-01/{i}/", caption="c", status="failed")
    qs.save([mk("m09-old"), mk("m09-new")])
    with db.session() as s:
        old = now - timedelta(days=route.OPEN_LOOKBACK_DAYS + 10)
        s.execute(update(Post).where(Post.id == "m09-old").values(created_at=old, updated_at=old))
        s.execute(update(Post).where(Post.id == "m09-new").values(created_at=old, updated_at=now - timedelta(days=2)))
    try:
        ids = {p.id for p in route._load_posts(now, 30)}
        assert "m09-new" in ids and "m09-old" not in ids
    finally:
        with db.session() as s:
            s.execute(delete(Post).where(Post.id.in_(["m09-old", "m09-new"])))
