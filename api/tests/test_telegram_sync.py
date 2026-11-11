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


def test_item_carries_owner_and_never_nulls_it(telegram):
    item = q.get("c")
    assert item.user_id == 1  # column default; send_preview/publish read item.user_id
    item.user_id = None
    q.save([item])
    assert q.get("c").user_id == 1


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


def test_reel_control_text_never_exceeds_telegram_video_caption_limit():
    huge_feedback = "Please remake with new style and designs! " * 20
    huge_caption = "Long technical caption with lots of quotes 'and' & ampersands <tags> here. " * 30
    item = _item("20261025-r-4a770b", "reel", version=2, feedback=huge_feedback, voice="en-US-EmmaNeural")
    item.caption = huge_caption
    text = approve_bot._control_text(item)
    assert len(text) <= 1024
    assert len(text) <= 1020


def test_preview_says_hinglish_only_for_hinglish_reels():
    reel = _item("r-hi", "reel", voice="hi-IN-SwaraNeural", language="hi")
    assert "Narration: Hinglish" in approve_bot._control_text(reel) and "Voice: Swara" in approve_bot._control_text(reel)
    assert "Hinglish" not in approve_bot._control_text(_item("r-en", "reel", voice="en-US-EmmaNeural"))
    assert "Hinglish" not in approve_bot._control_text(_item("c-hi", "carousel", language="hi"))


def test_find_start_chat_matches_only_exact_nonce(monkeypatch):
    from src.verify import telegram as tg
    tok = "111:tokentokentokentokentok"
    updates = [
        {"update_id": 1, "message": {"text": "/start wrong-nonce", "chat": {"id": 999, "type": "private", "first_name": "Evil"}}},
        {"update_id": 2, "message": {"text": "/start right-nonce-123", "chat": {"id": 777, "type": "private", "first_name": "Ana"}}},
    ]

    def fake_call(t, method, **kw):
        assert t == tok
        if method == "getWebhookInfo":
            return {"url": ""}, None
        if method == "getUpdates":
            return updates, None
        raise AssertionError(method)

    monkeypatch.setattr(tg, "_call", fake_call)
    chat, err = approve_bot.find_start_chat(tok, "right-nonce-123")
    assert err is None and chat == {"id": "777", "type": "private", "title": "Ana"}
    none_chat, err2 = approve_bot.find_start_chat(tok, "missing-nonce")
    assert err2 is None and none_chat is None


def test_1click_telegram_connect_unlink_change_bot_and_isolation(client, monkeypatch):
    import uuid
    from api.app.routes import integrations as int_route
    from api.app.security import hash_password
    from src import config_store, user_config_store
    from src.db.models import User, UserConfigValue
    from src.verify import telegram as tg

    int_route.limiter._hits.clear()
    key = config_store.generate_master_key()
    monkeypatch.setenv("CONFIG_MASTER_KEY", key)
    config_store._dek_cache.clear()
    config_store.invalidate()

    default_bot = "111:defaultbottokentokentoken"
    custom_bot = "222:custombottokentokentoken1"
    monkeypatch.setenv("TG_BOT_TOKEN", default_bot)

    with db.session() as s:
        u1 = User(username=f"tg1_{uuid.uuid4().hex[:6]}", email=f"tg1_{uuid.uuid4().hex[:6]}@example.com",
                  password_hash=hash_password("password123"), role="client", is_active=True)
        u2 = User(username=f"tg2_{uuid.uuid4().hex[:6]}", email=f"tg2_{uuid.uuid4().hex[:6]}@example.com",
                  password_hash=hash_password("password123"), role="client", is_active=True)
        s.add_all([u1, u2])
        s.flush()
        u1_id, u2_id = u1.id, u2.id

    def login_as(uname):
        r = client.post("/api/auth/login", json={"username": uname, "password": "password123"})
        assert r.status_code == 200
        client.headers["X-CSRF-Token"] = r.json()["csrf"]

    updates_by_bot: dict[str, list[dict]] = {default_bot: [], custom_bot: []}

    def fake_call(tok, method, **kw):
        if method == "getMe":
            return {"username": "MintlyDefaultBot" if tok == default_bot else "UserCustomBot"}, None
        if method == "getWebhookInfo":
            return {"url": ""}, None
        if method == "getUpdates":
            return updates_by_bot.get(tok, []), None
        return None, "telegram.unavailable"

    monkeypatch.setattr(tg, "_call", fake_call)

    try:
        # User 1 starts 1-click link using Mintly's default bot
        login_as(u1.username)
        link1 = client.post("/api/integrations/telegram/link").json()
        assert link1["url"].startswith("https://t.me/MintlyDefaultBot?start=")
        nonce1 = link1["url"].split("start=")[1]

        # User 2 cannot confirm using User 1's /start <nonce>
        login_as(u2.username)
        link2 = client.post("/api/integrations/telegram/link").json()
        nonce2 = link2["url"].split("start=")[1]
        assert nonce1 != nonce2
        updates_by_bot[default_bot].append(
            {"update_id": 10, "message": {"text": f"/start {nonce1}", "chat": {"id": 55501, "type": "private", "first_name": "U1"}}}
        )
        assert client.post("/api/integrations/telegram/confirm").json() == {"connected": False}
        assert user_config_store.lookup("TG_CHAT_ID", u2_id) is None

        # User 1 confirms -> TG_CHAT_ID bound strictly to u1_id
        login_as(u1.username)
        conf1 = client.post("/api/integrations/telegram/confirm").json()
        assert conf1["connected"] is True and conf1["chat_id"] == "55501"
        assert user_config_store.lookup("TG_CHAT_ID", u1_id) == "55501"
        assert user_config_store.lookup("TG_CHAT_ID", u2_id) is None
        # Nonce is single-use
        assert client.post("/api/integrations/telegram/confirm").status_code == 404

        # User 1 switches to custom bot ("Change Bot"), full token never echoed
        bad_bot = client.put("/api/integrations/telegram/bot", json={"token": "not-a-token"})
        assert bad_bot.status_code == 422
        ok_bot = client.put("/api/integrations/telegram/bot", json={"token": custom_bot})
        assert ok_bot.status_code == 200 and ok_bot.json()["bot_username"] == "@UserCustomBot"
        assert custom_bot not in ok_bot.text
        st = client.get("/api/integrations").json()
        assert st["telegram"]["using_custom_bot"] is True and custom_bot not in repr(st)

        # New 1-click link uses User 1's custom bot, while User 2 still uses Mintly's default bot
        link_custom = client.post("/api/integrations/telegram/link").json()
        assert link_custom["url"].startswith("https://t.me/UserCustomBot?start=")
        assert link_custom["using_custom_bot"] is True
        login_as(u2.username)
        link_u2 = client.post("/api/integrations/telegram/link").json()
        assert link_u2["url"].startswith("https://t.me/MintlyDefaultBot?start=")

        # Unlink TG for User 1 (keeps custom bot unless include_bot=true, then reset bot)
        login_as(u1.username)
        assert client.delete("/api/integrations/telegram").status_code == 204
        assert user_config_store.lookup("TG_CHAT_ID", u1_id) is None
        assert user_config_store.lookup("TG_BOT_TOKEN", u1_id) == custom_bot
        assert client.delete("/api/integrations/TG_BOT_TOKEN").status_code == 204
        assert user_config_store.lookup("TG_BOT_TOKEN", u1_id) is None
    finally:
        with db.session() as s:
            s.execute(delete(UserConfigValue).where(UserConfigValue.user_id.in_([u1_id, u2_id])))
            s.execute(delete(Setting).where(Setting.key.in_([f"tg_link:{u1_id}", f"tg_link:{u2_id}"])))
            s.execute(delete(User).where(User.id.in_([u1_id, u2_id])))
        user_config_store.invalidate(u1_id)
        user_config_store.invalidate(u2_id)
        config_store._dek_cache.clear()
        config_store.invalidate()
