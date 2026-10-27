"""renewal reminders: reminders_sent (one row per email, never sent twice) and users.subscription_interval

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-23 10:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('subscription_interval', sa.String(length=8), nullable=True))
    op.create_table(
        'reminders_sent',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'kind', 'period_end', 'day', name='uq_reminders_sent'),
    )
    op.create_index('ix_reminders_sent_user_id', 'reminders_sent', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_reminders_sent_user_id', table_name='reminders_sent')
    op.drop_table('reminders_sent')
    op.drop_column('users', 'subscription_interval')
