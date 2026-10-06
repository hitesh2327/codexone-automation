"""generation_jobs: dashboard/scheduled generation requests and their progress

Revision ID: c63e49f7a2d5
Revises: b52d38e6f1c4
Create Date: 2026-10-05 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c63e49f7a2d5'
down_revision: Union[str, Sequence[str], None] = 'b52d38e6f1c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE = "status IN ('queued', 'running')"


def upgrade() -> None:
    # Additive only: a new table; nothing existing is touched.
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')
    op.create_table(
        'generation_jobs',
        sa.Column('id', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('trigger', sa.String(length=16), nullable=False),
        sa.Column('requested_by', sa.String(length=254), nullable=True),
        sa.Column('idempotency_key', sa.String(length=64), nullable=True),
        sa.Column('slot_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('category', sa.String(length=32), nullable=True),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('force', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('allow_duplicate', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('phase', sa.String(length=20), nullable=True),
        sa.Column('failure_reason', sa.String(length=24), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('github_run_id', sa.BigInteger(), nullable=True),
        sa.Column('github_run_url', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('topic_title', sa.Text(), nullable=True),
        sa.Column('topic_category', sa.String(length=32), nullable=True),
        sa.Column('post_group_id', sa.String(length=120), nullable=True),
        sa.Column('post_ids', json_type, nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index('ix_generation_jobs_created_at', 'generation_jobs', ['created_at'], unique=False)
    # The lock: at most one queued/running job per trigger.
    op.create_index('uq_generation_jobs_one_active', 'generation_jobs', ['trigger'], unique=True,
                    postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))


def downgrade() -> None:
    op.drop_index('uq_generation_jobs_one_active', table_name='generation_jobs',
                  postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))
    op.drop_index('ix_generation_jobs_created_at', table_name='generation_jobs')
    op.drop_table('generation_jobs')
