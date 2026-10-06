"""The public brand endpoint: presentation fields only, plus the posting slot times the login page shows."""
from __future__ import annotations

from api.app.routes import public


def test_brand_exposes_slot_times_from_config(client):
    r = client.get("/api/public/brand")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"handle", "colors", "fonts", "post_times_ist"}
    times = body["post_times_ist"]
    assert times and times == sorted(times)
    assert all(len(t) == 5 and t[2] == ":" for t in times)


def test_brand_slot_times_follow_the_config(client, monkeypatch):
    monkeypatch.setattr(public, "load_brand", lambda: {"handle": "@x", "post_times_ist": ["19:30", "9:05", "bad", "25:00", "19:30"]})
    assert client.get("/api/public/brand").json()["post_times_ist"] == ["09:05", "19:30"]


def test_brand_legacy_single_slot_and_missing(client, monkeypatch):
    monkeypatch.setattr(public, "load_brand", lambda: {"post_time_ist": "18:00"})
    assert client.get("/api/public/brand").json()["post_times_ist"] == ["18:00"]
    monkeypatch.setattr(public, "load_brand", lambda: {})
    assert client.get("/api/public/brand").json()["post_times_ist"] == []
