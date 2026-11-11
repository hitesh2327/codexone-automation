-- Companion PostgreSQL rollback script for revision 5b2c3d4e5f6a (Phase 1 Expand).
-- Execute outside an explicit transaction block because DROP INDEX CONCURRENTLY cannot run inside BEGIN/COMMIT.

DROP INDEX CONCURRENTLY IF EXISTS ix_posted_topics_user_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_webhook_events_status;
DROP INDEX CONCURRENTLY IF EXISTS ix_publishing_targets_status_sched;
DROP INDEX CONCURRENTLY IF EXISTS ix_oauth_tokens_access_expires_at;

ALTER TABLE posted_topics DROP COLUMN IF EXISTS user_id;

DROP TABLE IF EXISTS webhook_events;
DROP TABLE IF EXISTS platform_analytics;
DROP TABLE IF EXISTS content_templates;
DROP TABLE IF EXISTS media_assets;
DROP TABLE IF EXISTS publishing_targets;
DROP TABLE IF EXISTS oauth_tokens;
DROP TABLE IF EXISTS social_accounts;
