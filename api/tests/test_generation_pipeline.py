"""Generation jobs from the pipeline's side: the lock, the Reporter, and `main.py generate` (all stages faked)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

import main
from src import approve_bot, db, fetch_topics, gen_content, generation, rank_topics, render_post, render_reel, upload
from src import queue_store as q
from src.db.models import ActivityLog, GenerationJob, Post

UTC = timezone.utc
FAR = "2026-01-01"  # an old date keeps `--force` runs independent of the clock


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    with db.session() as s:
        for model in (GenerationJob, ActivityLog, Post):
            s.execute(delete(model))
    monkeypatch.setattr(approve_bot, "notify", lambda *a, **k: None)
    for var in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(var, raising=False)


def events():
    with db.session() as s:
        return [(e.event, e.level) for e in s.scalars(select(ActivityLog).order_by(ActivityLog.id))]


# --------------------------------------------------------------------------- #
# The lock and the job lifecycle
# --------------------------------------------------------------------------- #
def test_only_one_active_job_per_trigger():
    first = generation.create(trigger="dashboard")
    with pytest.raises(generation.JobActive):
        generation.create(trigger="dashboard")
    generation.create(trigger="scheduled", status="running")  # a different trigger has its own lock
    generation.finish(first["id"], "failed", reason="timeout")
    generation.create(trigger="dashboard")                    # free again once the first is final


def test_idempotency_key_replays():
    a = generation.create(trigger="dashboard", idempotency_key="abc12345")
    generation.finish(a["id"], "succeeded")
    with pytest.raises(generation.Replay) as r:
        generation.create(trigger="dashboard", idempotency_key="abc12345")
    assert r.value.job["id"] == a["id"]


def test_finish_happens_once_and_logs_once():
    job = generation.create(trigger="dashboard", requested_by="admin")
    assert generation.finish(job["id"], "failed", reason="quota", message="x" * 500 + " key=AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE")
    assert not generation.finish(job["id"], "succeeded")            # already final: no second event, no overwrite
    got = generation.get(job["id"])
    assert got["status"] == "failed" and got["failure_reason"] == "quota" and len(got["message"]) <= 300
    assert events() == [("generate.failed", "error")]
    assert "AIza" not in generation.scrub("key=AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE Bearer abc.def")


def test_prune_and_expire():
    old = generation.create(trigger="scheduled", status="running")
    with db.session() as s:
        row = s.get(GenerationJob, old["id"])
        row.created_at = datetime.now(UTC) - timedelta(days=100)
        row.started_at = datetime.now(UTC) - timedelta(days=100)
    assert generation.expire_stuck() == 1 and generation.get(old["id"])["failure_reason"] == "timeout"
    assert generation.prune() == 1 and generation.get(old["id"]) is None


def test_a_queued_job_may_wait_behind_another_run_but_not_forever():
    job = generation.create(trigger="dashboard")
    with db.session() as s:
        s.get(GenerationJob, job["id"]).created_at = datetime.now(UTC) - timedelta(minutes=60)
    assert generation.expire_stuck() == 0                       # 60 min queued: still legitimately waiting
    with db.session() as s:
        s.get(GenerationJob, job["id"]).created_at = datetime.now(UTC) - timedelta(minutes=95)
    assert generation.expire_stuck() == 1 and generation.get(job["id"])["failure_reason"] == "timeout"


def _race(n: int, fn) -> list:
    """Run fn(i) on n threads released at the same moment; return each result or exception."""
    import threading
    gate, out = threading.Barrier(n), [None] * n

    def go(i):
        gate.wait()
        try:
            out[i] = fn(i)
        except Exception as e:  # noqa: BLE001
            out[i] = e
    threads = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def test_race_two_tabs_get_one_active_job():
    got = _race(8, lambda i: generation.create(trigger="dashboard", idempotency_key=f"tab-key-{i:04d}"))
    made = [g for g in got if isinstance(g, dict)]
    assert len(made) == 1, got
    assert all(isinstance(g, generation.JobActive) for g in got if not isinstance(g, dict)), got
    assert [j["id"] for j in generation.recent() if j["active"]] == [made[0]["id"]]


def test_race_double_click_same_key_is_one_job():
    got = _race(6, lambda i: generation.create(trigger="dashboard", idempotency_key="same-key-123"))
    made = [g for g in got if isinstance(g, dict)]
    replays = [g for g in got if isinstance(g, generation.Replay)]
    assert len(made) == 1 and len(replays) == len(got) - 1, got
    assert {r.job["id"] for r in replays} == {made[0]["id"]} and len(generation.recent()) == 1


def test_partial_unique_index_holds_on_postgres():
    """The lock as production has it. Runs only against a throwaway Postgres (GENERATION_PG_URL, e.g. the local
    docker DB) inside a private schema that is dropped afterwards; never against the real database."""
    import os
    url = os.getenv("GENERATION_PG_URL")
    if not url:
        pytest.skip("set GENERATION_PG_URL to a throwaway Postgres to run")
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError
    schema = "gen_lock_test"
    eng = create_engine(url, pool_size=10).execution_options(schema_translate_map={None: schema})
    with eng.begin() as c:
        c.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        c.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        GenerationJob.__table__.create(eng)

        def insert(i):
            with eng.begin() as c:
                c.execute(GenerationJob.__table__.insert().values(
                    id=f"job{i:04d}", trigger="dashboard", status="queued", idempotency_key=f"k{i:08d}",
                    created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
            return i
        got = _race(8, insert)
        assert sum(isinstance(g, int) for g in got) == 1, got
        assert all(isinstance(g, IntegrityError) for g in got if not isinstance(g, int))
        with eng.begin() as c:                                    # a finished job frees the lock
            c.execute(text(f"UPDATE {schema}.generation_jobs SET status='failed'"))
        assert insert(99) == 99
    finally:
        with eng.begin() as c:
            c.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        eng.dispose()


@pytest.mark.parametrize("url,ok", [
    ("https://example.com/post", True), ("https://news.ycombinator.com/item?id=1", True), ("", True),
    ("http://example.com", False), ("https://127.0.0.1", False), ("https://[::1]/", False), ("https://192.168.1.2/",
     False), ("https://localhost", False), ("https://db.internal/x", False), ("https://a@example.com", False),
    ("ftp://example.com", False), ("https://example.com/a b", False), ("https://" + "a" * 600 + ".com", False),
])
def test_source_url_rules(url, ok):
    if ok:
        generation.clean_source_url(url)
    else:
        with pytest.raises(ValueError):
            generation.clean_source_url(url)


def test_classify():
    assert generation.classify(RuntimeError("Gemini failed on all models: 429 RESOURCE_EXHAUSTED"), "writing") == "quota"
    assert generation.classify(RuntimeError("Gemini failed ... quota"), "ranking") == "quota"
    assert generation.classify(RuntimeError("boom"), "rendering") == "render"
    assert generation.classify(RuntimeError("boom"), "uploading") == "upload"
    assert generation.classify(RuntimeError("boom"), None) == "unknown"


def test_reporter_never_raises(monkeypatch):
    job = generation.create(trigger="dashboard")
    monkeypatch.setattr(db, "session", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    rep = generation.Reporter(job["id"])
    rep.phase("writing")
    rep.skipped("taken", "x")
    rep.failed(RuntimeError("y"))
    rep.succeeded("t", "AI", "g", ["a"])
    assert generation.Reporter.begin(None, slot_at=None, category=None, topic=None, source_url=None,
                                     force=False, allow_duplicate=False).job_id is None
    monkeypatch.setattr(db, "enabled", lambda: False)
    assert generation.Reporter.begin(None, slot_at=None, category=None, topic=None, source_url=None,
                                     force=False, allow_duplicate=False).job_id is None


def test_end_run_closes_by_request_or_run_id(monkeypatch):
    a = generation.create(trigger="dashboard")
    generation.set_phase(a["id"], "uploading")
    assert generation.end_run("failure", a["id"]) and generation.get(a["id"])["failure_reason"] == "upload"
    monkeypatch.setenv("GITHUB_RUN_ID", "555")
    b = generation.create(trigger="scheduled", status="running", run_id=555)
    assert generation.end_run("cancelled", None) and generation.get(b["id"])["status"] == "cancelled"
    assert not generation.end_run("failure", None)                # nothing left to close


# --------------------------------------------------------------------------- #
# main.py generate
# --------------------------------------------------------------------------- #
class Stages:
    """Fakes every expensive stage and records the order they ran in."""

    def __init__(self, monkeypatch):
        self.calls: list[str] = []
        self.topic = None
        self.fail_at: tuple[str, Exception] | None = None

        def stage(name, ret=None):
            def fn(*a, **k):
                self.calls.append(name)
                if self.fail_at and self.fail_at[0] == name:
                    raise self.fail_at[1]
                return ret(*a, **k) if callable(ret) else ret
            return fn

        def generate(topic, *a, **k):
            self.topic = topic
            self.calls.append("write")
            if self.fail_at and self.fail_at[0] == "write":
                raise self.fail_at[1]
            return SimpleNamespace(carousel=[1, 2, 3])

        monkeypatch.setattr(fetch_topics, "main", stage("fetch"))
        monkeypatch.setattr(rank_topics, "rank", stage("rank", lambda *a, **k: SimpleNamespace(
            category="DSA", title="Ranked pick", angle="a", source_url="")))
        monkeypatch.setattr(gen_content, "generate", generate)
        monkeypatch.setattr(gen_content, "save", lambda content, day: Path("output/x/content.json"))
        monkeypatch.setattr(render_post, "render_carousel", stage("render-carousel"))
        monkeypatch.setattr(render_reel, "render_reel", stage("render-reel"))
        monkeypatch.setattr(render_reel, "pick_voice", lambda: "v")
        monkeypatch.setattr(render_reel, "_default_music", lambda: None)
        monkeypatch.setattr(upload, "upload_post", stage("upload"))
        self.items = [SimpleNamespace(id=f"{k}-1", kind=k, topic="T", version=1, group_id="2026-01-01/t") for k in ("carousel", "reel")]
        monkeypatch.setattr(approve_bot, "items_from_post", lambda *a, **k: self.items)
        monkeypatch.setattr(approve_bot, "send_preview", stage("preview"))


@pytest.fixture()
def stages(monkeypatch):
    return Stages(monkeypatch)



def gen(*args):
    return main.main(["generate", "--date", FAR, "--slot", "10:00", "--force", *args])


def test_scheduled_run_reports_phases_and_succeeds(stages, monkeypatch):
    seen = []
    real = generation.set_phase
    monkeypatch.setattr(generation, "set_phase", lambda job_id, phase: (seen.append(phase), real(job_id, phase))[1])
    assert gen() == 0
    assert seen == ["fetching_topics", "ranking", "writing", "rendering", "uploading", "sending_previews"]
    assert stages.calls == ["fetch", "rank", "write", "render-carousel", "render-reel", "upload", "preview", "preview"]
    [job] = generation.recent()
    assert (job["status"], job["trigger"], job["phase"]) == ("succeeded", "scheduled", "done")
    assert job["topic_title"] == "Ranked pick" and job["post_ids"] == ["carousel-1", "reel-1"] and job["post_group_id"]
    assert [e for e, _ in events() if e.startswith("generate.")] == ["generate.started", "generate.finished"]


def test_dashboard_job_is_adopted_by_its_run(stages, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "4242")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    queued = generation.create(trigger="dashboard", requested_by="admin", category="DSA", topic="Topic about sharding")
    assert gen("--category", "DSA", "--topic", "Topic about sharding", "--request-id", queued["id"]) == 0
    [job] = generation.recent()
    assert job["id"] == queued["id"] and job["status"] == "succeeded" and job["trigger"] == "dashboard"
    assert job["github_run_url"] == "https://github.com/o/r/actions/runs/4242" and job["started_at"]
    # custom topic: no trending fetch, no ranking; the topic goes straight to writing
    assert "fetch" not in stages.calls and "rank" not in stages.calls
    assert (stages.topic.title, stages.topic.category) == ("Topic about sharding", "DSA")


def test_custom_topic_with_shell_text_stays_text(stages):
    evil = "Sharding $(touch /tmp/x) `id` \"; rm -rf / #"
    assert gen("--category", "DSA", "--topic", evil, "--source-url", "https://example.com/a") == 0
    assert stages.topic.title == evil and stages.topic.source_url == "https://example.com/a"


@pytest.mark.parametrize("args", [
    ["--topic", "Valid topic here"],                                       # needs a category
    ["--category", "Cooking"], ["--category", "DSA", "--topic", "abc"],
    ["--category", "DSA", "--topic", "Valid topic here", "--source-url", "http://example.com"],
    ["--category", "DSA", "--source-url", "https://example.com"],           # link without a topic
])
def test_bad_input_is_refused_before_anything_runs(stages, args):
    assert gen(*args) == 2
    assert stages.calls == [] and generation.recent() == []


def test_bad_slot_is_refused(stages):
    assert main.main(["generate", "--slot", "07:15"]) == 2 and stages.calls == []


def test_duplicate_topic_is_skipped_visibly_unless_allowed(stages):
    q.save([q.Item(id="r9", kind="reel", date="2026-01-01", topic="How Sharding Works", category="DSA", post_dir="o/d/s/",
                   caption="c", status="published")])
    assert gen("--category", "DSA", "--topic", "how sharding works") == 0
    [job] = generation.recent()
    assert (job["status"], job["failure_reason"]) == ("skipped", "duplicate") and "How Sharding Works" in job["message"]
    assert "write" not in stages.calls
    assert gen("--category", "DSA", "--topic", "how sharding works", "--allow-duplicate") == 0
    assert "write" in stages.calls


def test_taken_slot_is_reported_as_skipped_not_succeeded(stages):
    slot = approve_bot.slot_at(FAR, "10:00")
    q.save([q.Item(id="r1", kind="reel", date=FAR, topic="Existing", category="AI", post_dir="o/e/", caption="c",
                   publish_at=slot.isoformat())])
    assert main.main(["generate", "--date", FAR, "--slot", "10:00"]) == 0
    [job] = generation.recent()
    assert (job["status"], job["failure_reason"]) == ("skipped", "taken") and stages.calls == []
    assert events()[-1] == ("generate.skipped", "warning")


def test_stale_slot_is_reported_as_skipped(stages):
    assert main.main(["generate", "--date", FAR, "--slot", "10:00"]) == 0
    [job] = generation.recent()
    assert (job["status"], job["failure_reason"]) == ("skipped", "stale")


@pytest.mark.parametrize("stage,error,reason", [
    ("write", RuntimeError("Gemini failed on all models: 429 RESOURCE_EXHAUSTED quota"), "quota"),
    ("render-carousel", RuntimeError("chromium crashed"), "render"),
    ("upload", RuntimeError("cloudinary 500"), "upload"),
    ("preview", RuntimeError("telegram down"), "telegram"),
    ("fetch", RuntimeError("hn down"), "fetch"),
])
def test_failure_is_classified_and_nothing_is_partially_sent(stages, stage, error, reason):
    stages.fail_at = (stage, error)
    assert gen() == 1  # main() still reports the failure to Telegram and exits non-zero
    [job] = generation.recent()
    assert (job["status"], job["failure_reason"]) == ("failed", reason) and not job["active"]
    assert events()[-1] == ("generate.failed", "error")
    if stage != "preview":
        assert "preview" not in stages.calls  # no Telegram preview before every stage has succeeded


def test_dry_run_never_touches_jobs(stages):
    assert gen("--dry-run", "--category", "DSA", "--topic", "Valid topic here") == 0
    assert generation.recent() == [] and "upload" not in stages.calls and "preview" not in stages.calls


def test_generation_never_publishes_or_approves(stages):
    assert gen() == 0
    with db.session() as s:
        assert s.scalars(select(Post).where(Post.status.in_(("approved", "publishing", "published")))).all() == []


def test_job_end_command_closes_a_dead_run(monkeypatch):
    job = generation.create(trigger="dashboard")
    generation.set_phase(job["id"], "rendering")
    assert main.main(["job-end", "--outcome", "failure", "--request-id", job["id"]]) == 0
    assert generation.get(job["id"])["failure_reason"] == "render"
    assert main.main(["job-end", "--outcome", "failure", "--request-id", "zzzz"]) == 0  # unknown id: harmless


def test_poll_expires_stuck_jobs(monkeypatch):
    job = generation.create(trigger="dashboard")
    with db.session() as s:
        s.get(GenerationJob, job["id"]).created_at = datetime.now(UTC) - timedelta(hours=3)
    assert generation.expire_stuck() == 1 and generation.get(job["id"])["status"] == "failed"
