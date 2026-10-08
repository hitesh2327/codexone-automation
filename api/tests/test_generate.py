"""Generate API: guardrails, dispatch (GitHub faked), slot board, reconcile, and that nothing publishes."""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from api.app.routes import generate as route
from src import activity, approve_bot, db, generation, github_actions
from src import queue_store as q
from src.db.models import ActivityLog, GenerationJob, Post

IST = approve_bot.IST
UTC = timezone.utc


class FakeGitHub:
    """Stands in for `requests` inside src.github_actions. Nothing here touches the network."""

    def __init__(self):
        self.posts: list[dict] = []
        self.gets: list[str] = []
        self.post_status = 204
        self.runs: list[dict] = []          # workflow runs the list endpoint returns
        self.run_by_id: dict[int, dict] = {}
        self.get_status = 200
        self.get_headers: dict = {}
        self.RequestException = Exception

    def _resp(self, status, body=None, headers=None):
        return SimpleNamespace(status_code=status, headers=headers or {}, text="secret-body-never-shown",
                               json=lambda: body)

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append({"url": url, "json": json, "auth": headers["Authorization"]})
        return self._resp(self.post_status, None, self.get_headers if self.post_status == 403 else {})

    def get(self, url, headers=None, params=None, timeout=None):
        self.gets.append(url)
        if self.get_status != 200:
            return self._resp(self.get_status, {"message": "nope"}, self.get_headers)
        if url.endswith("/runs"):
            return self._resp(200, {"workflow_runs": self.runs})
        return self._resp(200, self.run_by_id[int(url.rsplit("/", 1)[1])])


def run(id_, name, status="queued", conclusion=None):
    return {"id": id_, "display_title": name, "name": name, "status": status, "conclusion": conclusion,
            "html_url": f"https://github.com/o/r/actions/runs/{id_}"}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    with db.session() as s:
        for model in (GenerationJob, ActivityLog, Post):
            s.execute(delete(model))
    route.limiter._hits.clear()
    github_actions.reset()
    monkeypatch.delenv("GENERATE_DAILY_CAP", raising=False)


@pytest.fixture()
def gh(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setenv("GITHUB_DISPATCH_TOKEN", "ghp_faketokenfaketoken")
    monkeypatch.setattr(github_actions, "requests", fake)
    return fake


_n = 0


def body(**kw):
    global _n
    _n += 1
    return {"slot": "auto", "idempotency_key": f"key-{_n:08d}", **kw}


def events(prefix="generate."):
    with db.session() as s:
        return [(e.event, e.level) for e in s.scalars(select(ActivityLog).order_by(ActivityLog.id)) if e.event.startswith(prefix)]


def finish_all():
    for j in generation.recent(50):
        if j["active"]:
            generation.finish(j["id"], "succeeded", topic_title="t", category="AI", group_id="g", post_ids=["p1"])


def item(id_, kind, slot, status="pending", **kw):
    media = {"carousel": ["https://x/1.jpg"]} if kind == "carousel" else {"reel": "https://x/r.mp4"}
    return q.Item(id=id_, kind=kind, date=slot.date().isoformat(), topic=kw.pop("topic", "Binary search"), category="DSA",
                  post_dir=f"output/{slot.date()}/binary-search/{kind}", media=media, caption="c #x", status=status,
                  publish_at=slot.isoformat(), **kw)


# --------------------------------------------------------------------------- #
def test_requires_auth(client):
    assert client.get("/api/generate/config").status_code == 401
    assert client.get("/api/generate/slots").status_code == 401
    assert client.get("/api/generate/jobs").status_code == 401
    client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery"})
    assert client.post("/api/generate", json=body()).status_code == 403  # no CSRF header


def test_without_token_is_visible_and_creates_nothing(authed):
    cfg = authed.get("/api/generate/config").json()
    assert cfg["dispatch_configured"] is False and cfg["slots"] == ["10:00", "19:00"]
    assert {c["name"] for c in cfg["categories"]} == set(generation.CATEGORIES)
    assert authed.get("/api/generate/slots").status_code == 200  # the board and history still load
    r = authed.post("/api/generate", json=body())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "not_configured"
    assert generation.recent() == []


def test_happy_path_dispatches_once_with_inputs(authed, gh):
    # shell metacharacters are just text: they travel as a dispatch input and are never interpreted here
    evil = "Binary search $(rm -rf /) `id` \"; rm -rf /"
    r = authed.post("/api/generate", json=body(category="DSA", topic=evil, source_url="https://example.com/a"))
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "queued" and job["trigger"] == "dashboard" and job["requested_by"] == "admin"
    assert len(gh.posts) == 1
    sent = gh.posts[0]
    assert sent["url"].endswith("/actions/workflows/daily-generate.yml/dispatches")
    slot_at = datetime.fromisoformat(job["slot_at"]).astimezone(IST)   # "auto" resolved ONCE, by the API (QA-L-10)
    assert sent["json"]["inputs"] == {"slot": f"{slot_at:%H:%M}", "date": slot_at.date().isoformat(), "category": "DSA",
                                      "topic": evil, "source_url": "https://example.com/a", "request_id": job["id"],
                                      "dry_run": "false", "force": "false", "allow_duplicate": "false"}
    assert events() == [("generate.requested", "info")]
    assert job["id"] in authed.get("/api/logs", params={"q": job["id"]}).text
    # nothing in any response carries the token or a GitHub body
    assert "ghp_" not in r.text and "secret-body" not in r.text


def test_double_submit_is_one_job_one_dispatch(authed, gh):
    b = body()
    first = authed.post("/api/generate", json=b)
    again = authed.post("/api/generate", json=b)          # double click / retry: same idempotency key
    other = authed.post("/api/generate", json=body())     # second tab: a different key
    assert first.status_code == 201 and again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert other.status_code == 409 and other.json()["detail"]["code"] == "job_active"
    assert other.json()["detail"]["job"]["id"] == first.json()["id"]
    assert len(gh.posts) == 1 and len(generation.recent()) == 1


@pytest.mark.parametrize("patch", [
    {"category": "Cooking"}, {"topic": "abcd", "category": "DSA"}, {"topic": "x" * 121, "category": "DSA"},
    {"topic": "A fine topic"},                                                   # topic without category
    {"topic": "Bad\x00topic here", "category": "DSA"},
    {"category": "DSA", "topic": "A fine topic", "source_url": "http://example.com/a"},
    {"category": "DSA", "topic": "A fine topic", "source_url": "https://127.0.0.1/a"},
    {"category": "DSA", "topic": "A fine topic", "source_url": "https://localhost/a"},
    {"category": "DSA", "topic": "A fine topic", "source_url": "https://user:pw@example.com/a"},
    {"category": "DSA", "topic": "A fine topic", "source_url": "https://10.0.0.1/a"},
    {"category": "DSA", "topic": "A fine topic", "source_url": "https://intranet/a"},
    {"source_url": "https://example.com/a"},                                      # link without topic
    {"slot": "07:00"},
])
def test_validation_rejects(authed, gh, patch):
    r = authed.post("/api/generate", json=body(**patch))
    assert r.status_code == 422, r.text
    assert not gh.posts and generation.recent() == []


def test_slot_taken_needs_force(authed, gh):
    slot = approve_bot.slot_at(datetime.now(IST).date().isoformat(), "10:00")
    q.save([item("c1", "carousel", slot), item("r1", "reel", slot)])
    r = authed.post("/api/generate", json=body(slot="10:00"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "slot_taken" and not gh.posts
    r = authed.post("/api/generate", json=body(slot="10:00", force=True))
    assert r.status_code == 201 and gh.posts[0]["json"]["inputs"]["force"] == "true"


def test_stale_slot_needs_force(authed, gh, monkeypatch):
    monkeypatch.setattr(generation, "slot_state", lambda *a: "stale")
    r = authed.post("/api/generate", json=body(slot="10:00"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "slot_stale" and not gh.posts


def test_duplicate_topic_needs_override(authed, gh):
    q.save([item("r1", "reel", datetime.now(IST) - timedelta(days=3), topic="How Binary Search Works")])
    asked = {"category": "DSA", "topic": "how binary search works!"}
    assert authed.get("/api/generate/check", params={"topic": asked["topic"]}).json()["duplicate"]["title"] == "How Binary Search Works"
    assert authed.get("/api/generate/check", params={"topic": "Consistent hashing explained"}).json()["duplicate"] is None
    r = authed.post("/api/generate", json=body(**asked))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "duplicate_topic" and not gh.posts
    r = authed.post("/api/generate", json=body(**asked, allow_duplicate=True))
    assert r.status_code == 201 and gh.posts[0]["json"]["inputs"]["allow_duplicate"] == "true"


def test_daily_cap_counts_dashboard_requests_only(authed, gh, monkeypatch):
    monkeypatch.setenv("GENERATE_DAILY_CAP", "1")
    generation.create(trigger="scheduled", status="running")  # scheduled runs are not counted
    finish_all()
    assert authed.get("/api/generate/config").json()["used_today"] == 0
    assert authed.post("/api/generate", json=body()).status_code == 201
    finish_all()
    cfg = authed.get("/api/generate/config").json()
    assert cfg["used_today"] == 1 and cfg["daily_cap"] == 1
    r = authed.post("/api/generate", json=body())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cap_reached" and len(gh.posts) == 1


def test_cooldown_between_requests(authed, gh):
    assert authed.post("/api/generate", json=body()).status_code == 201
    finish_all()
    r = authed.post("/api/generate", json=body())
    assert r.status_code == 429 and r.json()["detail"]["code"] == "cooldown" and int(r.headers["Retry-After"]) > 0


def test_quota_failure_needs_confirmation(authed, gh):
    job = generation.create(trigger="scheduled", status="running")
    generation.finish(job["id"], "failed", reason="quota")
    cfg = authed.get("/api/generate/config").json()
    assert cfg["quota_cooldown_until"]
    r = authed.post("/api/generate", json=body())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "quota_cooldown" and not gh.posts
    assert authed.post("/api/generate", json=body(confirm_quota=True)).status_code == 201


@pytest.mark.parametrize("status,reason", [(401, "dispatch_rejected"), (404, "dispatch_rejected"), (500, "dispatch_failed")])
def test_dispatch_refused_marks_job_failed_and_costs_nothing(authed, gh, status, reason):
    gh.post_status = status
    r = authed.post("/api/generate", json=body())
    assert r.status_code == 502 and r.json()["detail"]["code"] == "dispatch_failed"
    assert "secret-body" not in r.text and "ghp_" not in r.text
    [job] = generation.recent()
    assert job["status"] == "failed" and job["failure_reason"] == reason and not job["github_run_url"]
    assert events() == [("generate.requested", "info"), ("generate.failed", "error")]
    assert authed.get("/api/generate/config").json()["used_today"] == 0
    gh.post_status = 204  # the form is usable again straight away (the cooldown aside)
    with db.session() as s:
        s.execute(delete(GenerationJob))
    assert authed.post("/api/generate", json=body()).status_code == 201


def test_dispatch_rate_limit_response_is_not_a_token_problem(authed, gh):
    gh.post_status, gh.get_headers = 403, {"x-ratelimit-remaining": "0"}
    r = authed.post("/api/generate", json=body())
    assert r.status_code == 502 and generation.recent()[0]["failure_reason"] == "dispatch_failed"


# --------------------------------------------------------------------------- #
# Tracking + reconcile
# --------------------------------------------------------------------------- #
def start(authed, gh):
    job = authed.post("/api/generate", json=body()).json()
    return job["id"]


def test_reconcile_finds_run_by_name_and_follows_it(authed, gh):
    jid = start(authed, gh)
    r = authed.get(f"/api/generate/jobs/{jid}").json()
    assert r["job"]["status"] == "queued" and not r["job"]["github_run_url"] and r["github"]["ok"]  # run not listed yet

    github_actions.reset()  # (reads are cached for 5s)
    gh.runs = [run(7, "Generate someone-else"), run(8, f"Generate {jid}", "queued")]
    r = authed.get(f"/api/generate/jobs/{jid}").json()["job"]
    assert r["status"] == "queued" and r["github_run_id"] == 8 and r["github_run_url"].endswith("/runs/8")

    github_actions.reset()
    gh.run_by_id[8] = run(8, f"Generate {jid}", "in_progress")
    r = authed.get(f"/api/generate/jobs/{jid}").json()["job"]
    assert r["status"] == "running" and r["started_at"]

    generation.set_phase(jid, "rendering")
    github_actions.reset()
    gh.run_by_id[8] = run(8, f"Generate {jid}", "completed", "success")
    r = authed.get(f"/api/generate/jobs/{jid}").json()["job"]
    # the run ended but the pipeline never reported: not "succeeded"
    assert r["status"] == "failed" and r["failure_reason"] == "render" and not r["active"]
    assert events()[-1] == ("generate.failed", "error")


def test_run_cancelled_before_it_started_is_superseded(authed, gh):
    jid = start(authed, gh)
    gh.runs = [run(9, f"Generate {jid}", "queued")]
    authed.get(f"/api/generate/jobs/{jid}")
    github_actions.reset()
    gh.run_by_id[9] = run(9, f"Generate {jid}", "completed", "cancelled")
    job = authed.get(f"/api/generate/jobs/{jid}").json()["job"]
    assert (job["status"], job["failure_reason"]) == ("cancelled", "superseded")
    assert events()[-1] == ("generate.cancelled", "warning")
    assert authed.post("/api/generate", json=body()).status_code in (201, 429)  # form is free again (cooldown aside)


def test_no_run_appears_marks_not_started(authed, gh):
    jid = start(authed, gh)
    with db.session() as s:
        s.get(GenerationJob, jid).dispatched_at = datetime.now(UTC) - timedelta(minutes=3)
    job = authed.get(f"/api/generate/jobs/{jid}").json()["job"]
    assert (job["status"], job["failure_reason"]) == ("failed", "not_started")


def test_stuck_job_times_out_even_without_github(authed, monkeypatch):
    monkeypatch.setenv("GITHUB_DISPATCH_TOKEN", "")
    job = generation.create(trigger="scheduled", status="running")
    with db.session() as s:
        s.get(GenerationJob, job["id"]).started_at = datetime.now(UTC) - timedelta(minutes=50)
    jobs = authed.get("/api/generate/jobs").json()
    assert jobs["active"] is None and jobs["jobs"][0]["failure_reason"] == "timeout"


def test_github_rate_limit_keeps_last_state_and_backs_off(authed, gh):
    jid = start(authed, gh)
    gh.runs = [run(8, f"Generate {jid}", "queued")]
    authed.get(f"/api/generate/jobs/{jid}")
    github_actions.reset()
    gh.get_status, gh.get_headers = 403, {"x-ratelimit-remaining": "0", "retry-after": "60"}
    r = authed.get(f"/api/generate/jobs/{jid}").json()
    assert r["github"]["ok"] is False and r["github"]["as_of"] and r["job"]["status"] == "queued"
    calls = len(gh.gets)
    authed.get(f"/api/generate/jobs/{jid}")
    assert len(gh.gets) == calls  # paused: no further calls while GitHub says wait
    github_actions.reset()
    gh.get_status = 200
    gh.run_by_id[8] = run(8, f"Generate {jid}", "in_progress")
    r = authed.get(f"/api/generate/jobs/{jid}").json()
    assert r["github"]["ok"] and r["job"]["status"] == "running"


def test_reads_are_cached_for_a_few_seconds(authed, gh):
    jid = start(authed, gh)
    gh.runs = [run(8, f"Generate {jid}", "queued")]
    authed.get(f"/api/generate/jobs/{jid}")
    gh.run_by_id[8] = run(8, f"Generate {jid}", "queued")
    for _ in range(3):
        authed.get(f"/api/generate/jobs/{jid}")
    assert len([u for u in gh.gets if u.endswith("/runs/8")]) == 1


def test_concurrent_submits_from_two_tabs_dispatch_once(authed, gh):
    import threading
    gate, codes = threading.Barrier(4), []

    def go():
        gate.wait()
        codes.append(authed.post("/api/generate", json=body()).status_code)
    threads = [threading.Thread(target=go) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # one wins; the others hit the lock (409 job_active) or, if the winner already committed, the cooldown (429)
    assert codes.count(201) == 1 and set(codes) - {201} <= {409, 429}, codes
    assert len(gh.posts) == 1 and len(generation.recent()) == 1


def test_post_panel_can_find_the_request_behind_a_group(authed, gh):
    job = authed.post("/api/generate", json=body()).json()
    generation.finish(job["id"], "succeeded", topic_title="t", category="AI", group_id="2026-10-05/t", post_ids=["p1"])
    got = authed.get("/api/generate/for-group", params={"group_id": "2026-10-05/t"}).json()["job"]
    assert got["id"] == job["id"] and got["trigger"] == "dashboard" and got["requested_by"] == "admin"
    assert authed.get("/api/generate/for-group", params={"group_id": "other"}).json() == {"job": None}


def test_unknown_job_404(authed):
    assert authed.get("/api/generate/jobs/deadbeef00").status_code == 404


def test_scheduled_jobs_listed_and_block_dashboard(authed, gh):
    generation.create(trigger="scheduled", status="running", slot_at=datetime.now(UTC))
    jobs = authed.get("/api/generate/jobs").json()
    assert jobs["active"]["trigger"] == "scheduled"
    r = authed.post("/api/generate", json=body())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "job_active" and not gh.posts


# --------------------------------------------------------------------------- #
# Slot board
# --------------------------------------------------------------------------- #
def freeze(monkeypatch, at: datetime):
    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz) if tz else at.replace(tzinfo=None)
    monkeypatch.setattr(route, "datetime", Fixed)


def slots(authed):
    return {(s["date"], s["time"]): s for s in authed.get("/api/generate/slots").json()["slots"]}


def test_slot_board_afternoon(authed, monkeypatch):
    now = datetime(2026, 10, 5, 17, 0, tzinfo=IST)
    freeze(monkeypatch, now)
    s10 = datetime(2026, 10, 5, 10, 0, tzinfo=IST)
    q.save([item("c1", "carousel", s10, topic="Binary search"), item("r1", "reel", s10, "approved", topic="Binary search")])
    board = slots(authed)
    assert len(board) == 4
    done = board[("2026-10-05", "10:00")]
    assert done["state"] == "generated" and done["group_id"] and done["topic"] == "Binary search"
    assert done["items"]["reel"]["status"] == "approved" and done["items"]["carousel"]["status"] == "pending"
    assert done["can_generate"] is False
    nxt = board[("2026-10-05", "19:00")]
    assert nxt["state"] == "upcoming" and nxt["can_generate"] is True and nxt["day"] == "today"
    tomorrow = board[("2026-10-06", "10:00")]
    assert tomorrow["state"] == "upcoming" and tomorrow["day"] == "tomorrow" and tomorrow["can_generate"] is False


def test_slot_board_late_stale_generating_failed(authed, monkeypatch):
    freeze(monkeypatch, datetime(2026, 10, 5, 23, 30, tzinfo=IST))
    board = slots(authed)
    assert board[("2026-10-05", "10:00")]["state"] == "stale"      # 13.5h ago: needs "extra post"
    assert board[("2026-10-05", "19:00")]["state"] == "late"       # 4.5h ago: still generates
    generation.create(trigger="scheduled", status="failed", slot_at=datetime(2026, 10, 5, 10, 0, tzinfo=IST))
    generation.create(trigger="dashboard", status="running", slot_at=datetime(2026, 10, 5, 19, 0, tzinfo=IST))
    board = slots(authed)
    assert board[("2026-10-05", "10:00")]["state"] == "failed" and board[("2026-10-05", "10:00")]["can_generate"]
    gen = board[("2026-10-05", "19:00")]
    assert gen["state"] == "generating" and gen["job"]["status"] == "running" and not gen["can_generate"]


# --------------------------------------------------------------------------- #
# Safety: generating never publishes
# --------------------------------------------------------------------------- #
def test_generate_code_never_publishes():
    forbidden = ("publish_item", "finish_publish", "start_publish_now", "publish_due", "actions.approve",
                 "apply_decision", "trigger_pipeline_run", "poll-approvals")
    for mod in (route, generation, github_actions):
        src = inspect.getsource(mod)
        assert not [w for w in forbidden if w in src], (mod.__name__, [w for w in forbidden if w in src])
    assert generation.WORKFLOW == "daily-generate.yml"


def test_activity_helper_is_used_for_audit(authed, gh):
    authed.post("/api/generate", json=body())
    with db.session() as s:
        row = s.scalars(select(ActivityLog).where(ActivityLog.event == "generate.requested")).one()
    assert row.source == "generate" and row.actor == "admin" and row.detail["request_id"] == generation.recent()[0]["id"]
    assert activity.record  # the never-raising helper


def test_run_matching_takes_the_first_run_with_our_title(gh):
    """QA-L-11: a later hand-started run titled "Generate <id>" can't stand in for ours."""
    from datetime import datetime as dt
    ours = {**run(11, "Generate abc"), "created_at": "2026-10-06T10:00:05Z", "event": "workflow_dispatch", "head_branch": "main"}
    forged = {**run(12, "Generate abc"), "created_at": "2026-10-06T10:00:40Z", "event": "workflow_dispatch", "head_branch": "main"}
    other_branch = {**run(10, "Generate abc"), "created_at": "2026-10-06T09:59:59Z", "head_branch": "evil"}
    gh.runs = [forged, ours, other_branch]                    # GitHub lists newest first
    found = github_actions.find_run("daily-generate.yml", "Generate abc", dt(2026, 10, 6, 10, 0, tzinfo=timezone.utc))
    assert found["id"] == 11


def test_runner_rejects_a_malformed_date():
    import main
    assert main.main(["generate", "--date", "2026-13-45", "--dry-run"]) == 2
