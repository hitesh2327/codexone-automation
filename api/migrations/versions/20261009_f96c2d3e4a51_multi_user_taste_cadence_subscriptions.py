"""multi-user taste, cadence, subscriptions, config completion, and user_id scoping

Revision ID: f96c2d3e4a51
Revises: e85b1c2d9f40
Create Date: 2026-10-09 02:00:00

Additive migration:
- User taste, cadence, subscription details, and config completion gate.
- user_id scoping on posts, activity_log, and generation_jobs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f96c2d3e4a51'
down_revision: Union[str, Sequence[str], None] = 'e85b1c2d9f40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    # Users extensions
    op.add_column('users', sa.Column('taste', JSONType, nullable=True))
    op.add_column('users', sa.Column('cadence', JSONType, nullable=True))
    op.add_column('users', sa.Column('subscription_tier', sa.String(length=32), nullable=False, server_default='free'))
    op.add_column('users', sa.Column('subscription_status', sa.String(length=32), nullable=False, server_default='active'))
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('stripe_subscription_id', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('config_completed', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    # Existing admin account has completed config
    op.execute("UPDATE users SET config_completed = true WHERE id = 1")

    # Scoping on Posts
    op.add_column('posts', sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, server_default='1'))
    op.create_index('ix_posts_user_id', 'posts', ['user_id'], unique=False)

    # Scoping on Activity Log
    op.add_column('activity_log', sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, server_default='1'))
    op.create_index('ix_activity_log_user_id', 'activity_log', ['user_id'], unique=False)

    # Scoping on Generation Jobs
    op.add_column('generation_jobs', sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, server_default='1'))
    op.create_index('ix_generation_jobs_user_id', 'generation_jobs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_generation_jobs_user_id', table_name='generation_jobs')
    op.drop_column('generation_jobs', 'user_id')
    op.drop_index('ix_activity_log_user_id', table_name='activity_log')
    op.drop_column('activity_log', 'user_id')
    op.drop_index('ix_posts_user_id', table_name='posts')
    op.drop_column('posts', 'user_id')

    op.drop_column('users', 'config_completed')
    op.drop_column('users', 'stripe_subscription_id')
    op.drop_column('users', 'stripe_customer_id')
    op.drop_column('users', 'subscription_status')
    op.drop_column('users', 'subscription_tier')
    op.drop_column('users', 'cadence')
    op.drop_column('users', 'taste')
