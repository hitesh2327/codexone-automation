"""Telegram poll <-> dashboard consistency, with a fake Telegram bot."""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from sqlalchemy import delete

from src import approve_bot, db
from src import queue_store as q
from src.db.models import Post, Setting

CHAT = 4242


def _item(id_, kind, status="pending", **kw):
    return q.Item(id=id_, kind=kind, date="2026-09-28", topic="T", category="AI",
                  post_dir="output/2026-09-28/t", caption="c\n\n#x", status=status,
                  tg_message_ids=[10 if kind == "carousel" else 20], tg_control_id=10 if kind == "carousel" else 20,
                  **kw)


class FakeBot:
    def __init__(self, updates):
        self.updates, self.calls = updates, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get_updates(self, offset=None, **kw):
        return [u for u in self.updates if offset is None or u.update_id >= offset]

    def __getattr__(self, name):  # answer_callback_query, send_message, edit_message_* ...
        async def record(*a, **k):
            self.calls.append(name)
        return record


def tap(update_id, data, message_id):
    return NS(update_id=update_id, message=None,
              callback_query=NS(id=f"cb{update_id}", data=data, message=NS(chat=NS(id=CHAT), message_id=message_id)))


@pytest.fixture()
def telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_SYNC", "true")
    monkeypatch.setenv("TG_CHAT_ID", str(CHAT))
    with db.session() as s:
        s.execute(delete(Post))
        s.execute(delete(Setting).where(Setting.key == "tg_offset"))
    q.save([_item("c", "carousel"), _item("r", "reel")])

    def install(updates):
        bot = FakeBot(updates)
        monkeypatch.setattr(approve_bot, "_bot", lambda: bot)
        return bot
    return install


def test_telegram_approve_updates_db_and_offset(telegram):
    telegram([tap(100, "approve:r", 20)])
    assert approve_bot.poll() == [("r", "approved")]
    assert q.get("r").status == "approved" and q.get("c").status == "pending"
    assert db.get_setting("tg_offset") == {"offset": 101}
    assert approve_bot.poll() == []  # the same tap is not applied twice


def test_poll_does_not_overwrite_concurrent_dashboard_edits(telegram, monkeypatch):
    telegram([tap(200, "approve:r", 20)])
    real_load = q.load

    def load_then_dashboard_edits():
        items = real_load()           # the poll's snapshot...
        c = q.get("c")                # ...then the dashboard edits the carousel meanwhile
        c.caption = "edited in dashboard\n\n#x"
        q.upsert(c)
        return items
    monkeypatch.setattr(q, "load", load_then_dashboard_edits)
    approve_bot.poll()
    monkeypatch.setattr(q, "load", real_load)
    assert q.get("r").status == "approved"
    assert q.get("c").caption == "edited in dashboard\n\n#x"   # not reverted by the poll


def test_tap_after_dashboard_decision_is_ignored(telegram):
    r = q.get("r")
    q.apply_decision(r, "reject")
    q.upsert(r)
    bot = telegram([tap(300, "approve:r", 20)])
    assert approve_bot.poll() == []
    assert q.get("r").status == "rejected" and "answer_callback_query" in bot.calls


def test_dashboard_decision_updates_telegram(telegram):
    from src import actions
    bot = telegram([])
    actions.approve("c", targets=["ig"])
    assert "edit_message_reply_markup" in bot.calls and "send_message" in bot.calls
