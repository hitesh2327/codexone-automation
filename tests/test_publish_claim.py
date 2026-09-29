"""Only one publisher may publish an item.

A scheduled poll and a manual publish overlapped on 29 Sep and both posted the same
carousel and reel to Instagram (and two copies to YouTube). Run from the repo root:
    python -m pytest tests -q
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'claim.db').as_posix()}"

from src import db  # noqa: E402
from src import queue_store as q  # noqa: E402
from src.db.models import Base  # noqa: E402

for fn in (db.engine, db._sessionmaker):
    fn.cache_clear()
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
