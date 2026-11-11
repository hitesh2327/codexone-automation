"""Comprehensive QA Reliability & Stress Audit Test Suite.
Authored by: Clint Barton - Senior QA Reliability & Concurrency Engineer.
Validates concurrency, failure recovery, state machines, and edge case leaks across
src/publish.py, src/actions.py, src/publish_youtube.py, src/approve_bot.py, and queue_store.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime as _dt, timedelta as _td
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import actions, approve_bot, db, publish, publish_youtube
from src import queue_store as q
from src.db.models import Base

assert db.database_url().startswith("sqlite:///"), "tests must never run against a real database"
Base.metadata.create_all(db.engine())


def _make_item(item_id: str, status: str = "approved", kind: str = "reel", publish_at: str | None = None, **kw) -> q.Item:
    item = q.Item(
        id=item_id,
        kind=kind,
        date="2026-10-06",
        topic="Topic " + item_id,
        category="AI",
        post_dir=f"output/2026-10-06/{item_id}",
        caption="Caption content\n\n#tag",
        status=status,
        media={"reel": "https://res.cloudinary.com/demo/video.mp4"},
        publish_at=publish_at or (_dt.now(q.IST) - _td(minutes=5)).isoformat(timespec="seconds"),
        **kw,
    )
    q.upsert(item)
    return item


# --------------------------------------------------------------------------- #
# 1. Concurrency & Race Conditions in Publishing
# --------------------------------------------------------------------------- #

def test_start_publish_now_two_step_race_window(monkeypatch):
    """MNT-1308: Atomic claim in start_publish_now eliminates two-step race window."""
    monkeypatch.setenv("PUBLISH_ENABLED", "true")
    monkeypatch.setenv("PUBLISH_VIA", "inline")

    item = _make_item("test-pnow-window", status="approved")

    orig_update_if = q.update_if
    def stealing_update_if(it, before):
        # Simulate publish_due winning the claim right before update_if
        assert q.claim_for_publish(item.id, ("approved",)) is True
        return orig_update_if(it, before)

    monkeypatch.setattr(q, "update_if", stealing_update_if)

    with pytest.raises(actions.ActionError) as exc_info:
        actions.start_publish_now(item.id)

    assert "Another run is already publishing this post" in str(exc_info.value)


def test_partial_retry_prematurely_marks_post_as_published(monkeypatch):
    """BUG: When finishing a single retried platform (e.g. YouTube), if that platform succeeds,
    publish.py evaluates 'failed' only against the requested platform subset.
    If Instagram had failed, the post is falsely marked 'published' and Instagram is lost forever."""
    monkeypatch.setenv("PUBLISH_ENABLED", "true")
    monkeypatch.setenv("PUBLISH_VIA", "inline")
    monkeypatch.setattr(publish, "notify", lambda *a, **k: None)

    item = _make_item(
        "test-partial-retry",
        status="publishing",
        platforms={
            "ig": {"status": "failed", "error": "IG container timeout", "attempts": 1},
            "yt": {"status": "failed", "error": "YT quota exceeded", "attempts": 1},
        },
    )

    # Simulate retrying ONLY YouTube, and YouTube succeeds
    def fake_yt(it):
        return {"status": "published", "id": "yt-ok-123", "url": "https://youtube.com/shorts/yt-ok-123"}

    monkeypatch.setattr(publish, "_publish_yt", fake_yt)

    # Run publish_item with claimed=True and platforms=('yt',) as actions.finish_publish does
    res = publish.publish_item(item, platforms=("yt",), claimed=True)

    # BUG VERIFICATION:
    # YouTube is published, but Instagram is still failed:
    assert res.platforms["yt"]["status"] == "published"
    assert res.platforms["ig"]["status"] == "failed"

    # Overall post status remains failed because Instagram is still failed:
    assert res.status == "failed"
    assert res.error is not None

    due_items = [i.id for i in q.load(statuses=("approved", "failed"))]
    assert item.id in due_items, "Post remains in retry queue for uncompleted platforms"


def test_duplicate_instagram_publish_on_container_timeout_and_retry(monkeypatch):
    """CRITICAL P0: In publish_reel / publish_carousel, if _call('POST', ... /media_publish)
    times out on the network after Meta has already published the container, the container ID
    is lost. A subsequent retry will create a brand new container and publish it again,
    causing duplicate posts on Instagram."""
    monkeypatch.setenv("PUBLISH_ENABLED", "true")
    monkeypatch.setenv("PUBLISH_VIA", "inline")
    monkeypatch.setattr(publish, "notify", lambda *a, **k: None)

    container_creations = []
    publish_calls = []

    def fake_call(method, path, **params):
        if method == "POST" and path.endswith("/media"):
            cid = f"container-{len(container_creations)+1}"
            container_creations.append(cid)
            return {"id": cid}
        if method == "GET" and "container-" in path:
            return {"status_code": "FINISHED"}
        if method == "POST" and path.endswith("/media_publish"):
            publish_calls.append(params.get("creation_id"))
            if len(publish_calls) == 1:
                # First run: Meta published it, but HTTP response timed out / network reset
                raise publish.IGError("POST media_publish failed: network error: Read timed out")
            return {"id": "ig-media-ok-123"}
        if method == "GET" and "ig-media" in path:
            return {"permalink": "https://instagram.com/p/123"}
        return {}

    monkeypatch.setattr(publish, "_call", fake_call)
    monkeypatch.setattr(publish, "_user", lambda: "12345678")

    item = _make_item("test-ig-duplicate", status="approved", kind="reel", targets=["ig"])

    # Attempt 1: First publish runs, container is published on Meta, but network error occurs
    res1 = publish.publish_item(item, platforms=("ig",))
    assert res1.status == "failed"
    assert res1.platforms["ig"]["status"] == "failed"
    assert len(container_creations) == 1

    # Attempt 2: retry occurs (e.g. by publish_due or dashboard retry)
    res2 = publish.publish_item(res1, platforms=("ig",))

    # Container is reused across retry, preventing duplicate publish:
    assert len(container_creations) == 1
    assert len(publish_calls) == 2


def test_quota_exceeded_permanently_exhausts_retries_before_midnight(monkeypatch):
    """MNT-1306: Quota exceeded records quota_exhausted=True, avoids burning regular
    retry attempts rapidly, and remains retryable after midnight Pacific."""
    monkeypatch.setenv("PUBLISH_ENABLED", "true")
    monkeypatch.setenv("PUBLISH_VIA", "inline")
    monkeypatch.setattr(publish, "notify", lambda *a, **k: None)

    item = _make_item("test-yt-quota", status="approved", kind="reel", targets=["yt"])

    # Mock YouTube upload failing with quotaExceeded
    def fake_publish_yt(it):
        raise publish_youtube.YTError("YouTube upload rejected: HTTP 403 quotaExceeded (daily API quota used up)")

    monkeypatch.setattr(publish, "_publish_yt", fake_publish_yt)

    # Attempt 1: First publish runs and fails with quotaExceeded
    item = publish.publish_item(item, platforms=("yt",))
    assert item.status == "failed"
    assert item.platforms["yt"]["attempts"] == 1
    assert item.platforms["yt"]["quota_exhausted"] is True

    # Quota exceeded halts immediate retries until quota reset:
    assert publish._retryable(item, ("yt",)) is False

    # Does not burn regular retry attempts rapidly:
    item = publish.publish_item(item, platforms=("yt",))
    assert item.platforms["yt"]["attempts"] == 1
    assert item.platforms["yt"]["quota_exhausted"] is True

    # After midnight Pacific quota reset, it is retryable again:
    monkeypatch.setattr(publish, "_is_quota_reset", lambda at: True)
    assert publish._retryable(item, ("yt",)) is True


def test_telegram_poll_deleted_post_callback_hangs_without_answer(monkeypatch):
    """BUG: When an inline button is pressed for a deleted or nonexistent post,
    approve_bot._poll_bot executes 'continue' without calling answer_callback_query.
    This causes the Telegram client to display an infinite loading spinner for 30-60s."""
    mock_bot = MagicMock()
    mock_bot.__aenter__.return_value = mock_bot

    mock_cq = MagicMock()
    mock_cq.data = "approve:deleted-post-id"
    mock_cq.id = "cq-deleted"
    mock_cq.message.chat.id = 12345

    mock_update = MagicMock()
    mock_update.update_id = 600
    mock_update.callback_query = mock_cq
    mock_update.message = None

    async def fake_get_updates(*a, **k):
        return [mock_update]

    async def fake_noop(*a, **k):
        return None

    mock_bot.get_updates = fake_get_updates
    mock_bot.answer_callback_query = MagicMock(side_effect=fake_noop)

    import asyncio
    applied = asyncio.run(approve_bot._poll_bot(mock_bot, "token", "tg_offset", {}, {}, False, True))

    assert applied == []
    # answer_callback_query must be called to dismiss the Telegram spinner (MNT-1309)
    mock_bot.answer_callback_query.assert_called_with("cq-deleted", "This post was deleted.")


# --------------------------------------------------------------------------- #
# 2. YouTube Shorts Upload State Machine
# --------------------------------------------------------------------------- #

def test_download_tempfile_leaks_on_network_failure(monkeypatch):
    """BUG: In publish_youtube._download, tempfile.mkstemp creates a file on disk before
    making requests.get(). If requests.get() raises an error or times out, no try/finally
    cleans up the temp file, permanently leaking orphaned .mp4 files on disk."""
    temp_dir = Path(tempfile.gettempdir())
    before_files = set(temp_dir.glob("*.mp4"))

    def fake_get_fail(*args, **kwargs):
        raise requests.exceptions.Timeout("Connection to Cloudinary timed out after 120s")

    monkeypatch.setattr(requests, "get", fake_get_fail)

    with pytest.raises(requests.exceptions.Timeout):
        publish_youtube._download("https://res.cloudinary.com/demo/nonexistent.mp4")

    after_files = set(temp_dir.glob("*.mp4"))
    leaked = after_files - before_files

    assert len(leaked) == 0, "Temp file must be cleaned up and not leak on disk!"
    for f in leaked:
        f.unlink(missing_ok=True)  # clean up after test


def test_youtube_upload_429_treated_as_fatal(monkeypatch):
    """MNT-1305: HTTP 429 is in RETRIABLE_STATUS and retried with backoff."""
    assert 429 in publish_youtube.RETRIABLE_STATUS

    from googleapiclient.errors import HttpError
    from httplib2 import Response

    monkeypatch.setattr(publish_youtube.time, "sleep", lambda s: None)

    resp = Response({"status": "429", "reason": "Too Many Requests"})
    http_error = HttpError(resp, b'{"error": {"code": 429, "message": "User rate limit exceeded"}}')

    mock_request = MagicMock()
    mock_request.next_chunk.side_effect = http_error

    with pytest.raises(publish_youtube.YTError) as exc_info:
        publish_youtube._run_upload(mock_request)

    assert "YouTube upload failed after 6 retries: HTTP 429" in str(exc_info.value)
    assert mock_request.next_chunk.call_count == 7


# --------------------------------------------------------------------------- #
# 3. Telegram Approval Bot Polling
# --------------------------------------------------------------------------- #

def test_telegram_poll_unhandled_conflict_exception(monkeypatch):
    """FIX (MNT-1307): approve_bot.poll catches Conflict (HTTP 409), backs off for 5s,
    and cleanly exits or retries instead of crashing the GitHub Actions runner."""
    from telegram.error import Conflict

    monkeypatch.setattr(approve_bot, "sync_enabled", lambda: True)
    slept = []
    monkeypatch.setattr(approve_bot.time, "sleep", lambda s: slept.append(s))

    calls = 0

    def fake_poll(dry_run):
        nonlocal calls
        calls += 1
        raise Conflict("Conflict: terminated by other getUpdates request")

    monkeypatch.setattr(approve_bot, "_poll", fake_poll)

    res = approve_bot.poll()
    assert res == []
    assert calls == 2  # initial try + 1 retry
    assert slept == [5]


def test_telegram_poll_expired_callback_does_not_remove_markup(monkeypatch):
    """BUG: If an expired post button is pressed, line 521 checks item.status != 'pending',
    calls answer_callback_query('Already expired.'), and immediately does 'continue'.
    It never removes the inline keyboard markup, leaving unusable buttons active in chat,
    and ignores DECIDABLE['approve'] which allows reviving expired posts."""
    # We can inspect the code logic directly in _poll_bot:
    item = _make_item("test-tg-expired", status="expired")

    mock_bot = MagicMock()
    mock_bot.__aenter__.return_value = mock_bot

    mock_cq = MagicMock()
    mock_cq.data = f"approve:{item.id}"
    mock_cq.id = "cq-123"
    mock_cq.message.chat.id = 12345
    mock_cq.message.message_id = 999

    mock_update = MagicMock()
    mock_update.update_id = 500
    mock_update.callback_query = mock_cq
    mock_update.message = None

    async def fake_get_updates(*a, **k):
        return [mock_update]

    async def fake_noop(*a, **k):
        return None

    mock_bot.get_updates = fake_get_updates
    mock_bot.answer_callback_query = MagicMock(side_effect=fake_noop)
    mock_bot.edit_message_reply_markup = MagicMock(side_effect=fake_noop)

    monkeypatch.setattr(approve_bot, "_chat_id", lambda uid=None: 12345)
    monkeypatch.setattr(approve_bot, "_user_uses_token", lambda *a: True)

    items = {item.id: item}
    by_msg = {}

    import asyncio
    applied = asyncio.run(approve_bot._poll_bot(mock_bot, "token", "tg_offset", items, by_msg, False, True))

    # It was rejected:
    assert applied == []
    # Callback query answered with "Already expired."
    mock_bot.answer_callback_query.assert_called_with("cq-123", "Already expired.")
    # edit_message_reply_markup must be called to dismantle dead buttons (MNT-1310)
    mock_bot.edit_message_reply_markup.assert_called_with(12345, 999, reply_markup=None)


# End of test suite


# --------------------------------------------------------------------------- #
# 4. Background Workflows & Scheduling
# --------------------------------------------------------------------------- #

def test_file_mode_release_stuck_publishing_returns_empty(monkeypatch, tmp_path):
    """FIX (MNT-1303): In file mode (DATABASE_URL unset), release_stuck_publishing
    releases stuck publishing items older than cutoff to 'failed'."""
    fake_queue = tmp_path / "queue.json"
    monkeypatch.setattr(q, "QUEUE_FILE", fake_queue)
    monkeypatch.setattr(db, "enabled", lambda: False)

    item = _make_item("test-stuck-file", status="publishing")

    # In file mode:
    stuck = q.release_stuck_publishing(minutes=0)
    assert stuck == [item.id]
    # Post transitioned to failed for retry
    assert q.get(item.id).status == "failed"
    assert q.get(item.id).error == "Publishing was interrupted; it will be retried."
