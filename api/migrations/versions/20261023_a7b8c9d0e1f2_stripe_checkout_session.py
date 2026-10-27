"""stripe again: users.stripe_checkout_session_id (the open Checkout Session of a new plan or an upgrade)

Billing is back on Stripe (src/billing_stripe.py; BILLING_PROVIDER=razorpay switches to src/billing_razorpay.py,
whose columns stay). stripe_customer_id and stripe_subscription_id already exist.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-23 18:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True))
    op.create_index('ix_users_stripe_checkout_session_id', 'users', ['stripe_checkout_session_id'])


def downgrade() -> None:
    op.drop_index('ix_users_stripe_checkout_session_id', table_name='users')
    op.drop_column('users', 'stripe_checkout_session_id')
