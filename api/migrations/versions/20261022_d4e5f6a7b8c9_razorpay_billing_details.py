"""razorpay subscriptions and GST billing details on users

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-22 12:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('razorpay_subscription_id', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('razorpay_pending_subscription_id', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('billing_name', sa.String(length=120), nullable=False, server_default=''))
    op.add_column('users', sa.Column('billing_country', sa.String(length=2), nullable=True))
    op.add_column('users', sa.Column('billing_state', sa.String(length=2), nullable=True))
    op.add_column('users', sa.Column('billing_gstin', sa.String(length=15), nullable=True))
    op.create_index('ix_users_razorpay_subscription_id', 'users', ['razorpay_subscription_id'])
    op.create_index('ix_users_razorpay_pending_subscription_id', 'users', ['razorpay_pending_subscription_id'])


def downgrade() -> None:
    op.drop_index('ix_users_razorpay_pending_subscription_id', table_name='users')
    op.drop_index('ix_users_razorpay_subscription_id', table_name='users')
    for col in ('billing_gstin', 'billing_state', 'billing_country', 'billing_name',
                'razorpay_pending_subscription_id', 'razorpay_subscription_id'):
        op.drop_column('users', col)
