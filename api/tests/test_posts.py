"""Posts API: grouping, filters, decisions, edits, publish-now/retry (publisher faked)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete

import pytest

from src import db
from src import queue_store as q
from src.db.models import Post

GROUP = "2026-09-27/prompt-injection"


def _item(id_, kind, version=1, status="pending", **kw) -> q.Item:
    media = ({"carousel": ["https://x/1.jpg", "https://x/2.jpg"]} if kind == "carousel"
             else {"reel": "https://x/reel.mp4", "cover": "https://x/c.jpg"})
    base = dict(id=id_, kind=kind, date="2026-09-27", topic="Understanding Prompt Injection", category="AI",
                post_dir=f"output/2026-09-27/prompt-injection/v{version}-{kind}", media=media,
                caption="Prompt injection hijacks AI. Here is how.\n\n#ai #security", version=version,
                status=status, publish_at="2026-09-27T19:00:00+05:30", tg_control_id=None)
    base.update(kw)
    return q.Item(**base)


@pytest.fixture(autouse=True)
def seed():
    with db.session() as s:
        s.execute(delete(Post))
    q.save([
        _item("c1", "carousel", 1, "replaced"), _item("r1", "reel", 1, "replaced"),
        _item("c2", "carousel", 2), _item("r2", "reel", 2),
        _item("x1", "reel", 1, "published", topic="Other topic", category="DSA", date="2026-09-20",
              post_dir="output/2026-09-20/other/", publish_at="2026-09-20T19:00:00+05:30",
              platforms={"ig": {"status": "published", "url": "https://ig/p/1"},
                         "yt": {"status": "failed", "error": "quota", "attempts": 3}}),
    ])


def groups(client, **params):
    r = client.get("/api/posts", params=params)
    assert r.status_code == 200, r.text
    return r.json()["groups"]


def test_requires_auth_and_csrf(client):
    assert client.get("/api/posts").status_code == 401
    client.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery"})
    assert client.get("/api/posts").status_code == 200
    assert client.post("/api/posts/c2/reject").status_code == 403  # no CSRF header


def test_groups_show_current_versions(authed):
    gs = groups(authed)
    assert [g["group_id"] for g in gs] == [GROUP, "2026-09-20/other"]
    g = gs[0]
    assert g["versions"] == 2 and g["items"]["carousel"]["id"] == "c2" and g["items"]["reel"]["id"] == "r2"
    reel = g["items"]["reel"]
    assert reel["targets"] == ["ig", "yt"] and reel["hashtags"] == ["#ai", "#security"]
    assert reel["youtube"]["title"].endswith("#Shorts") and not reel["youtube"]["title_is_custom"]
    assert "youtube" not in g["items"]["carousel"]


@pytest.mark.parametrize("params,expected", [
    ({"status": "pending"}, [GROUP]),
    ({"status": "published"}, ["2026-09-20/other"]),
    ({"category": "DSA"}, ["2026-09-20/other"]),
    ({"q": "injection"}, [GROUP]),
    ({"date_from": "2026-09-25"}, [GROUP]),
    ({"date_to": "2026-09-21"}, ["2026-09-20/other"]),
    ({"platform": "yt"}, [GROUP, "2026-09-20/other"]),
])
def test_filters(authed, params, expected):
    assert [g["group_id"] for g in groups(authed, **params)] == expected


def test_approve_with_selected_platforms(authed):
    r = authed.post("/api/posts/r2/approve", json={"targets": ["yt"]})
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["targets"] == ["yt"]
    assert q.get("r2").targets == ["yt"]


def test_approve_with_no_platforms_rejects(authed):
    r = authed.post("/api/posts/c2/approve", json={"targets": []})
    assert r.json()["status"] == "rejected" and r.json()["error"] == "no platforms selected"


def test_carousel_cannot_target_youtube(authed):
    assert authed.post("/api/posts/c2/approve", json={"targets": ["yt"]}).status_code == 409


def test_schedule(authed):
    assert authed.post("/api/posts/r2/schedule", json={"publish_at": "2026-10-01T10:30:00"}).status_code == 422
    r = authed.post("/api/posts/r2/schedule", json={"publish_at": "2026-10-01T05:00:00Z"})
    assert r.status_code == 200 and r.json()["publish_at"] == "2026-10-01T10:30:00+05:30"


def test_reject_and_no_double_decision(authed):
    assert authed.post("/api/posts/c2/reject").json()["status"] == "rejected"
    r = authed.post("/api/posts/c2/approve", json={})
    assert r.status_code == 409 and "already rejected" in r.json()["detail"]


def test_edit_caption_hashtags_and_youtube(authed):
    r = authed.patch("/api/posts/r2", json={"caption": "New hook. Body.", "hashtags": ["ai", "#Security", "ai"],
                                            "yt_title": "Custom title"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["caption"] == "New hook. Body." and out["hashtags"] == ["#ai", "#Security"]
    assert out["youtube"]["title"] == "Custom title #Shorts" and out["youtube"]["title_is_custom"]
    assert q.get("r2").caption == "New hook. Body.\n\n#ai #Security"
    back = authed.patch("/api/posts/r2", json={"yt_title": ""}).json()
    assert not back["youtube"]["title_is_custom"]


@pytest.mark.parametrize("body", [
    {"hashtags": ["not ok!"]},
    {"hashtags": [f"t{i}" for i in range(31)]},
    {"caption": "x" * 2190, "hashtags": ["#abcdefghij"]},
    {"caption": "   "},
])
def test_edit_validation(authed, body):
    assert authed.patch("/api/posts/r2", json=body).status_code == 409


def test_cannot_edit_published(authed):
    assert authed.patch("/api/posts/x1", json={"caption": "x"}).status_code == 409


def test_regenerate_both_formats(authed):
    r = authed.post("/api/posts/regenerate", json={"item_ids": ["c2", "r2"], "feedback": "Show the prompt"})
    assert r.status_code == 200
    assert {q.get(i).status for i in ("c2", "r2")} == {"regenerate"}
    assert q.get("r2").feedback == "Show the prompt"


def test_publish_now_runs_publisher(authed, monkeypatch):
    calls = []

    def fake_publish(item, dry_run=False, platforms=q.PLATFORMS):
        calls.append((item.id, item.status, platforms))
        item.status = "published"
        item.platforms = {p: {"status": "published", "url": f"https://{p}/x"} for p in item.effective_targets}
        q.upsert(item)
        return item

    monkeypatch.setattr("src.publish.publish_item", fake_publish)
    r = authed.post("/api/posts/r2/publish-now", json={"targets": ["ig"]})
    assert r.status_code == 200 and r.json()["status"] == "publishing"
    assert calls == [("r2", "publishing", q.PLATFORMS)]          # background task ran
    assert q.get("r2").status == "published" and q.get("r2").targets == ["ig"]


def test_publish_now_disabled(authed, monkeypatch):
    monkeypatch.setenv("PUBLISH_ENABLED", "false")
    r = authed.post("/api/posts/r2/publish-now", json={})
    assert r.status_code == 409 and "PUBLISH_ENABLED" in r.json()["detail"]
    assert q.get("r2").status == "pending"


def test_retry_only_failed_platform(authed, monkeypatch):
    calls = []
    monkeypatch.setattr("src.publish.publish_item",
                        lambda item, dry_run=False, platforms=q.PLATFORMS: calls.append(platforms) or item)
    assert authed.post("/api/posts/x1/retry", json={"platform": "ig"}).status_code == 409  # IG didn't fail
    r = authed.post("/api/posts/x1/retry", json={"platform": "yt"})
    assert r.status_code == 200 and calls == [("yt",)]


def test_publisher_crash_never_leaves_item_stuck(authed, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr("src.publish.publish_item", boom)
    authed.post("/api/posts/r2/publish-now", json={})
    assert q.get("r2").status == "failed" and "network down" in q.get("r2").error


def test_detail_has_history(authed):
    d = authed.get("/api/posts/r2").json()
    assert d["item"]["id"] == "r2" and [h["version"] for h in d["history"]] == [1, 2]
    assert authed.get("/api/posts/nope").status_code == 404


def test_sync_telegram_respects_switch(authed):
    assert authed.post("/api/posts/sync-telegram").json() == {"enabled": False, "changes": []}


# --- PUBLISH_VIA=dispatch (AWS Lambda): the API never publishes itself --------------------------
@pytest.fixture
def dispatch(monkeypatch):
    monkeypatch.setenv("PUBLISH_VIA", "dispatch")
    kicks = []
    monkeypatch.setattr("src.actions.trigger_pipeline_run", lambda *a, **k: kicks.append(1) or True)
    monkeypatch.setattr("src.publish.publish_item",
                        lambda *a, **k: pytest.fail("the API must not publish in dispatch mode"))
    return kicks


def test_dispatch_publish_now_approves_and_kicks_poll(authed, dispatch):
    r = authed.post("/api/posts/r2/publish-now", json={"targets": ["ig"]})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    item = q.get("r2")
    assert item.status == "approved" and item.targets == ["ig"] and dispatch == [1]
    assert datetime.fromisoformat(item.publish_at) <= datetime.now(timezone.utc)  # due immediately


def test_dispatch_retry_resets_attempts_and_kicks_poll(authed, dispatch):
    r = authed.post("/api/posts/x1/retry", json={"platform": "yt"})
    assert r.status_code == 200 and r.json()["status"] == "failed" and dispatch == [1]
    assert q.get("x1").platforms["yt"]["attempts"] == 0
    from src.publish import _retryable
    assert _retryable(q.get("x1"), q.PLATFORMS)  # so the poll job will pick it up


def test_dispatch_publish_now_still_blocked_when_disabled(authed, dispatch, monkeypatch):
    monkeypatch.setenv("PUBLISH_ENABLED", "false")
    assert authed.post("/api/posts/r2/publish-now", json={}).status_code == 409
    assert dispatch == [] and q.get("r2").status == "pending"


# --- expired posts can be scheduled again ---------------------------------------------------------
@pytest.fixture
def expired():
    q.save([_item("e1", "carousel", 1, "expired", date="2026-10-02", post_dir="output/2026-10-02/old/",
                  publish_at="2026-10-02T10:00:00+05:30")])


def test_expired_post_can_be_scheduled(authed, expired):
    assert authed.get("/api/posts/e1").json()["item"]["can"]["approve"] is True
    when = "2026-10-06T19:00:00+05:30"
    r = authed.post("/api/posts/e1/schedule", json={"publish_at": when})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    item = q.get("e1")
    assert item.status == "approved" and item.decided_at
    assert datetime.fromisoformat(item.publish_at) == datetime.fromisoformat(when)


def test_expired_post_can_be_approved_again_and_edited(authed, expired):
    assert authed.patch("/api/posts/e1", json={"caption": "Fixed caption #ai"}).status_code == 200
    assert authed.post("/api/posts/e1/approve", json={}).status_code == 200
    assert q.get("e1").status == "approved" and q.get("e1").caption.startswith("Fixed caption")


def test_expired_post_still_cannot_be_rejected_or_published_directly(authed, expired):
    assert authed.post("/api/posts/e1/reject").status_code == 409
    from src.publish import publish_item
    with pytest.raises(PermissionError):
        publish_item(q.get("e1"))  # only approved items publish; reviving goes through approve first


def test_revived_post_is_not_expired_again(expired):
    import main
    from datetime import timedelta
    old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
    item = q.get("e1"); item.created_at = old; item.status = "approved"; q.upsert(item)
    main.expire_stale(dry_run=False)
    assert q.get("e1").status == "approved"
