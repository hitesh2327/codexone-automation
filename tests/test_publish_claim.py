"""Only one publisher may publish an item.

A scheduled poll and a manual publish overlapped on 29 Sep and both posted the same
carousel and reel to Instagram (and two copies to YouTube). Run from the repo root:
    python -m pytest tests -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db  # noqa: E402
from src import queue_store as q  # noqa: E402
from src.db.models import Base  # noqa: E402

# The session's throwaway database comes from the repo-root conftest.py; this module no longer redirects it
# (QA-L-13). create_all is idempotent.
assert db.database_url().startswith("sqlite:///"), "tests must never run against a real database"
Base.metadata.create_all(db.engine())


def make(item_id: str, status: str) -> q.Item:
    item = q.Item(id=item_id, kind="reel", date="2026-09-29", topic="T", category="AI",
                  post_dir="output/2026-09-29/t", caption="c\n\n#x", status=status)
    q.upsert(item)
    return item


@pytest.mark.parametrize("status,expected", [
    ("approved", True),
    ("failed", True),       # a retry of a failed platform may claim
    ("pending", False),     # never publishable
    ("rejected", False),
    ("published", False),
    ("publishing", False),  # someone already holds it
    ("expired", False),
])
def test_only_publishable_states_can_be_claimed(status, expected):
    item = make(f"claim-{status}", status)
    assert q.claim_for_publish(item.id) is expected
    assert q.get(item.id).status == ("publishing" if expected else status)


def test_second_publisher_backs_off():
    """The exact 29 Sep race: two runs try to publish the same approved item."""
    item = make("claim-race", "approved")
    assert q.claim_for_publish(item.id) is True     # the poll wins
    assert q.claim_for_publish(item.id) is False    # the manual publish backs off
    assert q.get(item.id).status == "publishing"


def test_stuck_publish_is_released_for_retry():
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update
    from src.db.models import Post

    item = make("claim-stuck", "approved")
    assert q.claim_for_publish(item.id) is True
    assert q.release_stuck_publishing(30) == []     # still running: left alone

    with db.session() as s:                          # pretend the publisher died 45 min ago
        s.execute(update(Post).where(Post.id == item.id)
                  .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=45)))
    assert q.release_stuck_publishing(30, dry_run=True) == [item.id]
    assert q.get(item.id).status == "publishing"     # dry run changes nothing
    assert q.release_stuck_publishing(30) == [item.id]
    assert q.get(item.id).status == "failed"
    assert q.claim_for_publish(item.id) is True      # retryable again


# --------------------------------------------------------------------------- #
# QA-H-01: the dashboard's "publish now" / "retry" use the same claim as the poll
# --------------------------------------------------------------------------- #
import threading  # noqa: E402
import time  # noqa: E402
from datetime import datetime as _dt, timedelta as _td  # noqa: E402


@pytest.fixture
def fake_platforms(monkeypatch):
    """No network: every IG/YT publish is recorded with the caller's thread name."""
    from src import actions, publish
    monkeypatch.setenv("TELEGRAM_SYNC", "false")
    monkeypatch.setenv("PUBLISH_ENABLED", "true")
    monkeypatch.setenv("PUBLISH_VIA", "inline")
    monkeypatch.setenv("GITHUB_DISPATCH_TOKEN", "")
    calls: list[tuple[str, str, str]] = []

    def fake(p):
        def run(item):
            calls.append((p, item.id, threading.current_thread().name))
            time.sleep(0.05)
            return {"status": "published", "id": f"{p}-1", "url": ""}
        return run
    monkeypatch.setattr(publish, "_publish_ig", fake("ig"))
    monkeypatch.setattr(publish, "_publish_yt", fake("yt"))
    monkeypatch.setattr(publish, "notify", lambda *a, **k: None)
    monkeypatch.setattr(actions, "trigger_pipeline_run", lambda *a, **k: False)
    return calls


def _due(item_id: str, status: str = "approved", kind: str = "carousel", **kw) -> q.Item:
    item = q.Item(id=item_id, kind=kind, date="2026-10-06", topic="T", category="AI",
                  post_dir=f"output/2026-10-06/{item_id}", caption="c\n\n#x", status=status,
                  media={"carousel": ["https://x/1.jpg", "https://x/2.jpg"]},
                  publish_at=(_dt.now(q.IST) - _td(minutes=5)).isoformat(timespec="seconds"), **kw)
    q.upsert(item)
    return item


def test_publish_now_loses_to_a_poll_that_already_claimed(fake_platforms):
    from src import actions
    _due("h01-a")
    assert q.claim_for_publish("h01-a") is True               # the poll got there first
    with pytest.raises(actions.ActionError):
        actions.start_publish_now("h01-a")                     # -> 409, nothing overwritten
    assert q.get("h01-a").status == "publishing"
    assert fake_platforms == []


def test_poll_backs_off_from_a_dashboard_claim(fake_platforms):
    from src import actions, publish
    stale = _due("h01-b")                                       # the poll's copy, read before the click
    assert actions.start_publish_now("h01-b").status == "publishing"
    publish.publish_due()                                       # the next poll: not its item any more
    publish.publish_item(stale)                                # stale "approved" copy: claim fails
    assert [c for c in fake_platforms if c[1] == "h01-b"] == []  # (the shared test DB may hold other due items)
    actions.finish_publish("h01-b")
    assert [c[:2] for c in fake_platforms if c[1] == "h01-b"] == [("ig", "h01-b")]
    assert q.get("h01-b").status == "published"


def test_unclaimed_publishing_is_not_permission(fake_platforms):
    from src import publish
    item = _due("h01-c", status="publishing")
    publish.publish_item(item)
    assert fake_platforms == [] and q.get("h01-c").status == "publishing"


def test_retry_loses_to_a_running_publisher(fake_platforms):
    from src import actions
    _due("h01-d", status="failed", platforms={"ig": {"status": "failed", "error": "x", "attempts": 1}})
    assert q.claim_for_publish("h01-d") is True                 # publish_due is retrying it
    with pytest.raises(actions.ActionError):
        actions.start_retry("h01-d", "ig")
    assert q.get("h01-d").status == "publishing" and fake_platforms == []


def test_publish_now_races_poll_exactly_one_publish(fake_platforms, monkeypatch):
    """QA repro race_publish.py: a slow Telegram edit widens the window between approve and claim."""
    from src import actions, approve_bot, publish
    monkeypatch.setattr(approve_bot, "mark_decided", lambda *a, **k: time.sleep(0.3))
    for n in range(3):
        _due(f"h01-race{n}")
        barrier = threading.Barrier(2)

        def dash():
            barrier.wait()
            try:
                if actions.start_publish_now(f"h01-race{n}").status == "publishing":
                    actions.finish_publish(f"h01-race{n}")
            except actions.ActionError:
                pass

        def poll():
            barrier.wait()
            time.sleep(0.1)
            publish.publish_due()
        threads = [threading.Thread(target=dash, name="dash"), threading.Thread(target=poll, name="poll")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert [c[:2] for c in fake_platforms if c[1] == f"h01-race{n}"] == [("ig", f"h01-race{n}")]
        assert q.get(f"h01-race{n}").status == "published"


def test_claimed_item_with_nothing_left_is_not_left_publishing(fake_platforms):
    from src import publish
    _due("h01-e", status="published", platforms={"ig": {"status": "published", "id": "1"}})
    assert q.claim_for_publish("h01-e", ("published",)) is True
    publish.publish_item(q.get("h01-e"), claimed=True)
    assert q.get("h01-e").status == "published" and fake_platforms == []


def test_stale_copy_cannot_overwrite_a_claim():
    item = _due("h01-f")
    assert q.claim_for_publish(item.id) is True
    item.caption = "edited"
    assert q.update_if(item, "approved") is False
    assert q.get(item.id).status == "publishing" and q.get(item.id).caption == "c\n\n#x"


def test_one_unreadable_row_does_not_break_the_queue():
    """QA-L-12: a row with a status this code doesn't know used to make q.load() (Posts, Generate, poll) fail."""
    from sqlalchemy import update
    from src.db.models import Post
    good = _due("l12-good")
    bad = _due("l12-bad")
    with db.session() as s:
        s.execute(update(Post).where(Post.id == bad.id).values(status="weird_status"))
    ids = {i.id for i in q.load()}
    assert good.id in ids and bad.id not in ids
    assert q.get(bad.id) is None and q.get(good.id).status == "approved"
    with db.session() as s:
        s.execute(update(Post).where(Post.id == bad.id).values(status="rejected"))
