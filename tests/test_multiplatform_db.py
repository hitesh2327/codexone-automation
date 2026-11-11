"""Tests for the Phase-1 Multi-Platform DB schema, Alembic migration, AAD-bound OAuth encryption,
idempotent backfill/parity verification, and queue_store dual-write hooks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import IntegrityError

from src import config_store, db, queue_store as q, user_config_store
from src.db.backfill_multiplatform import backfill_all, verify_parity
from src.db.models import (
    Base,
    ContentTemplate,
    MediaAsset,
    OAuthToken,
    PlatformAnalytic,
    Post,
    PostedTopic,
    PublishingTarget,
    SocialAccount,
    User,
    UserConfigValue,
    WebhookEvent,
)
from src.db.multiplatform import decrypt_oauth_tokens, encrypt_oauth_tokens

ROOT = Path(__file__).resolve().parent.parent


def _alembic_cfg() -> Config:
    cfg = Config(str(ROOT / "api" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "api" / "migrations"))
    return cfg


def _reset_db_caches() -> None:
    try:
        db.engine().dispose()
    except Exception:  # noqa: BLE001
        pass
    db.engine.cache_clear()
    db._sessionmaker.cache_clear()
    config_store._dek_cache.clear()
    config_store.invalidate()


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Fresh SQLite database with full Base.metadata schema and a fresh CONFIG_MASTER_KEY."""
    db_file = tmp_path / "multiplatform_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("CONFIG_MASTER_KEY", config_store.generate_master_key())
    _reset_db_caches()
    Base.metadata.create_all(db.engine())
    try:
        yield db_file
    finally:
        user_config_store._cache.clear()
        _reset_db_caches()


def test_alembic_upgrade_and_downgrade_sqlite(tmp_path, monkeypatch):
    """Verify 5b2c3d4e5f6a upgrades cleanly from 4a1b2c3d4e5f and downgrades cleanly on SQLite."""
    from alembic.script import ScriptDirectory

    db_file = tmp_path / "alembic_test.db"
    url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    _reset_db_caches()

    cfg = _alembic_cfg()
    script = ScriptDirectory.from_config(cfg)
    assert list(script.get_heads()) == ["5b2c3d4e5f6a"]
    rev = script.get_revision("5b2c3d4e5f6a")
    assert rev is not None and rev.down_revision == "4a1b2c3d4e5f"

    expected_tables = {
        "social_accounts",
        "oauth_tokens",
        "publishing_targets",
        "media_assets",
        "content_templates",
        "platform_analytics",
        "webhook_events",
    }

    try:
        # Build full current schema, stamp at head, and downgrade to 4a1b2c3d4e5f
        # (older 2026-09 migrations contain Postgres-only SQL like to_char/substring).
        eng = create_engine(url)
        try:
            Base.metadata.create_all(eng)
        finally:
            eng.dispose()

        command.stamp(cfg, "head")
        command.downgrade(cfg, "4a1b2c3d4e5f")

        eng = create_engine(url)
        try:
            insp = inspect(eng)
            tables_before = set(insp.get_table_names())
            for tbl in expected_tables:
                assert tbl not in tables_before
            pt_cols_before = {c["name"] for c in insp.get_columns("posted_topics")}
            assert "user_id" not in pt_cols_before
        finally:
            eng.dispose()

        # Upgrade 4a1b2c3d4e5f -> 5b2c3d4e5f6a (head) on SQLite.
        command.upgrade(cfg, "head")
        eng = create_engine(url)
        try:
            insp = inspect(eng)
            tables = set(insp.get_table_names())
            assert expected_tables.issubset(tables)

            pt_cols = {c["name"] for c in insp.get_columns("posted_topics")}
            assert "user_id" in pt_cols

            oauth_idx = {i["name"] for i in insp.get_indexes("oauth_tokens")}
            assert "ix_oauth_tokens_access_expires_at" in oauth_idx
            pub_idx = {i["name"] for i in insp.get_indexes("publishing_targets")}
            assert "ix_publishing_targets_status_sched" in pub_idx
            wh_idx = {i["name"] for i in insp.get_indexes("webhook_events")}
            assert "ix_webhook_events_status" in wh_idx
            pt_idx = {i["name"] for i in insp.get_indexes("posted_topics")}
            assert "ix_posted_topics_user_id" in pt_idx
        finally:
            eng.dispose()

        # Downgrade back to 4a1b2c3d4e5f and re-upgrade to confirm repeatability.
        command.downgrade(cfg, "4a1b2c3d4e5f")
        command.upgrade(cfg, "head")
    finally:
        _reset_db_caches()

    down_sql = (ROOT / "api" / "migrations" / "versions" / "5b2c3d4e5f6a_multiplatform_expand_down.sql").read_text(
        encoding="utf-8"
    )
    for tbl in (
        "webhook_events",
        "platform_analytics",
        "content_templates",
        "media_assets",
        "publishing_targets",
        "oauth_tokens",
        "social_accounts",
    ):
        assert f"DROP TABLE IF EXISTS {tbl}" in down_sql
    assert "ALTER TABLE posted_topics DROP COLUMN IF EXISTS user_id" in down_sql


def test_social_account_and_oauth_token_aad_binding(isolated_db):
    """Ciphertext encrypted for one social_account_id must fail decryption if transplanted or tampered."""
    with db.session() as s:
        u = User(id=1, username="owner", email="owner@example.com", role="owner")
        s.add(u)
        s.flush()
        acct1 = SocialAccount(
            user_id=u.id,
            platform="instagram",
            external_account_id="17841400001",
            handle="@mintly",
            display_name="Mintly Official",
            is_default=True,
        )
        acct2 = SocialAccount(
            user_id=u.id,
            platform="instagram",
            external_account_id="17841400002",
            handle="@mintly_alt",
            display_name="Mintly Alt",
            is_default=False,
        )
        s.add_all([acct1, acct2])
        s.flush()

        expires = datetime.now(timezone.utc) + timedelta(days=60)
        tok = encrypt_oauth_tokens(
            s,
            acct1.id,
            access_token="IG_SECRET_ACCESS_123",
            refresh_token="IG_SECRET_REFRESH_456",
            scopes=["instagram_business_content_publish"],
            access_expires_at=expires,
        )
        tok_id = tok.id
        acct1_id = acct1.id
        acct2_id = acct2.id

    # Valid decryption with matching social_account_id succeeds.
    with db.session() as s:
        tok = s.get(OAuthToken, tok_id)
        assert tok is not None
        acc, ref = decrypt_oauth_tokens(s, tok)
        assert acc == "IG_SECRET_ACCESS_123"
        assert ref == "IG_SECRET_REFRESH_456"

        # Tampering / checking against a different social_account_id fails AES-GCM tag verification.
        with pytest.raises(config_store.StoreError) as exc_info:
            decrypt_oauth_tokens(s, tok, expected_social_account_id=acct2_id)
        assert exc_info.value.code == "database.key_mismatch"

        # Transplant ciphertext onto acct2's row: row's own social_account_id now disagrees with AAD.
        tok2 = OAuthToken(
            social_account_id=acct2_id,
            access_token_enc=tok.access_token_enc,
            access_token_nonce=tok.access_token_nonce,
            dek_version=tok.dek_version,
        )
        with pytest.raises(config_store.StoreError) as exc_info2:
            decrypt_oauth_tokens(s, tok2)
        assert exc_info2.value.code == "database.key_mismatch"

        # Verify unique constraint on (user_id, platform, external_account_id)
        dup = SocialAccount(user_id=1, platform="instagram", external_account_id="17841400001")
        s.add(dup)
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()
        assert acct1_id != acct2_id


def test_webhook_event_unique_constraint_idempotency(isolated_db):
    """WebhookEvent enforces unique (provider, event_id) across deliveries."""
    with db.session() as s:
        s.add(
            WebhookEvent(
                provider="razorpay",
                event_id="evt_rzp_001",
                event_type="subscription.charged",
                signature_valid=True,
                status="processed",
                payload={"amount": 99900},
            )
        )

    with db.session() as s:
        s.add(
            WebhookEvent(
                provider="razorpay",
                event_id="evt_rzp_001",
                event_type="subscription.charged",
                signature_valid=True,
                status="received",
                payload={"amount": 99900},
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()

    # Different provider with the same event_id is allowed.
    with db.session() as s:
        s.add(
            WebhookEvent(
                provider="stripe",
                event_id="evt_rzp_001",
                event_type="invoice.paid",
                signature_valid=True,
                status="processed",
                payload={},
            )
        )
        s.flush()
        assert s.scalar(select(func.count()).select_from(WebhookEvent)) == 2


def test_content_template_and_platform_analytics_models(isolated_db):
    """Smoke-test ContentTemplate and PlatformAnalytic persistence and FK relations."""
    with db.session() as s:
        u = User(id=1, username="owner", email="owner@example.com", role="owner")
        s.add(u)
        s.flush()

        tpl = ContentTemplate(
            user_id=u.id,
            slug="mintly-dark-9-16",
            name="Mintly Dark Reel",
            kind="reel_v2",
            aspect_ratio="9:16",
            brand_tokens={"bg": "#0b0f19", "accent": "#22d3ee"},
            prompt_system_hint="Keep hooks crisp.",
            is_public=False,
        )
        s.add(tpl)

        post = Post(
            id="20261112-r-abc123",
            kind="reel",
            date=datetime(2026, 11, 12, tzinfo=timezone.utc).date(),
            topic="Database Sharding",
            category="SystemDesign",
            post_dir="output/2026-11-12/sharding",
            caption="Sharding basics",
            media={"reel": "https://res.cloudinary.com/demo/video/upload/v1/codexone/2026-11-12/sharding/reel.mp4"},
            status="published",
            user_id=u.id,
        )
        s.add(post)
        s.flush()

        pt = PublishingTarget(
            post_id=post.id,
            platform="instagram",
            status="published",
            external_post_id="1800001",
        )
        s.add(pt)
        s.flush()

        analytic = PlatformAnalytic(
            publishing_target_id=pt.id,
            user_id=u.id,
            platform="instagram",
            impressions=1200,
            reach=980,
            views=1100,
            likes=85,
            comments=12,
            shares=9,
            saves=34,
            avg_watch_time_ms=14500,
            engagement_rate_bps=1142,
            raw_metrics={"plays": 1100},
        )
        s.add(analytic)
        s.flush()
        assert tpl.id is not None and analytic.id is not None


def test_backfill_multiplatform_idempotent_and_parity(isolated_db):
    """End-to-end backfill from legacy UserConfigValue, Post, and PostedTopic + idempotency + verify_parity()."""
    with db.session() as s:
        u1 = User(id=1, username="owner", email="owner@example.com", role="owner")
        u2 = User(id=2, username="client2", email="client2@example.com", role="client")
        s.add_all([u1, u2])
        s.flush()

    # Populate legacy UserConfigValue credentials for both users.
    user_config_store.save(1, {"IG_ACCESS_TOKEN": "ig-tok-u1", "IG_USER_ID": "17841411111"}, actor="test")
    user_config_store.save(
        2,
        {
            "IG_ACCESS_TOKEN": "ig-tok-u2",
            "IG_USER_ID": "17841422222",
            "YT_CLIENT_ID": "yt-cid-2",
            "YT_REFRESH_TOKEN": "yt-ref-u2",
            "YT_PRIVACY": "unlisted",
        },
        actor="test",
    )

    # Populate legacy Post rows directly (bypassing queue_store dual-write to simulate pre-migration data).
    with db.session() as s:
        p1 = Post(
            id="20261110-c-111111",
            kind="carousel",
            date=datetime(2026, 11, 10, tzinfo=timezone.utc).date(),
            topic="Consistent Hashing",
            category="SystemDesign",
            post_dir="output/2026-11-10/consistent-hashing",
            caption="Consistent hashing explained",
            media={
                "carousel": [
                    "https://res.cloudinary.com/demo/image/upload/v1/codexone/2026-11-10/ch/slide_01.jpg",
                    "https://res.cloudinary.com/demo/image/upload/v1/codexone/2026-11-10/ch/slide_02.jpg",
                ]
            },
            status="published",
            ig_media_id="ig-999",
            platforms={"ig": {"status": "published", "id": "ig-999", "url": "https://ig/p/999"}},
            user_id=1,
        )
        p2 = Post(
            id="20261111-r-222222",
            kind="reel",
            date=datetime(2026, 11, 11, tzinfo=timezone.utc).date(),
            topic="B-Tree Indexes",
            category="SystemDesign",
            post_dir="output/2026-11-11/btree",
            caption="How B-Trees work",
            media={
                "reel": "https://res.cloudinary.com/demo/video/upload/v1/codexone/2026-11-11/btree/reel.mp4",
                "cover": "https://res.cloudinary.com/demo/image/upload/v1/codexone/2026-11-11/btree/reel_cover.jpg",
            },
            status="approved",
            publish_at=datetime(2026, 11, 12, 13, 30, tzinfo=timezone.utc),
            targets=["ig", "yt"],
            yt_title="B-Tree Indexes in 30s",
            yt_description="Deep dive into database indexes.",
            platforms={"ig": {"status": "published", "id": "ig-888"}},
            user_id=2,
        )
        s.add_all([p1, p2])
        s.flush()

        # Legacy PostedTopic rows without user_id (one linked to p2, one legacy unlinked).
        s.add_all([
            PostedTopic(item_id=p2.id, title="B-Tree Indexes", category="SystemDesign", kind="reel"),
            PostedTopic(item_id=None, title="Legacy Topic Without Item", category="AI", kind="carousel"),
        ])

    # Dry-run should not write anything.
    dry = backfill_all(batch_size=1, dry_run=True)
    assert dry["dry_run"] is True
    assert dry["social_accounts"]["created"] == 3
    assert dry["publishing_targets"]["created"] == 3
    assert dry["media_assets"]["created"] == 4
    assert dry["posted_topics"]["updated"] == 2
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(SocialAccount)) == 0
        assert s.scalar(select(func.count()).select_from(PublishingTarget)) == 0
        assert s.scalar(select(func.count()).select_from(MediaAsset)) == 0

    # First real run (with small batch_size=1 to exercise batching loops).
    first = backfill_all(batch_size=1, dry_run=False)
    assert first["dry_run"] is False
    assert first["social_accounts"] == {"created": 3, "updated": 0, "skipped": 0}
    assert first["oauth_tokens"] == {"created": 3, "updated": 0, "skipped": 0}
    assert first["publishing_targets"] == {"created": 3, "updated": 0, "skipped": 0}
    assert first["media_assets"] == {"created": 4, "updated": 0, "skipped": 0}
    assert first["posted_topics"] == {"updated": 2, "skipped": 0}

    parity = verify_parity()
    assert parity["ok"] is True
    assert parity["publishing_targets_count"] == 3
    assert parity["media_assets_count"] == 4
    assert parity["posted_topics_missing_user_id"] == 0
    assert parity["social_accounts_count"] == 3
    assert parity["oauth_tokens_count"] == 3

    # Verify decrypted tokens and Cloudinary storage_key extraction.
    with db.session() as s:
        u2_yt = s.scalars(
            select(SocialAccount).where(SocialAccount.user_id == 2, SocialAccount.platform == "youtube")
        ).first()
        assert u2_yt is not None
        u2_tok = s.scalars(select(OAuthToken).where(OAuthToken.social_account_id == u2_yt.id)).first()
        assert u2_tok is not None
        acc, ref = decrypt_oauth_tokens(s, u2_tok)
        assert acc is None and ref == "yt-ref-u2"

        assets = list(s.scalars(select(MediaAsset).where(MediaAsset.post_id == "20261110-c-111111")))
        assert sorted(a.storage_key for a in assets) == [
            "codexone/2026-11-10/ch/slide_01",
            "codexone/2026-11-10/ch/slide_02",
        ]

        topics = {t.title: t.user_id for t in s.scalars(select(PostedTopic))}
        assert topics["B-Tree Indexes"] == 2
        assert topics["Legacy Topic Without Item"] == 1

    # Second run: strictly idempotent (zero created, zero updated).
    second = backfill_all(batch_size=500, dry_run=False)
    assert second["social_accounts"] == {"created": 0, "updated": 0, "skipped": 3}
    assert second["oauth_tokens"] == {"created": 0, "updated": 0, "skipped": 3}
    assert second["publishing_targets"] == {"created": 0, "updated": 0, "skipped": 3}
    assert second["media_assets"] == {"created": 0, "updated": 0, "skipped": 4}
    assert second["posted_topics"] == {"updated": 0, "skipped": 2}
    assert verify_parity()["ok"] is True


def test_queue_store_dual_write_sync(isolated_db):
    """queue_store.save / update_if / record_posted dual-write into PublishingTarget, MediaAsset, and PostedTopic.user_id."""
    with db.session() as s:
        s.add(User(id=1, username="owner", email="owner@example.com", role="owner"))

    item = q.Item(
        id="20261112-r-dual01",
        kind="reel",
        date="2026-11-12",
        topic="Dual Write Verification",
        category="AI",
        post_dir="output/2026-11-12/dual-write",
        caption="Dual write caption",
        media={
            "reel": "https://res.cloudinary.com/demo/video/upload/v1/codexone/2026-11-12/dual/reel.mp4",
            "cover": "https://res.cloudinary.com/demo/image/upload/v1/codexone/2026-11-12/dual/reel_cover.jpg",
        },
        status="pending",
        targets=["ig", "yt"],
        yt_title="Dual Write YT",
        user_id=1,
    )
    q.save([item])

    with db.session() as s:
        targets = list(s.scalars(select(PublishingTarget).where(PublishingTarget.post_id == item.id)))
        assert {t.platform: t.status for t in targets} == {"instagram": "queued", "youtube": "queued"}
        assets = list(s.scalars(select(MediaAsset).where(MediaAsset.post_id == item.id)))
        assert {a.role for a in assets} == {"reel_mp4", "cover_jpg"}

    item.status = "published"
    item.ig_media_id = "ig-dual-99"
    item.platforms = {
        "ig": {"status": "published", "id": "ig-dual-99", "url": "https://ig/p/dual"},
        "yt": {"status": "failed", "error": "quota", "attempts": 2},
    }
    assert q.update_if(item, from_status="pending") is True
    q.record_posted(item)

    with db.session() as s:
        targets = {
            t.platform: t
            for t in s.scalars(select(PublishingTarget).where(PublishingTarget.post_id == item.id))
        }
        assert targets["instagram"].status == "published"
        assert targets["instagram"].external_post_id == "ig-dual-99"
        assert targets["youtube"].status == "failed"
        assert targets["youtube"].error_message == "quota"
        assert targets["youtube"].attempts == 2

        pt = s.scalars(select(PostedTopic).where(PostedTopic.item_id == item.id)).first()
        assert pt is not None and pt.user_id == 1

    assert verify_parity()["ok"] is True
