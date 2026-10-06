"""Activity log: the recording helper, the read-only /api/logs API, and that real actions write rows."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from src import activity, db
from src import queue_store as q
from src.db.models import ActivityLog, Post


def _wipe():
    with db.session() as s:
        s.execute(delete(ActivityLog))
        s.execute(delete(Post))


@pytest.fixture(autouse=True)
def clean():
    _wipe()


def _add(event="post.approved", level="info", source="dashboard", message="m", post_id=None, ago_h=0.0, actor=None):
    with db.session() as s:
        s.add(ActivityLog(event=event, level=level, source=source, message=message, post_id=post_id, actor=actor,
                          created_at=datetime.now(timezone.utc) - timedelta(hours=ago_h)))


def test_record_writes_and_never_raises(monkeypatch):
    activity.record("x.test", "hello", source="pipeline", post_id="p1", detail={"a": 1})
    with db.session() as s:
        row = s.scalars(select(ActivityLog)).one()
    assert (row.event, row.level, row.source, row.post_id, row.detail) == ("x.test", "info", "pipeline", "p1", {"a": 1})

    activity.record("x.bad", "m", level="nonsense")  # unknown level is coerced
    with db.session() as s:
        assert s.scalars(select(ActivityLog).where(ActivityLog.event == "x.bad")).one().level == "info"

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "session", boom)
    activity.record("x.fail", "m")  # must not raise
    monkeypatch.setattr(db, "enabled", lambda: False)
    activity.record("x.nodb", "m")  # file mode: no-op
    assert activity.prune() == 0


def test_prune_removes_only_old_rows():
    _add(message="old", ago_h=24 * 100)
    _add(message="new")
    assert activity.prune() == 1
    with db.session() as s:
        assert [r.message for r in s.scalars(select(ActivityLog))] == ["new"]


def test_requires_auth_and_is_read_only(client):
    assert client.get("/api/logs").status_code == 401
    assert client.get("/api/logs/summary").status_code == 401


def test_filters_pagination_facets(authed):
    _wipe()  # the sign-in itself logged a row
    _add("post.approved", source="dashboard", message="Approved reel Alpha", post_id="a")
    _add("post.published", source="publisher", message="Published Alpha", post_id="a")
    _add("publish.failed", "error", "publisher", "IG failed for Beta_100%", post_id="b")
    _add("login.failed", "warning", "auth", "Failed sign-in", actor="admin")
    _add("post.approved", source="telegram", message="old one", ago_h=24 * 5)

    def get(**p):
        r = authed.get("/api/logs", params=p)
        assert r.status_code == 200, r.text
        return r.json()

    body = get()
    assert len(body["items"]) == 5
    assert [i["id"] for i in body["items"]] == sorted((i["id"] for i in body["items"]), reverse=True)
    assert body["facets"]["level"] == {"info": 3, "error": 1, "warning": 1}
    assert get(level="error")["items"][0]["event"] == "publish.failed"
    assert {i["event"] for i in get(level=["error", "warning"])["items"]} == {"publish.failed", "login.failed"}
    # a facet ignores its own filter, so chips show what choosing them would give
    assert get(level="error")["facets"]["level"]["info"] == 3
    assert get(level="error")["facets"]["source"] == {"publisher": 1}
    assert len(get(source="publisher")["items"]) == 2
    assert len(get(event="post.")["items"]) == 3
    assert len(get(post_id="a")["items"]) == 2
    assert len(get(q="alpha")["items"]) == 2
    assert [i["post_id"] for i in get(q="Beta_100%")["items"]] == ["b"]  # LIKE wildcards are literal
    assert get(q="Beta_1")["items"][0]["post_id"] == "b" and not get(q="Beta%1")["items"]
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
    assert len(get(date_from=today)["items"]) == 4
    assert len(get(date_to=(datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat())["items"]) == 1

    page1 = get(limit=2)
    assert len(page1["items"]) == 2 and page1["next_before_id"] == page1["items"][-1]["id"]
    page2 = get(limit=2, before_id=page1["next_before_id"])
    page3 = get(limit=2, before_id=page2["next_before_id"])
    assert len(page3["items"]) == 1 and page3["next_before_id"] is None
    ids = [i["id"] for p in (page1, page2, page3) for i in p["items"]]
    assert len(set(ids)) == 5
    assert authed.get("/api/logs", params={"limit": 501}).status_code == 422
    assert body["items"][0]["created_at"].endswith("Z")
    assert authed.delete("/api/logs/1").status_code in (404, 405)


def test_summary(authed):
    _wipe()
    _add("publish.failed", "error", "publisher", "old failure", ago_h=30)
    _add("publish.failed", "error", "publisher", "recent failure", ago_h=1)
    _add("post.published", source="publisher", message="Published", post_id="a", ago_h=2)
    _add("login.failed", "warning", "auth")
    r = authed.get("/api/logs/summary").json()
    assert r["last_24h"] == {"info": 1, "warning": 1, "error": 1}
    assert r["last_error"]["message"] == "recent failure"
    assert r["last_publish"]["post_id"] == "a"
    with db.session() as s:
        s.execute(delete(ActivityLog))
    r = authed.get("/api/logs/summary").json()
    assert r["last_error"] is None and r["last_publish"] is None


def test_login_and_approve_write_rows(client):
    client.post("/api/auth/login", json={"username": "admin", "password": "wrong password!"})
    r = client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery"})
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    q.save([q.Item(id="lg1", kind="reel", date="2026-09-27", topic="Logged topic", category="AI",
                   post_dir="output/2026-09-27/logged/v1-reel", media={"reel": "https://x/r.mp4"},
                   caption="c\n\n#ai", version=1, status="pending", publish_at="2026-09-27T19:00:00+05:30",
                   tg_control_id=None)])
    assert client.post("/api/posts/lg1/approve", json={}).status_code == 200
    rows = client.get("/api/logs").json()["items"]
    events = [i["event"] for i in rows]
    assert {"login.failed", "login.success", "post.approved"} <= set(events)
    ap = next(i for i in rows if i["event"] == "post.approved")
    assert ap["post_id"] == "lg1" and ap["source"] == "dashboard" and "Logged topic" in ap["message"]
    blob = str(rows)
    assert "wrong password" not in blob and "correct horse" not in blob
