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
    from api.app.settings import settings
    Base.metadata.create_all(db.engine())
    ratelimit.login_limiter.clear()
    ratelimit.otp_limiter.clear()
    monkeypatch.setenv("JWT_SECRET", "t" * 48)
    monkeypatch.setenv("SESSION_SECRET", "s" * 48)
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse battery")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("ORIGIN_VERIFY", "")
    settings.cache_clear()

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


# --------------------------------------------------------------------------- #
# 6. Adversarial QA Regression Tests (TOCTOU, Hex IP, 5KB XXE, Unicode CLI,
#    Non-Tech Empty Categories & Prompt Leak, Live Form Niche)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("obfuscated_url", [
    "https://0x7f.0.0.0x1/feed.xml",
    "https://0177.0.0.1/feed.xml",
    "https://2130706433/feed.xml",
    "https://127.1/feed.xml",
    "https://0x7f000001/feed.xml",
    "https://0x0a.0.0.1/feed.xml",
    "https://0xa9fea9fe/latest/meta-data",
])
def test_ssrf_blocks_obfuscated_hex_octal_decimal_ipv4(obfuscated_url):
    with pytest.raises(ValueError):
        fetch_topics.validate_safe_feed_url(obfuscated_url)


def test_ssrf_toctou_dns_rebinding_pins_validated_ip(monkeypatch):
    import urllib3.util.connection as u3_conn

    calls = {"dns": 0, "connect": []}

    def rebinding_getaddrinfo(host, port, *a, **kw):
        calls["dns"] += 1
        ip = "93.184.216.34" if calls["dns"] == 1 else "10.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    def fake_create_connection(address, *a, **kw):
        calls["connect"].append(address)
        raise OSError("sentinel-stop-after-pin-check")

    monkeypatch.setattr(fetch_topics.socket, "getaddrinfo", rebinding_getaddrinfo)
    monkeypatch.setattr(u3_conn, "create_connection", fake_create_connection)

    with pytest.raises(Exception):
        fetch_topics.fetch_rss(fetch_topics._session(), "https://rebind.example.com/feed.xml")

    assert calls["connect"], "expected urllib3 create_connection to be called"
    assert all(addr == ("93.184.216.34", 443) for addr in calls["connect"])


def test_xml_bomb_padded_over_5kb_and_utf16_rejected():
    padded = (
        b'<?xml version="1.0" encoding="UTF-8"?><!-- '
        + b"A" * 5200
        + b' --><!DOCTYPE lolz [<!ENTITY lol "lol">]><rss version="2.0"><channel><item><title>&lol;</title></item></channel></rss>'
    )
    with pytest.raises(ValueError, match="DOCTYPE/ENTITY"):
        fetch_topics.parse_feed_xml(padded)

    utf16_bom = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE lolz [<!ENTITY a "b">]><rss/>'.encode("utf-16")
    with pytest.raises(ValueError, match="DOCTYPE/ENTITY"):
        fetch_topics.parse_feed_xml(utf16_bom)


def test_main_generate_input_error_accepts_unicode_and_blocks_xss():
    import main as pipeline_main

    ok_args = SimpleNamespace(
        date="2026-11-11",
        slot=None,
        category="हिंदी टेक & Finance",
        topic="Index Funds vs ETFs Explained",
        source_url=None,
    )
    assert pipeline_main._generate_input_error(ok_args) is None

    bad_args = SimpleNamespace(
        date="2026-11-11",
        slot=None,
        category="Fitness<script>",
        topic="Valid Topic Name",
        source_url=None,
    )
    assert pipeline_main._generate_input_error(bad_args) is not None


def test_nontech_empty_categories_no_ai_fallback_and_reel_v2_uses_tenant_handle(monkeypatch):
    Base.metadata.create_all(db.engine())
    tag = uuid.uuid4().hex[:8]
    with db.session() as s:
        u = User(
            username=f"fituser_{tag}",
            name="Fit User",
            role="client",
            taste={"niche": "Fitness & Workout", "handle": "@fitstudio", "target_audience": "Lifters"},
        )
        s.add(u)
        s.flush()
        uid = u.id

    try:
        taste = user_taste.get_user_taste(uid)
        assert taste.categories == []
        assert taste.category_configs == []
        assert taste.effective_handle() == "@fitstudio"

        # rank() with no configured categories on non-tech niche refuses to silently pick AI/DSA
        monkeypatch.setattr(user_taste, "get_user_taste", lambda *a, **k: taste)
        with pytest.raises(ValueError, match="No content categories configured"):
            rank_topics.rank("2026-11-11")

        # reel_v2 prompt and pipeline CTA use tenant handle & omit tech education / tech hashtags
        monkeypatch.setattr(reel_spec, "load_brand", lambda: {"handle": "@wrongbrand", "hashtags": ["#systemdesign", "#dsa"], "reel": {}})
        prompt = reel_spec._prompt("Progressive Overload", "Hypertrophy", "Track weekly sets", {"handle": "@wrongbrand", "hashtags": ["#systemdesign"], "reel": {}})
        sys_p = reel_spec._system_prompt(taste)
        assert "@fitstudio" in prompt and "@wrongbrand" not in prompt
        assert "#systemdesign" not in prompt
        assert "tech education" not in sys_p.lower()
        assert "Fitness & Workout" in sys_p

        from src.reel_v2 import pipeline as v2_pipe
        example_path = Path(__file__).resolve().parent.parent / "src" / "reel_v2" / "examples" / "blue_green.json"
        spec_obj = reel_spec.SceneSpec.model_validate_json(example_path.read_text(encoding="utf-8"))
        content = v2_pipe.to_content(spec_obj, "Progressive Overload", "Hypertrophy")
        assert content.carousel[-1].body == "Follow @fitstudio"
    finally:
        with db.session() as s:
            s.execute(delete(User).where(User.id == uid))


def test_suggest_categories_honors_unsaved_body_niche(monkeypatch):
    from api.app.security import hash_password
    from api.app.settings import settings
    Base.metadata.create_all(db.engine())
    ratelimit.login_limiter.clear()
    ratelimit.otp_limiter.clear()
    monkeypatch.setenv("JWT_SECRET", "t" * 48)
    monkeypatch.setenv("SESSION_SECRET", "s" * 48)
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse battery")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("ORIGIN_VERIFY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFakeTestKeyForUnitTestsOnly12345")
    settings.cache_clear()

    captured = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            captured["prompt"] = contents
            return SimpleNamespace(text='{"categories":[{"name":"Sourdough","description":"Wild yeast","weight":40},{"name":"Pastries","description":"Laminated dough","weight":60}],"suggested_subreddits":["Breadit"],"reasoning":"Balanced baking pillars."}')

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    import google.genai as _genai
    monkeypatch.setattr(_genai, "Client", FakeClient)

    tag = uuid.uuid4().hex[:8]
    uname = f"baker_{tag}"
    with db.session() as s:
        u = User(username=uname, password_hash=hash_password("river-stone-42"), name="Baker", role="client",
                 taste={"niche": "AI & Tech"})
        s.add(u)
        s.flush()
        uid = u.id

    try:
        with TestClient(create_app()) as client:
            r = client.post("/api/auth/login", json={"username": uname, "password": "river-stone-42"})
            assert r.status_code == 200
            client.headers["X-CSRF-Token"] = r.json()["csrf"]

            res = client.post("/api/profile/suggest-categories", json={
                "niche": "Vegan Baking",
                "content_type": "Tutorial & Walkthrough",
                "target_audience": "Home bakers",
            })
            assert res.status_code == 200, res.text
            assert "Vegan Baking" in captured["prompt"]
            assert "Home bakers" in captured["prompt"]
            assert "AI & Tech" not in captured["prompt"]
            assert res.json()["categories"] == ["Sourdough", "Pastries"]
    finally:
        with db.session() as s:
            s.execute(delete(User).where(User.id == uid))
