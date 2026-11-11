"""Tests for Dynamic Per-User Categories, Tenant-Scoped Dedupe, Niche Source Routing, and SSRF Hardening."""
from __future__ import annotations

import socket
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.app import ratelimit  # noqa: E402
from api.app.main import create_app  # noqa: E402
from api.app.routes.generate import GenerateBody  # noqa: E402
from src import db, fetch_topics, gen_content, rank_topics, user_taste  # noqa: E402
from src import queue_store as q  # noqa: E402
from src.db.models import Base, GenerationJob, Post, PostedTopic, User  # noqa: E402
from src.reel_v2 import spec as reel_spec  # noqa: E402


def _fake_public_dns(ip: str = "93.184.216.34"):
    return lambda host, port, *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
    ]


@pytest.fixture(autouse=True)
def _reset_taste_cache():
    user_taste._CACHE.clear()
    yield
    user_taste._CACHE.clear()


# --------------------------------------------------------------------------- #
# 1. SSRF-hardened feed URL validation & RSS/Atom/Substack parsing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_url", [
    "http://example.com/feed.xml",
    "file:///etc/passwd",
    "ftp://example.com/feed.xml",
    "javascript:alert(1)",
    "https://user:pass@example.com/feed.xml",
    "https://127.0.0.1/feed.xml",
    "https://127.0.1.1/feed.xml",
    "https://169.254.169.254/latest/meta-data",
    "https://10.0.0.5/rss",
    "https://172.16.0.1/rss",
    "https://192.168.1.1/rss",
    "https://0.0.0.0/rss",
    "https://[::1]/feed.xml",
    "https://[fc00::1]/feed.xml",
    "https://[::ffff:127.0.0.1]/feed.xml",
    "https://localhost/feed.xml",
    "https://metadata.internal/feed.xml",
    "https://example.com:8080/feed.xml",
])
def test_ssrf_blocks_unsafe_urls(bad_url):
    with pytest.raises(ValueError):
        fetch_topics.validate_safe_feed_url(bad_url)


@pytest.mark.parametrize("resolved_ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "172.16.4.2", "192.168.0.10", "::1"])
def test_ssrf_blocks_dns_resolving_to_private_ip(monkeypatch, resolved_ip):
    monkeypatch.setattr(fetch_topics.socket, "getaddrinfo", _fake_public_dns(resolved_ip))
    with pytest.raises(ValueError, match="blocked private"):
        fetch_topics.validate_safe_feed_url("https://evil-rebind.example.com/feed.xml")


def test_ssrf_blocks_redirect_to_private_target(monkeypatch):
    monkeypatch.setattr(fetch_topics.socket, "getaddrinfo", _fake_public_dns("93.184.216.34"))

    class FakeSess:
        def get(self, url, **kwargs):
            assert kwargs.get("allow_redirects") is False
            return SimpleNamespace(
                status_code=302,
                headers={"Location": "http://169.254.169.254/latest/meta-data"},
                close=lambda: None,
            )

    with pytest.raises(ValueError, match="https://"):
        fetch_topics.fetch_rss(FakeSess(), "https://public.example.com/feed.xml")


def test_ssrf_blocks_oversized_feed_over_1mb(monkeypatch):
    monkeypatch.setattr(fetch_topics.socket, "getaddrinfo", _fake_public_dns("93.184.216.34"))

    class FakeBigSess:
        def get(self, url, **kwargs):
            return SimpleNamespace(
                status_code=200,
                headers={},
                iter_content=lambda chunk_size=16384: [b"x" * (600 * 1024), b"y" * (600 * 1024)],
                raise_for_status=lambda: None,
                close=lambda: None,
            )

    with pytest.raises(ValueError, match="1 MB"):
        fetch_topics.fetch_rss(FakeBigSess(), "https://public.example.com/huge.xml")


def test_substack_normalization_and_rss_atom_parsing(monkeypatch):
    monkeypatch.setattr(fetch_topics.socket, "getaddrinfo", _fake_public_dns("93.184.216.34"))
    assert fetch_topics.validate_safe_feed_url("https://stronger.substack.com") == "https://stronger.substack.com/feed"

    rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Fitness</title>
      <item><title>Progressive Overload Basics</title><link>https://fit.example.com/1</link><description>&lt;p&gt;Track volume.&lt;/p&gt;</description><pubDate>Mon, 10 Nov 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    atom_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Feed</title>
      <entry><title>Protein Timing Myth</title><link rel="alternate" href="https://fit.example.com/2"/><summary>Daily intake matters most.</summary><updated>2026-11-11T08:00:00Z</updated></entry>
    </feed>"""

    rss_topics = fetch_topics.parse_feed_xml(rss_xml, source_label="rss/fit", pinned_category="Hypertrophy")
    assert len(rss_topics) == 1
    assert rss_topics[0].title == "Progressive Overload Basics"
    assert rss_topics[0].category == "Hypertrophy"
    assert rss_topics[0].summary == "Track volume."

    atom_topics = fetch_topics.parse_feed_xml(atom_xml, source_label="rss/atom")
    assert len(atom_topics) == 1
    assert atom_topics[0].url == "https://fit.example.com/2"
    assert atom_topics[0].title == "Protein Timing Myth"


# --------------------------------------------------------------------------- #
# 2. Tenant-isolated PostedTopic dedupe & 64-char category columns
# --------------------------------------------------------------------------- #
def test_posted_topic_tenant_isolation_and_64_char_categories(monkeypatch):
    Base.metadata.create_all(db.engine())
    monkeypatch.setattr(db, "enabled", lambda: True)
    tag = uuid.uuid4().hex[:8]
    long_cat = "Personal Finance & Tax Optimization Hacks for Freelancers 2026"
    assert len(long_cat) == 62

    with db.session() as s:
        u_a = User(username=f"alice_{tag}", name="Alice", role="client")
        u_b = User(username=f"bob_{tag}", name="Bob", role="client")
        s.add_all([u_a, u_b])
        s.flush()
        uid_a, uid_b = u_a.id, u_b.id

    try:
        item_a = q.Item(
            id=f"item-a-{tag}",
            kind="reel",
            date="2026-11-11",
            topic="S&P 500 Index Funds Explained",
            category=long_cat,
            source_url="https://finance.example.com/sp500",
            post_dir="output/2026-11-11/sp500",
            caption="Save this.",
            user_id=uid_a,
        )
        q.upsert(item_a)
        q.record_posted(item_a)

        with db.session() as s:
            job = GenerationJob(
                id=f"job{tag[:6]}",
                trigger="dashboard",
                user_id=uid_a,
                category=long_cat,
                topic_category=long_cat,
                status="succeeded",
            )
            s.add(job)
            s.flush()

        # User A's posted URL & title block User A, NOT User B!
        urls_a, titles_a = fetch_topics.load_posted(user_id=uid_a)
        urls_b, titles_b = fetch_topics.load_posted(user_id=uid_b)
        assert "sp 500 index funds explained" in titles_a
        assert "sp 500 index funds explained" not in titles_b
        assert "//finance.example.com/sp500" in urls_a
        assert "//finance.example.com/sp500" not in urls_b

        cand = [fetch_topics.Topic(title="S&P 500 Index Funds Explained", url="https://finance.example.com/sp500", source="reddit", score=100)]
        assert fetch_topics.dedupe(cand, user_id=uid_a) == []
        assert len(fetch_topics.dedupe(cand, user_id=uid_b)) == 1

        # Backwards compatibility: user_id=None sees all rows
        _, all_titles = fetch_topics.load_posted(user_id=None)
        assert "sp 500 index funds explained" in all_titles

        # rank_topics.recent_titles is also tenant-scoped
        assert "S&P 500 Index Funds Explained" in rank_topics.recent_titles(user_id=uid_a)
        assert "S&P 500 Index Funds Explained" not in rank_topics.recent_titles(user_id=uid_b)
    finally:
        with db.session() as s:
            s.execute(delete(GenerationJob).where(GenerationJob.user_id.in_([uid_a, uid_b])))
            s.execute(delete(PostedTopic).where(PostedTopic.user_id.in_([uid_a, uid_b])))
            s.execute(delete(Post).where(Post.user_id.in_([uid_a, uid_b])))
            s.execute(delete(User).where(User.id.in_([uid_a, uid_b])))


# --------------------------------------------------------------------------- #
# 3. Non-tech niche source routing
# --------------------------------------------------------------------------- #
def test_nontech_niche_skips_tech_feeds_and_routes_custom_sources(monkeypatch):
    fitness_taste = user_taste.UserTaste(
        niche="Fitness & Workout",
        tone="Punchy",
        content_type="Educational & How-To",
        aesthetic="Vibrant",
        template_style="Minimal Clean",
        target_audience="Gym beginners",
        prompt_instructions="",
        categories=["Hypertrophy", "Meal Prep", "Myth Busting"],
        category_configs=[
            user_taste.CategoryConfig(name="Hypertrophy", weight=50, keywords=["hypertrophy", "muscle", "volume"]),
            user_taste.CategoryConfig(name="Meal Prep", weight=30, keywords=["protein", "meal", "recipe"]),
            user_taste.CategoryConfig(name="Myth Busting", weight=20),
        ],
        sources=[
            user_taste.TopicSourceConfig(source_type="rss", locator="https://stronger.example.com/feed", label="SBS"),
            user_taste.TopicSourceConfig(source_type="reddit", locator="r/naturalbodybuilding"),
        ],
    )
    plan = fetch_topics.resolve_sources_for_user(fitness_taste)
    assert plan["is_tech"] is False
    assert plan["tech_feeds"] == []
    assert "naturalbodybuilding" in plan["reddit_subs"]
    assert "fitness" in plan["reddit_subs"]
    assert any(r["url"] == "https://stronger.example.com/feed" for r in plan["rss_sources"])

    # Tech niche still gets HN/devto/github/arxiv
    tech_taste = user_taste.UserTaste(
        niche="Software Engineering & Dev",
        tone="Educational",
        content_type="Educational",
        aesthetic="Dark",
        template_style="Technical Dark",
        target_audience="Developers",
        prompt_instructions="",
        categories=["AI", "SystemDesign"],
    )
    assert fetch_topics.resolve_sources_for_user(tech_taste)["tech_feeds"] == ["hackernews", "devto", "github", "arxiv"]

    # fetch_all_for_user must NOT call hackernews/devto/github/arxiv for Fitness
    for bad_fn in ("fetch_hackernews", "fetch_devto", "fetch_github", "fetch_arxiv"):
        monkeypatch.setitem(fetch_topics.SOURCES, bad_fn.replace("fetch_", ""), lambda *a, **k: (_ for _ in ()).throw(AssertionError(bad_fn)))
    monkeypatch.setattr(fetch_topics, "fetch_reddit", lambda s, limit, **kw: [
        fetch_topics.Topic(title="Weekly muscle volume sweet spot", url="https://reddit.com/r/fitness/1", source="reddit/r/fitness", score=420)
    ])
    monkeypatch.setattr(fetch_topics, "fetch_rss", lambda s, url, **kw: [
        fetch_topics.Topic(title="High protein meal prep guide", url="https://stronger.example.com/1", source="rss/stronger", score=0)
    ])
    monkeypatch.setattr(fetch_topics, "load_posted", lambda user_id=None: (set(), set()))

    got = fetch_topics.fetch_all_for_user(fitness_taste, limit=10)
    assert {t.title for t in got} == {"Weekly muscle volume sweet spot", "High protein meal prep guide"}
    by_title = {t.title: t for t in got}
    assert by_title["Weekly muscle volume sweet spot"].category == "Hypertrophy"
    assert by_title["High protein meal prep guide"].category == "Meal Prep"


# --------------------------------------------------------------------------- #
# 4. Weighted rotation, 40-candidate semantic fallback, tenant locale & style
# --------------------------------------------------------------------------- #
def test_weighted_selection_40_candidate_fallback_and_prompt_style(monkeypatch, tmp_path):
    monkeypatch.setattr(rank_topics, "DATA_DIR", tmp_path)
    # 45 candidates, NONE tagged as "Myth Busting"
    cands = [
        {
            "category": "Other",
            "title": f"Fitness Topic #{i}",
            "source": "reddit/r/fitness",
            "norm_score": round(i / 50.0, 3),
            "url": f"https://reddit.com/r/fitness/{i}",
            "summary": f"Summary {i}",
        }
        for i in range(45)
    ]
    import json
    (tmp_path / "topics_2026-11-11.json").write_text(json.dumps(cands), encoding="utf-8")

    custom_taste = user_taste.UserTaste(
        niche="Fitness & Workout",
        tone="Punchy",
        content_type="Educational",
        aesthetic="Vibrant",
        template_style="Minimal Clean",
        target_audience="Busy professionals",
        prompt_instructions="Keep tips practical.",
        categories=["Hypertrophy", "Myth Busting"],
        default_language="hi",
        handle="@fitbyraj",
        category_configs=[
            user_taste.CategoryConfig(name="Hypertrophy", weight=90),
            user_taste.CategoryConfig(
                name="Myth Busting",
                description="Debunk common gym and nutrition myths with evidence",
                weight=10,
                prompt_style="Start with a bold myth bust hook in 3 seconds.",
            ),
        ],
    )
    monkeypatch.setattr(user_taste, "get_user_taste", lambda uid=None: custom_taste)
    monkeypatch.setattr(rank_topics, "load_brand", lambda: {"handle": "@global_wrong", "language": "English", "topics_weight": {"AI": 1}})
    monkeypatch.setattr(rank_topics, "recent_titles", lambda *a, **k: [])
    monkeypatch.setattr(rank_topics, "last_category", lambda *a, **k: None)

    # Check weighted selection favors weight=90 over weight=10
    picks = [rank_topics.pick_category(custom_taste.category_weights(), seed=f"2026-11-11-{i}", avoid=None) for i in range(100)]
    assert picks.count("Hypertrophy") > 75

    captured = {}

    def fake_gen_json(prompt, schema, **kw):
        captured["prompt"] = prompt
        return rank_topics.RankedTopic(
            category="Myth Busting",
            title="Spot Reduction Is A Myth",
            angle="Fat loss happens systemically, not over the muscle you train.",
            source_url="https://reddit.com/r/fitness/44",
            evergreen=False,
            why="High save rate for beginners",
        )

    monkeypatch.setattr(rank_topics, "generate_json", fake_gen_json)
    res = rank_topics.rank("2026-11-11", category="Myth Busting")
    assert "@fitbyraj" in captured["prompt"] and "@global_wrong" not in captured["prompt"]
    assert "Language: Hinglish" in captured["prompt"]
    assert "Debunk common gym and nutrition myths" in captured["prompt"]
    assert "Start with a bold myth bust hook in 3 seconds." in captured["prompt"]
    # Top 40 candidates passed (indices 44 down to 5; lowest 0..4 excluded)
    assert "Fitness Topic #44" in captured["prompt"]
    assert "Fitness Topic #5" in captured["prompt"]
    assert "Fitness Topic #4\n" not in captured["prompt"]
    assert "Start with a bold myth bust hook in 3 seconds." in res.prompt_style

    # Verify prompt_style reaches gen_content -> reel_v2.spec.generate
    seen_scene_args = {}

    def fake_spec_gen(topic, category="", angle="", feedback="", language="en", prompt_style=""):
        seen_scene_args["prompt_style"] = prompt_style
        raise RuntimeError("stop-after-capture")

    monkeypatch.setattr(reel_spec, "generate", fake_spec_gen)
    monkeypatch.setattr("src.reel_v2.pipeline.notify_failure", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="stop-after-capture"):
        gen_content.generate(res, language="hi")
    assert "Start with a bold myth bust hook in 3 seconds." in seen_scene_args["prompt_style"]


# --------------------------------------------------------------------------- #
# 5. API validator & endpoints (/profile/categories, /profile/sources/test)
# --------------------------------------------------------------------------- #
def test_generate_category_validator_accepts_unicode_and_blocks_xss():
    ok = GenerateBody(category="हिंदी टेक & Finance (2026)", idempotency_key="abc12345")
    assert ok.category == "हिंदी टेक & Finance (2026)"

    with pytest.raises(ValueError):
        GenerateBody(category="Cooking<script>", idempotency_key="abc12345")
    with pytest.raises(ValueError):
        GenerateBody(category="a" * 65, idempotency_key="abc12345")
    with pytest.raises(ValueError):
        GenerateBody(category="Bad\x00Cat", idempotency_key="abc12345")


def test_profile_categories_and_source_test_endpoints(monkeypatch):
    from api.app.security import hash_password
    Base.metadata.create_all(db.engine())
    ratelimit.login_limiter.clear()
    ratelimit.otp_limiter.clear()
    monkeypatch.setenv("JWT_SECRET", "t" * 48)
    monkeypatch.setenv("SESSION_SECRET", "s" * 48)
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse battery")
    monkeypatch.setenv("COOKIE_SECURE", "false")

    tag = uuid.uuid4().hex[:8]
    uname = f"cat_tester_{tag}"
    with db.session() as s:
        u = User(username=uname, password_hash=hash_password("river-stone-42"), name="Cat Tester", role="client")
        s.add(u)
        s.flush()
        uid = u.id

    try:
        with TestClient(create_app()) as client:
            r = client.post("/api/auth/login", json={"username": uname, "password": "river-stone-42"})
            assert r.status_code == 200
            client.headers["X-CSRF-Token"] = r.json()["csrf"]

            put_res = client.put("/api/profile/categories", json={
                "categories": [
                    {"name": "Hypertrophy", "description": "Muscle building science", "weight": 60, "prompt_style": "Cite studies"},
                    {"name": "Meal Prep", "description": "High protein recipes", "weight": 40},
                ],
                "sources": [
                    {"source_type": "reddit", "locator": "r/fitness", "category": "Hypertrophy"},
                ],
            })
            assert put_res.status_code == 200, put_res.text
            data = put_res.json()
            assert [c["name"] for c in data["categories"]] == ["Hypertrophy", "Meal Prep"]
            assert data["categories"][0]["weight"] == 60
            assert data["sources"][0]["locator"] == "fitness"

            # GET returns the saved categories
            get_res = client.get("/api/profile/categories")
            assert get_res.status_code == 200
            assert get_res.json()["categories"][0]["prompt_style"] == "Cite studies"

            # SSRF attempt on /sources/test is rejected with 422
            ssrf_res = client.post("/api/profile/sources/test", json={"source_type": "rss", "locator": "http://169.254.169.254/latest/meta-data"})
            assert ssrf_res.status_code == 422

            # Valid RSS preview returns up to 3 headlines
            monkeypatch.setattr(fetch_topics.socket, "getaddrinfo", _fake_public_dns("93.184.216.34"))
            monkeypatch.setattr(fetch_topics, "fetch_rss", lambda s, url, limit=3: [
                fetch_topics.Topic(title=f"Headline {i}", url=f"https://fit.example.com/{i}", source="rss", published="2026-11-11")
                for i in range(5)
            ])
            ok_res = client.post("/api/profile/sources/test", json={"source_type": "substack", "locator": "fitweekly"})
            assert ok_res.status_code == 200, ok_res.text
            assert ok_res.json()["resolved_url"] == "https://fitweekly.substack.com/feed"
            assert len(ok_res.json()["headlines"]) == 3
    finally:
        with db.session() as s:
            s.execute(delete(User).where(User.id == uid))
