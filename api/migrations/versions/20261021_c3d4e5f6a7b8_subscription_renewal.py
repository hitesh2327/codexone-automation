"""subscription renewal time on users; index the Stripe subscription id (webhooks look users up by it)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-21 12:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('subscription_renews_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_users_stripe_subscription_id', 'users', ['stripe_subscription_id'])


def downgrade() -> None:
    op.drop_index('ix_users_stripe_subscription_id', table_name='users')
    op.drop_column('users', 'subscription_renews_at')
