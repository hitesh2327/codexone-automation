"""multi-platform normalized schema expand: 7 tables + posted_topics.user_id

Revision ID: 5b2c3d4e5f6a
Revises: 4a1b2c3d4e5f
Create Date: 2026-11-12 00:00:00

Phase 1 (Expand — Non-Blocking DDL):
- Creates social_accounts, oauth_tokens, publishing_targets, media_assets,
  content_templates, platform_analytics, and webhook_events.
- Adds nullable user_id column to posted_topics for tenant-scoped deduplication.
- Creates concurrent indexes on PostgreSQL via autocommit_block().
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "5b2c3d4e5f6a"
down_revision: Union[str, Sequence[str], None] = "4a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
BigIntPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("id", BigIntPK, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=24), nullable=False),
        sa.Column("external_account_id", sa.String(length=128), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False, server_default="business"),
        sa.Column("handle", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("display_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("metadata_json", JSONType, nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "platform", "external_account_id", name="uq_social_accounts_user_plat_ext"),
    )
    op.create_index("ix_social_accounts_user_id", "social_accounts", ["user_id"], unique=False)
    op.create_index("ix_social_accounts_status", "social_accounts", ["status"], unique=False)

    op.create_table(
        "oauth_tokens",
        sa.Column("id", BigIntPK, autoincrement=True, nullable=False),
        sa.Column("social_account_id", BigIntPK, nullable=False),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("access_token_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("dek_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("token_type", sa.String(length=24), nullable=False, server_default="Bearer"),
        sa.Column("scopes", JSONType, nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("social_account_id"),
    )

    op.create_table(
        "publishing_targets",
        sa.Column("id", BigIntPK, autoincrement=True, nullable=False),
        sa.Column("post_id", sa.String(length=40), nullable=False),
        sa.Column("social_account_id", BigIntPK, nullable=True),
        sa.Column("platform", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_post_id", sa.String(length=128), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("title_override", sa.Text(), nullable=True),
        sa.Column("caption_override", sa.Text(), nullable=True),
        sa.Column("platform_options", JSONType, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "social_account_id", name="uq_publishing_targets_post_acct"),
    )
    op.create_index("ix_publishing_targets_post_id", "publishing_targets", ["post_id"], unique=False)
    op.create_index("ix_publishing_targets_status", "publishing_targets", ["status"], unique=False)
    op.create_index("ix_publishing_targets_scheduled_at", "publishing_targets", ["scheduled_at"], unique=False)

    op.create_table(
        "media_assets",
        sa.Column("id", BigIntPK, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.String(length=40), nullable=True),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=True),
        sa.Column("storage_provider", sa.String(length=16), nullable=False, server_default="cloudinary"),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("public_url", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False, server_default="application/octet-stream"),
        sa.Column("bytes_size", sa.BigInteger(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_assets_user_id", "media_assets", ["user_id"], unique=False)
    op.create_index("ix_media_assets_post_id", "media_assets", ["post_id"], unique=False)

    op.create_table(
        "content_templates",
        sa.Column("id", BigIntPK, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=16), nullable=False, server_default="9:16"),
        sa.Column("brand_tokens", JSONType, nullable=False),
        sa.Column("prompt_system_hint", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_templates_user_id", "content_templates", ["user_id"], unique=False)

    op.create_table(
        "platform_analytics",
        sa.Column("id", BigIntPK, autoincrement=True, nullable=False),
        sa.Column("publishing_target_id", BigIntPK, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=24), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reach", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("saves", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_watch_time_ms", sa.Integer(), nullable=True),
        sa.Column("engagement_rate_bps", sa.Integer(), nullable=True),
        sa.Column("raw_metrics", JSONType, nullable=False),
        sa.ForeignKeyConstraint(["publishing_target_id"], ["publishing_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_analytics_publishing_target_id", "platform_analytics", ["publishing_target_id"], unique=False)
    op.create_index("ix_platform_analytics_user_id", "platform_analytics", ["user_id"], unique=False)
    op.create_index("ix_platform_analytics_captured_at", "platform_analytics", ["captured_at"], unique=False)

    op.create_table(
        "webhook_events",
        sa.Column("id", BigIntPK, autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("social_account_id", BigIntPK, nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("signature_valid", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="received"),
        sa.Column("payload", JSONType, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"),
    )

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("posted_topics") as batch_op:
            batch_op.add_column(
                sa.Column("user_id", sa.Integer(), nullable=True),
            )
            batch_op.create_foreign_key(
                "fk_posted_topics_user_id",
                "users",
                ["user_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.add_column(
            "posted_topics",
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", name="fk_posted_topics_user_id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    with op.get_context().autocommit_block():
        op.create_index(
            "ix_oauth_tokens_access_expires_at",
            "oauth_tokens",
            ["access_expires_at"],
            unique=False,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_publishing_targets_status_sched",
            "publishing_targets",
            ["status", "scheduled_at"],
            unique=False,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_webhook_events_status",
            "webhook_events",
            ["status"],
            unique=False,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_posted_topics_user_id",
            "posted_topics",
            ["user_id"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index("ix_posted_topics_user_id", table_name="posted_topics", postgresql_concurrently=True)
        op.drop_index("ix_webhook_events_status", table_name="webhook_events", postgresql_concurrently=True)
        op.drop_index("ix_publishing_targets_status_sched", table_name="publishing_targets", postgresql_concurrently=True)
        op.drop_index("ix_oauth_tokens_access_expires_at", table_name="oauth_tokens", postgresql_concurrently=True)

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("posted_topics") as batch_op:
            batch_op.drop_column("user_id")
    else:
        op.drop_column("posted_topics", "user_id")

    op.drop_table("webhook_events")
    op.drop_index("ix_platform_analytics_captured_at", table_name="platform_analytics")
    op.drop_index("ix_platform_analytics_user_id", table_name="platform_analytics")
    op.drop_index("ix_platform_analytics_publishing_target_id", table_name="platform_analytics")
    op.drop_table("platform_analytics")
    op.drop_index("ix_content_templates_user_id", table_name="content_templates")
    op.drop_table("content_templates")
    op.drop_index("ix_media_assets_post_id", table_name="media_assets")
    op.drop_index("ix_media_assets_user_id", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_publishing_targets_scheduled_at", table_name="publishing_targets")
    op.drop_index("ix_publishing_targets_status", table_name="publishing_targets")
    op.drop_index("ix_publishing_targets_post_id", table_name="publishing_targets")
    op.drop_table("publishing_targets")
    op.drop_table("oauth_tokens")
    op.drop_index("ix_social_accounts_status", table_name="social_accounts")
    op.drop_index("ix_social_accounts_user_id", table_name="social_accounts")
    op.drop_table("social_accounts")
