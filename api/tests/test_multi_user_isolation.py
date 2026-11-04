"""Multi-user data isolation tests:
Verify that each user only sees their own posts, dashboard, generation slots/jobs,
activity logs, and that client users are blocked from global config.
"""
from __future__ import annotations

from datetime import datetime, timezone
import pytest
from sqlalchemy import delete

from src import activity, db, generation
from src import queue_store as q
from src.db.models import ActivityLog, GenerationJob, Post, User
from api.app.security import hash_password


def _item(id_, user_id, kind="carousel", version=1, status="pending", **kw) -> q.Item:
    media = ({"carousel": ["https://x/1.jpg"]} if kind == "carousel"
             else {"reel": "https://x/reel.mp4", "cover": "https://x/c.jpg"})
    base = dict(id=id_, kind=kind, date="2026-10-15", topic=f"Topic for {id_}", category="AI",
                post_dir=f"output/2026-10-15/{id_}/v{version}-{kind}", media=media,
                caption=f"Caption for {id_}\n\n#test", version=version,
                status=status, publish_at="2026-10-15T18:00:00+05:30", tg_control_id=None,
                user_id=user_id)
    base.update(kw)
    return q.Item(**base)


def _create_user(username: str, email: str, role: str = "client") -> int:
    with db.session() as s:
        user = User(
            username=username,
            email=email,
            name=username.capitalize(),
            password_hash=hash_password("password123"),
            role=role,
            is_active=True,
            subscription_tier="pro",
            subscription_status="active",
        )
        s.add(user)
        s.flush()
        return user.id


def _login(client, username: str) -> None:
    r = client.post("/api/auth/login", json={"username": username, "password": "password123"})
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf"]


def test_signup_creates_client_role(client):
    r = client.post("/api/auth/signup", json={
        "username": "newclient",
        "email": "newclient@example.com",
        "password": "Password123!",
        "name": "New Client",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["role"] == "client"

    # /api/auth/me also returns role="client"
    client.headers["X-CSRF-Token"] = data["csrf"]
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "client"


def test_posts_isolation_between_users(client):
    u1_id = _create_user("user_one", "user1@example.com", role="client")
    u2_id = _create_user("user_two", "user2@example.com", role="client")

    q.save([
        _item("post-u1", user_id=u1_id),
        _item("post-u2", user_id=u2_id),
    ])

    # User 1 lists posts
    _login(client, "user_one")
    r1 = client.get("/api/posts")
    assert r1.status_code == 200
    groups1 = r1.json()["groups"]
    assert len(groups1) == 1
    assert groups1[0]["items"]["carousel"]["id"] == "post-u1"

    # User 1 cannot view User 2's post directly
    assert client.get("/api/posts/post-u2").status_code == 404

    # User 1 cannot modify User 2's post
    assert client.post("/api/posts/post-u2/approve", json={"targets": ["ig"]}).status_code == 404
    assert client.patch("/api/posts/post-u2", json={"caption": "Hacked"}).status_code == 404
    assert client.post("/api/posts/post-u2/reject").status_code == 404
    assert client.post("/api/posts/regenerate", json={"item_ids": ["post-u2"]}).status_code == 404

    # User 2 lists posts
    _login(client, "user_two")
    r2 = client.get("/api/posts")
    assert r2.status_code == 200
    groups2 = r2.json()["groups"]
    assert len(groups2) == 1
    assert groups2[0]["items"]["carousel"]["id"] == "post-u2"

    # User 2 cannot view User 1's post
    assert client.get("/api/posts/post-u1").status_code == 404


def test_dashboard_isolation_and_cache_partitioning(client):
    u1_id = _create_user("dash_one", "dash1@example.com", role="client")
    u2_id = _create_user("dash_two", "dash2@example.com", role="client")

    q.save([
        _item("p1", user_id=u1_id, status="published",
              platforms={"ig": {"status": "published", "url": "https://ig/1"}}),
        _item("p2", user_id=u2_id, status="pending"),
    ])

    # User 1 visits dashboard
    _login(client, "dash_one")
    d1 = client.get("/api/dashboard/overview?range=30&workspace=live")
    assert d1.status_code == 200
    res1 = d1.json()
    assert len(res1["recent_posts"]["items"]) == 1
    assert res1["recent_posts"]["items"][0]["topic"] == "Topic for p1"

    # Immediately (cache window), User 2 visits dashboard
    _login(client, "dash_two")
    d2 = client.get("/api/dashboard/overview?range=30&workspace=live")
    assert d2.status_code == 200
    res2 = d2.json()
    # User 2 has no published posts, so recent_posts items should be 0
    assert len(res2["recent_posts"]["items"]) == 0


def test_generate_slots_and_jobs_isolation(client):
    u1_id = _create_user("gen_one", "gen1@example.com", role="client")
    u2_id = _create_user("gen_two", "gen2@example.com", role="client")

    slot_dt = datetime.now(timezone.utc).replace(hour=12, minute=30, second=0, microsecond=0)

    # User 1 creates a job and post for this slot
    j1 = generation.create(trigger="dashboard", user_id=u1_id, slot_at=slot_dt, status="running")
    q.save([_item("gen-post-1", user_id=u1_id, publish_at=slot_dt.isoformat())])

    # User 2 lists jobs
    _login(client, "gen_two")
    jobs_resp = client.get("/api/generate/jobs")
    assert jobs_resp.status_code == 200
    # User 2 shouldn't see User 1's active job
    assert jobs_resp.json()["active"] is None
    assert len(jobs_resp.json()["jobs"]) == 0

    # User 2 cannot inspect User 1's job
    assert client.get(f"/api/generate/jobs/{j1['id']}").status_code == 404

    # User 1 lists jobs
    _login(client, "gen_one")
    j1_resp = client.get("/api/generate/jobs")
    assert j1_resp.status_code == 200
    assert j1_resp.json()["active"] is not None
    assert j1_resp.json()["active"]["id"] == j1["id"]


def test_activity_logs_isolation(client):
    u1_id = _create_user("log_one", "log1@example.com", role="client")
    u2_id = _create_user("log_two", "log2@example.com", role="client")

    with db.session() as s:
        s.add(ActivityLog(event="test.user1", message="Secret user 1 log", source="test", user_id=u1_id))
        s.add(ActivityLog(event="test.user2", message="Secret user 2 log", source="test", user_id=u2_id))

    # User 1 sees only user 1 logs
    _login(client, "log_one")
    r1 = client.get("/api/logs")
    assert r1.status_code == 200
    messages1 = [item["message"] for item in r1.json()["items"]]
    assert "Secret user 1 log" in messages1
    assert "Secret user 2 log" not in messages1

    # User 2 sees only user 2 logs
    _login(client, "log_two")
    r2 = client.get("/api/logs")
    assert r2.status_code == 200
    messages2 = [item["message"] for item in r2.json()["items"]]
    assert "Secret user 2 log" in messages2
    assert "Secret user 1 log" not in messages2


def test_client_cannot_access_global_config(client):
    _create_user("regular_client", "regclient@example.com", role="client")

    _login(client, "regular_client")
    # Client is blocked from /api/config
    r = client.get("/api/config")
    assert r.status_code == 403

    # Client CAN access /api/integrations
    r_integ = client.get("/api/integrations")
    assert r_integ.status_code == 200
